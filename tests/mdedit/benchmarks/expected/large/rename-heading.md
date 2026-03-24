---
title: Meridian Document Processing Pipeline — Comprehensive Reference
date: 2024-12-01
status: stable
revision: 5
authors:
  - Platform Engineering Team
classification: internal
last_reviewed: 2024-11-28
---

# Meridian Comprehensive Reference

This document is the authoritative reference for the Meridian document processing pipeline. It covers the system's history, full architecture, all data structures, the complete API surface, operational procedures, performance characteristics, and known limitations. Engineers responsible for operating, extending, or integrating with Meridian should treat this document as the primary source of truth.

## Background

### History

Meridian's origins trace back to a post-incident review conducted in July 2024, following a 14-hour processing outage caused by a single malformed file that caused the legacy processor to enter an infinite retry loop. The incident resulted in a backlog of over 40,000 unprocessed documents and required manual intervention by two engineers over a weekend.

The legacy system, `doc_processor.py`, had been in continuous operation since 2018. It was written by a contractor who had since left the organization, and no engineer on the current team had a complete mental model of its behavior. The codebase was 2,400 lines of undocumented Python with no test coverage.

The post-incident review produced three recommendations:

1. Replace the legacy processor with a system that had bounded failure modes and explicit error handling.
2. Invest in test coverage before adding new transformation logic.
3. Adopt structured logging and metrics emission as first-class requirements rather than afterthoughts.

Meridian was chartered to fulfill all three recommendations. Development began in August 2024 under the Platform Engineering team. A beta deployment ran alongside the legacy system from October through mid-November, with full cutover completing on November 18, 2024.

### Problem Domain

The organization processes documents arriving from four distinct source systems: a vendor EDI feed, an internal content management system, a partner API, and a manual upload portal. Each source produces documents in different formats (JSON, XML, CSV, and binary PDF respectively), with varying schemas and quality characteristics.

Prior to Meridian, each source had its own ad-hoc processing path, sharing no infrastructure or monitoring. This made it impossible to reason about system-wide throughput or error rates, and meant that any reliability improvement had to be applied four times independently.

Meridian unified these four ingestion paths behind a single pipeline abstraction. Source-specific parsing logic was encapsulated in source adapters; everything downstream of parsing — transformation, validation, routing, and audit logging — became shared infrastructure.

### Stakeholders

The following teams have a material interest in Meridian's correctness and availability:

- **Platform Engineering**: owns and operates the system.
- **Data Engineering**: consumes processed document events from the output Kafka topic.
- **Compliance**: relies on the audit log for regulatory reporting. Any change to audit log format or retention must be reviewed by Compliance before deployment.
- **Partner Integrations**: operates the partner API source adapter and deploys custom transformation stages.
- **Security**: reviews changes to authentication, authorization, and any handling of PII fields.

### Goals

The system was designed to satisfy the following goals, ranked by priority:

1. **Reliability**: no document should be silently dropped. Every input must either be successfully processed or land on the dead-letter queue with a full explanation.
2. **Observability**: operators must be able to determine system state, per-document processing history, and error patterns using only standard tooling (Prometheus, structured logs, the management API).
3. **Extensibility**: new transformation stages should be addable without touching the core runner. New source adapters should be addable without touching existing adapters.
4. **Throughput**: the system should sustain at least 800 documents per second on the minimum-spec cluster to provide headroom above peak observed traffic.
5. **Operability**: runbook procedures should cover all common failure scenarios, and the system should be deployable and rollbackable within five minutes.

### Non-Goals

The following are explicitly out of scope for Meridian v1:

- Branching or conditional pipeline execution.
- Fan-out (delivering one input document to multiple downstream outputs).
- Real-time streaming ingestion (Meridian processes discrete documents, not event streams).
- Cross-tenant isolation (all documents are processed within a single trust boundary).
- A graphical user interface for pipeline configuration.

## Implementation

Meridian is written in Go 1.22. The codebase is organized as a single Go module at `github.com/org/meridian`. The top-level package structure is:

```
meridian/
  cmd/
    meridian/       # Main binary entrypoint
    meridian-ctl/   # Management CLI
  internal/
    pipeline/       # Core runner and stage interface
    document/       # Document type and audit trail
    queue/          # Queue abstraction and Redis backend
    sink/           # Output sink abstraction
    adapter/        # Source adapter interface and implementations
    api/            # HTTP management API
    metrics/        # Prometheus metric definitions
    config/         # Configuration loading and validation
  stages/           # Built-in transformation stages
  testutil/         # Shared test helpers
```

### Architecture

#### Pipeline Runner

The pipeline runner is the central coordination component. It is initialized with a configuration, a set of registered stages, a queue backend, and an output sink. On startup it:

1. Validates the stage registry against the configured stage list, failing fast if any configured stage is not registered.
2. Establishes connectivity to the queue backend and output sink, retrying with exponential backoff for up to 30 seconds before giving up.
3. Launches the worker pool.
4. Begins the health check HTTP server.

Workers run in a loop: pull a job from the queue, execute the stage chain, write the result or dispatch to the DLQ, acknowledge the job. The queue backend uses Redis BLPOP for blocking dequeue with a 5-second timeout, which allows workers to wake on new items without busy-waiting.

#### Worker Pool

The worker pool is a fixed-size pool of goroutines. The pool size is configurable via `pipeline.workers` in the configuration file and defaults to `runtime.NumCPU() * 2`. A `sync.WaitGroup` tracks live workers; the runner waits for all workers to finish draining before shutdown to avoid message loss during graceful termination.

Workers do not share state directly. Each worker has its own context derived from the root context, cancelled when the runner receives a termination signal. Stage functions receive this context and are expected to respect cancellation, particularly for any I/O operations.

#### Stage Execution

Stages execute sequentially within a worker. Each stage receives the current `*Document` and returns either a modified `*Document` or an error. A non-nil error from any stage short-circuits the remainder of the chain and routes the document to the DLQ.

Stage functions must be safe to call concurrently from multiple goroutines. The contract is enforced by convention rather than compile-time checks; the code review checklist includes a concurrency safety item for new stages.

Retry logic is intentionally absent from the stage execution loop. Transient errors (network timeouts, downstream unavailability) are expected to be handled within the stage itself if retrying is appropriate. The DLQ provides the mechanism for human-reviewed replay of persistently failed documents.

#### Graceful Shutdown

On receiving SIGTERM or SIGINT, the runner:

1. Stops accepting new jobs from the queue by cancelling the worker contexts.
2. Allows in-flight jobs to complete, waiting up to 30 seconds.
3. Flushes any buffered output to the sink.
4. Closes queue and sink connections.
5. Exits with code 0 if all in-flight jobs completed, code 1 if the 30-second timeout was reached.

This behavior ensures that a rolling deployment does not result in processing gaps: Kubernetes will not route new work to a terminating pod, and the pod will not exit until current work is done.

### Source Adapters

Source adapters are responsible for translating raw bytes from a source-specific format into the canonical `Document` type. Each adapter implements the following interface:

```go
type Adapter interface {
    // SourceID returns the stable identifier for this source.
    SourceID() string
    // Parse takes raw bytes and returns a Document or an error.
    Parse(ctx context.Context, raw []byte) (*document.Document, error)
    // Validate checks the parsed document for source-specific invariants.
    Validate(ctx context.Context, doc *document.Document) error
}
```

Four adapters are included in the standard distribution:

| Adapter | Source | Format | Notes |
|---|---|---|---|
| `edi` | Vendor EDI feed | X12 EDI | Uses the `edify` library for parsing |
| `cms` | Internal CMS | JSON | Schema-validated against a versioned JSON Schema |
| `partner` | Partner API | XML | Namespace-aware; handles two legacy schema versions |
| `upload` | Manual upload portal | PDF | Text extraction via `pdftotext`; binary content stored separately |

Adapters are registered at startup and selected per-job based on a source discriminator field in the queue message. Unknown source values cause immediate DLQ placement without invoking any stages.

### Data Model

#### Document

The `Document` struct is the core data structure flowing through the pipeline:

```go
type Document struct {
    // ID is a content-addressed identifier derived from SHA-256 of RawContent.
    ID string `json:"id"`

    // Source identifies the originating source adapter.
    Source string `json:"source"`

    // Format is the input format as declared by the source adapter.
    Format string `json:"format"`

    // RawContent holds the original bytes as received. Never modified after creation.
    RawContent []byte `json:"-"`

    // Parsed holds the structured representation produced by the source adapter.
    // Schema varies by source; consumers should not assume a fixed structure.
    Parsed map[string]any `json:"parsed,omitempty"`

    // Metadata holds key-value pairs accumulated by stages.
    Metadata map[string]string `json:"metadata"`

    // Tags holds classification labels applied during processing.
    Tags []string `json:"tags,omitempty"`

    // PIIFields lists keys within Parsed that contain personally identifiable information.
    // These fields are redacted before the document is written to the output sink.
    PIIFields []string `json:"pii_fields,omitempty"`

    // AuditTrail records each stage's actions on this document.
    AuditTrail []AuditEntry `json:"audit_trail"`

    // IngestedAt is the time the document was placed on the queue.
    IngestedAt time.Time `json:"ingested_at"`

    // ProcessedAt is the time the final stage completed successfully.
    ProcessedAt time.Time `json:"processed_at,omitempty"`
}
```

#### AuditEntry

```go
type AuditEntry struct {
    Stage     string    `json:"stage"`
    Action    string    `json:"action"`
    Detail    string    `json:"detail,omitempty"`
    Timestamp time.Time `json:"timestamp"`
}
```

Every stage that modifies the document must append an `AuditEntry` before returning. The audit trail is written to the audit log sink in its entirety, regardless of pipeline outcome. This is enforced by the runner after each stage call; stages that forget to append an entry will have one generated automatically with `Action: "completed"` and no detail.

#### QueueMessage

The queue message format used by all source integrations:

```go
type QueueMessage struct {
    JobID     string    `json:"job_id"`
    Source    string    `json:"source"`
    Payload   []byte    `json:"payload"`
    EnqueuedAt time.Time `json:"enqueued_at"`
    Attempt   int       `json:"attempt"`
    TraceID   string    `json:"trace_id,omitempty"`
}
```

`JobID` is assigned by the enqueuing system and is used for deduplication at the queue level. `Attempt` is incremented each time the job is replayed from the DLQ. `TraceID` propagates a distributed trace identifier for correlation with upstream systems.

### Configuration

Configuration is loaded from a YAML file at startup. The path defaults to `/etc/meridian/config.yaml` and can be overridden with the `MERIDIAN_CONFIG` environment variable.

```yaml
pipeline:
  workers: 16
  shutdown_timeout: 30s
  dlq_retention: 72h

queue:
  backend: redis
  address: redis:6379
  list_key: meridian:jobs
  dlq_key: meridian:dlq
  connect_timeout: 5s

sink:
  backend: kafka
  brokers:
    - kafka-0:9092
    - kafka-1:9092
    - kafka-2:9092
  topic: meridian.processed
  acks: all

audit:
  sink: kafka
  topic: meridian.audit
  include_raw: false

api:
  listen: :8080
  metrics_listen: :9090
  auth_token_env: MERIDIAN_API_TOKEN

stages:
  - name: deduplicate
  - name: validate_schema
  - name: redact_pii
  - name: enrich_metadata
  - name: classify
  - name: route
```

All duration fields accept Go duration strings (`30s`, `5m`, `72h`). The configuration is validated at startup; any invalid field causes an immediate fatal error with a descriptive message.

### API Design

#### Management HTTP API

The management API runs on the port configured under `api.listen` (default `:8080`). All endpoints require a bearer token matching the value of the environment variable named in `api.auth_token_env`.

**Health and Readiness**

```
GET /healthz
```
Returns 200 if the process is alive. Does not check downstream connectivity. Used as the Kubernetes liveness probe.

```
GET /readyz
```
Returns 200 if the pipeline is ready to accept work (queue and sink connections are healthy). Returns 503 otherwise. Used as the Kubernetes readiness probe.

**Dead-Letter Queue**

```
GET /api/v1/dlq?limit=50&offset=0
```
Returns a paginated list of DLQ entries. Default limit is 50, maximum is 500. Entries are sorted by failure time descending.

```
GET /api/v1/dlq/{id}
```
Returns the full DLQ entry for the given document ID, including the full document context at time of failure.

```
POST /api/v1/dlq/{id}/replay
```
Re-enqueues the document for processing. Returns 202 on success. The `Attempt` counter in the re-enqueued message is incremented. The DLQ entry is not deleted until the document is successfully processed.

```
DELETE /api/v1/dlq/{id}
```
Removes a DLQ entry without replaying it. Intended for documents that are known to be unprocessable (for example, test documents accidentally ingested in production).

**Pipeline Introspection**

```
GET /api/v1/pipeline/stages
```
Returns the ordered list of registered stages, including name and a human-readable description if provided at registration.

```
GET /api/v1/pipeline/stats
```
Returns real-time pipeline statistics: worker count, queue depth, DLQ depth, documents processed (current process lifetime), and documents failed.

#### meridian-ctl CLI

`meridian-ctl` is a command-line client for the management API. It is intended for use in runbook procedures and automation scripts.

```
meridian-ctl dlq list
meridian-ctl dlq show <id>
meridian-ctl dlq replay <id>
meridian-ctl dlq replay --all
meridian-ctl dlq delete <id>
meridian-ctl pipeline stages
meridian-ctl pipeline stats
```

`meridian-ctl` reads the API endpoint and token from environment variables `MERIDIAN_API_URL` and `MERIDIAN_API_TOKEN` respectively, or from a config file at `~/.meridian/ctl.yaml`.

### Testing

#### Unit Tests

Unit tests cover individual stages, adapters, and utility functions in isolation. The test convention is:

- Each `internal/` package has a `_test.go` file in the same package (white-box testing).
- Each `stages/` stage has a corresponding `_test.go` testing the stage function directly.
- No external I/O is permitted in unit tests. Redis, Kafka, and file I/O are either mocked or avoided.

Unit tests are run with `go test ./...` and must complete in under 30 seconds on developer hardware.

#### Integration Tests

Integration tests are in the `integration/` directory (build tag `integration`) and require live Redis and Kafka instances. They are run in CI using Docker Compose to spin up dependencies. Each test:

1. Creates a fresh Redis keyspace with a test-specific prefix.
2. Submits one or more documents to the queue.
3. Runs the pipeline runner for a bounded duration.
4. Asserts on documents arriving at the output topic.
5. Cleans up its keyspace after completion.

Integration tests must complete in under 5 minutes in CI. Tests that cannot meet this bound are moved to a separate `slow_integration` suite that runs nightly.

#### Benchmark Tests

Benchmark tests measure pipeline throughput and latency under controlled load. They live in `benchmarks/` and are run with `go test -bench=. ./benchmarks/...`. Results are recorded to `benchmarks/results/` and compared against a baseline to detect regressions.

The benchmark suite includes:
- Single-stage throughput (measures the runner overhead, not stage logic).
- Full pipeline throughput with all production stages enabled.
- DLQ placement rate under high error injection.
- Latency distribution at p50, p95, p99 under sustained and burst load.

#### Load Tests

Load tests are run against a dedicated staging environment and are not part of the automated test suite. The load test harness is in `loadtest/` and uses `k6`. Results from pre-release load tests are stored in `benchmarks/results/load/`.

## Results

### Performance

#### Throughput

Benchmark and load test results as of the v1.0.0 release:

| Scenario | Cluster | Throughput (docs/sec) | p50 latency | p99 latency |
|---|---|---|---|---|
| Baseline (no-op stages) | 1 node, 8 vCPU | 4,200 | 3ms | 11ms |
| Production stages | 1 node, 8 vCPU | 890 | 14ms | 42ms |
| Production stages | 3 nodes, 8 vCPU | 2,650 | 14ms | 39ms |
| Burst (3x, 60s) | 3 nodes, 8 vCPU | 2,480 (sustained during burst) | 17ms | 61ms |

Throughput scales approximately linearly with worker count up to the point where the Redis queue becomes the bottleneck. At very high worker counts (>64 per node), Redis BLPOP contention becomes visible in latency histograms. For deployments requiring more than 3,000 docs/sec sustained, a Kafka-backed queue variant is available (see the `queue.backend: kafka` configuration option).

Memory usage per worker is stable at approximately 22 MB RSS under sustained load with the standard stage configuration. The `redact_pii` stage accounts for approximately 40% of per-document CPU time due to regex evaluation over the parsed document tree.

#### Reliability

Over the first 30 days of production operation:

- Total documents processed: 2,847,291
- Documents placed on DLQ: 412 (0.014%)
- Documents replayed from DLQ: 388
- Documents deleted from DLQ (unprocessable): 24
- Data loss events: 0

The 24 unprocessable documents were all traced to a schema version mismatch in the partner adapter that was fixed in v1.0.2. No documents were lost; all were retained in the DLQ and manually reviewed before deletion.

#### Scalability

Horizontal scaling has been validated up to 10 nodes. Beyond 3 nodes, the primary bottleneck shifts from CPU to queue throughput. The Kafka-backed queue backend was introduced in v1.1.0 to address this; it has been used in the partner integrations deployment, which operates at higher sustained volume.

### Limitations

#### Known Issues

The following limitations are tracked and accepted for v1.x:

**Large document latency.** Documents larger than 10 MB cause elevated p99 latency due to in-memory copying within the stage chain. Each stage receives a pointer to the document, but stages that produce a modified document currently copy the `Parsed` map. A streaming document abstraction using `io.Reader`-based APIs is planned for v2.0. Workaround: configure the upload adapter to reject documents exceeding 10 MB until v2.0 is available.

**Per-node deduplication only.** The `deduplicate` stage uses an in-memory LRU cache with a configurable capacity (default 100,000 entries). In multi-node deployments, a document submitted twice in rapid succession may be processed on different nodes, each with a cold cache entry, resulting in duplicate output. Cross-node deduplication via a shared Redis set is implemented but disabled by default pending performance validation.

**Synchronous DLQ replay.** The `POST /api/v1/dlq/{id}/replay` endpoint re-enqueues the document synchronously in the request handler. Replaying large DLQ backlogs (>1,000 entries) via the API can cause request timeouts. Use `meridian-ctl dlq replay --all` which batches replays and reports progress incrementally.

**PII redaction is best-effort.** The `redact_pii` stage redacts fields listed in `Document.PIIFields`. Fields must be explicitly listed by the source adapter; the stage does not perform automatic PII detection. Adapters that fail to populate `PIIFields` will pass PII through to the output topic unredacted.

#### Operational Constraints

- Redis must be available at startup. Meridian will not start if it cannot connect to the configured queue backend.
- The output Kafka topic must exist before Meridian starts. Topic auto-creation is disabled to prevent silent misconfiguration.
- The audit log Kafka topic must be separate from the output topic. Using the same topic for both will cause audit entries to be processed as documents.
- Configuration changes require a restart. There is no hot-reload support.

#### Future Work

The following items are planned for future releases:

- **v1.2**: Cross-node deduplication (Redis set backend for the deduplicate stage).
- **v1.3**: Hot configuration reload without pipeline restart.
- **v2.0**: Streaming document abstraction; support for documents as `io.Reader` through the stage chain.
- **v2.1**: Branching pipeline support (conditional stage execution based on document classification).
- **Backlog**: Web UI for DLQ inspection and replay; automatic PII detection stage.

## Summary and Next Steps

Meridian v1.0 delivered on all five stated goals. The reliability record in the first 30 days of production — zero data loss events and a DLQ rate under 0.02% — represents a substantial improvement over the legacy system, which had no visibility into loss events at all. The observability investment has paid dividends: the average time to diagnose a processing anomaly dropped from several hours to under ten minutes, and two incidents that would previously have required on-call pages were resolved by the on-duty engineer using the management API without escalation.

One of the less-anticipated benefits of the content-addressed ID scheme was its effect on operator confidence during incident response. When investigating a suspected duplicate-processing event, engineers can immediately determine whether two DLQ entries represent the same underlying document by comparing IDs — no guessing, no timestamp correlation. This has meaningfully reduced the cognitive overhead of post-incident reviews.

The decision to make configuration changes require a restart was deliberate but has generated the most friction in practice. Several teams have requested hot-reload support to allow stage configuration changes without service disruption. This is planned for v1.3 and will be implemented via a SIGHUP handler that reloads and revalidates the configuration file, then drains the current worker pool and starts a new pool with the updated configuration.

Operationally, the `meridian-ctl` CLI has become the primary interface for day-to-day management. The management API exists to support automation, but most human workflows go through the CLI. Future CLI development will focus on richer output formatting, progress indicators for bulk operations, and integration with the organization's incident management tooling.

The extensibility model has been validated in practice. The Partner Integrations team deployed a custom transformation stage without any changes to the core runner, and Data Engineering added a new output routing rule through configuration alone. The boundary between "core infrastructure" and "pluggable behavior" has held in all cases so far.

Looking ahead, the two most important investments are the streaming document abstraction (to address the large-document latency limitation) and the web UI for DLQ management (to reduce the operational burden of the replay workflow, which currently requires familiarity with `meridian-ctl`). Both are planned for the next major development cycle.

The fundamental architectural choices — content-addressed document IDs, stateless stages, queue-backed worker pools, and structured audit logging — have proven durable. No rearchitecting is anticipated for v2.x. The system is expected to meet organizational document processing needs for at least the next two years without major structural change.

## References

### Internal Documents

- RFC-0041: Meridian Architecture Proposal
- RFC-0047: Meridian Management API Surface
- RFC-0052: Meridian Kafka Queue Backend
- RFC-0058: Meridian Cross-Node Deduplication (draft)
- INC-2024-0312: Post-incident review, legacy doc_processor outage
- INC-2024-0389: Partner adapter schema version mismatch (resolved in v1.0.2)
- RUNBOOK-meridian-001: Standard Operating Procedures
- RUNBOOK-meridian-002: DLQ Management and Replay Procedures
- RUNBOOK-meridian-003: Scaling and Capacity Planning
- ADR-0011: Choice of Redis for queue backend
- ADR-0014: Content-addressed document identity
- ADR-0019: Stateless stage contract

### External References

- Go standard library — sync package: https://pkg.go.dev/sync
- Go standard library — context package: https://pkg.go.dev/context
- Redis BLPOP documentation: https://redis.io/commands/blpop/
- Redis sorted sets (used for DLQ indexing): https://redis.io/docs/data-types/sorted-sets/
- testcontainers-go: https://github.com/testcontainers/testcontainers-go
- Prometheus Go client: https://github.com/prometheus/client_golang
- Prometheus naming conventions: https://prometheus.io/docs/practices/naming/
- Kafka Go client (confluent-kafka-go): https://github.com/confluentinc/confluent-kafka-go
- Kafka producer configuration reference: https://docs.confluent.io/platform/current/installation/configuration/producer-configs.html
- Content-addressable storage: https://en.wikipedia.org/wiki/Content-addressable_storage
- SHA-256 specification (FIPS 180-4): https://csrc.nist.gov/publications/detail/fips/180/4/final
- X12 EDI standard: https://www.x12.org/
- pdftotext (poppler): https://poppler.freedesktop.org/
- JSON Schema specification: https://json-schema.org/specification.html
- k6 load testing: https://k6.io/docs/
- Helm chart best practices: https://helm.sh/docs/chart_best_practices/
- Kubernetes graceful termination: https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-termination
- Kubernetes liveness and readiness probes: https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/
