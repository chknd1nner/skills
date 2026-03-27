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



The pipeline runner is the central coordination component. It is initialized with a configuration, a set of registered stages, a queue backend, and an output sink. On startup it:

1. Validates the stage registry against the configured stage list, failing fast if any configured stage is not registered.
2. Establishes connectivity to the queue backend and output sink, retrying with exponential backoff for up to 30 seconds before giving up.
3. Launches the worker pool.
4. Begins the health check HTTP server.

Workers run in a loop: pull a job from the queue, execute the stage chain, write the result or dispatch to the DLQ, acknowledge the job. The queue backend uses Redis BLPOP for blocking dequeue with a 5-second timeout, which allows workers to wake on new items without busy-waiting.


The worker pool is a fixed-size pool of goroutines. The pool size is configurable via `pipeline.workers` in the configuration file and defaults to `runtime.NumCPU() * 2`. A `sync.WaitGroup` tracks live workers; the runner waits for all workers to finish draining before shutdown to avoid message loss during graceful termination.

Workers do not share state directly. Each worker has its own context derived from the root context, cancelled when the runner receives a termination signal. Stage functions receive this context and are expected to respect cancellation, particularly for any I/O operations.


Stages execute sequentially within a worker. Each stage receives the current `*Document` and returns either a modified `*Document` or an error. A non-nil error from any stage short-circuits the remainder of the chain and routes the document to the DLQ.

Stage functions must be safe to call concurrently from multiple goroutines. The contract is enforced by convention rather than compile-time checks; the code review checklist includes a concurrency safety item for new stages.

Retry logic is intentionally absent from the stage execution loop. Transient errors (network timeouts, downstream unavailability) are expected to be handled within the stage itself if retrying is appropriate. The DLQ provides the mechanism for human-reviewed replay of persistently failed documents.


On receiving SIGTERM or SIGINT, the runner:

1. Stops accepting new jobs from the queue by cancelling the worker contexts.
2. Allows in-flight jobs to complete, waiting up to 30 seconds.
3. Flushes any buffered output to the sink.
4. Closes queue and sink connections.
5. Exits with code 0 if all in-flight jobs completed, code 1 if the 30-second timeout was reached.

This behavior ensures that a rolling deployment does not result in processing gaps: Kubernetes will not route new work to a terminating pod, and the pod will not exit until current work is done.


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


```go
type AuditEntry struct {
    Stage     string    `json:"stage"`
    Action    string    `json:"action"`
    Detail    string    `json:"detail,omitempty"`
    Timestamp time.Time `json:"timestamp"`
}
```

Every stage that modifies the document must append an `AuditEntry` before returning. The audit trail is written to the audit log sink in its entirety, regardless of pipeline outcome. This is enforced by the runner after each stage call; stages that forget to append an entry will have one generated automatically with `Action: "completed"` and no detail.


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



Unit tests cover individual stages, adapters, and utility functions in isolation. The test convention is:

- Each `internal/` package has a `_test.go` file in the same package (white-box testing).
- Each `stages/` stage has a corresponding `_test.go` testing the stage function directly.
- No external I/O is permitted in unit tests. Redis, Kafka, and file I/O are either mocked or avoided.

Unit tests are run with `go test ./...` and must complete in under 30 seconds on developer hardware.


Integration tests are in the `integration/` directory (build tag `integration`) and require live Redis and Kafka instances. They are run in CI using Docker Compose to spin up dependencies. Each test:

1. Creates a fresh Redis keyspace with a test-specific prefix.
2. Submits one or more documents to the queue.
3. Runs the pipeline runner for a bounded duration.
4. Asserts on documents arriving at the output topic.
5. Cleans up its keyspace after completion.

Integration tests must complete in under 5 minutes in CI. Tests that cannot meet this bound are moved to a separate `slow_integration` suite that runs nightly.


Benchmark tests measure pipeline throughput and latency under controlled load. They live in `benchmarks/` and are run with `go test -bench=. ./benchmarks/...`. Results are recorded to `benchmarks/results/` and compared against a baseline to detect regressions.

The benchmark suite includes:
- Single-stage throughput (measures the runner overhead, not stage logic).
- Full pipeline throughput with all production stages enabled.
- DLQ placement rate under high error injection.
- Latency distribution at p50, p95, p99 under sustained and burst load.


Load tests are run against a dedicated staging environment and are not part of the automated test suite. The load test harness is in `loadtest/` and uses `k6`. Results from pre-release load tests are stored in `benchmarks/results/load/`.
