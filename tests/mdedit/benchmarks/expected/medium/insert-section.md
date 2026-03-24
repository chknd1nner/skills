---
title: Meridian Document Processing Pipeline — Design Document
date: 2024-10-03
status: approved
revision: 2
---

# Meridian Design Document

This document describes the design of the Meridian document processing pipeline, including architecture decisions, data model, API surface, and test approach. It is intended for engineers contributing to or integrating with the system.

For a shorter overview, see the project README. For operational procedures, see RUNBOOK-meridian-001. This document covers design rationale and is the appropriate reference when making changes to the system's core behavior.

## Background

### Problem Statement

Document processing at the organization was handled by a legacy Python script (`doc_processor.py`) that had accumulated over six years of incremental patches. The script ran as a cron job every five minutes, polled a local directory, and processed files sequentially. Several characteristics made it a persistent source of operational pain:

- Sequential processing meant a single large file could block the queue for minutes at a time.
- No retry logic: transient failures silently dropped documents.
- No structured logging: debugging required grepping through unstructured stdout captures.
- The script had no test coverage and was considered too fragile to refactor safely.

By mid-2024, peak ingestion volumes had grown to 15,000 documents per day, with burst spikes reaching 3,000 documents per hour. The existing system could not keep up without manual intervention.

### Goals

The replacement system was required to:

1. Process documents concurrently across a configurable worker pool.
2. Guarantee at-least-once delivery with idempotent stage execution where possible.
3. Emit structured, queryable audit logs per document.
4. Be deployable via the organization's standard Kubernetes/Helm workflow.
5. Support pluggable transformation stages without changes to the core runner.

### Non-Goals

Meridian does not aim to be a general-purpose workflow engine. It does not support branching pipelines, conditional routing, or fan-out semantics in the initial release. These may be addressed in a future version.

Explicitly out of scope: real-time stream processing, cross-tenant isolation, GUI-based pipeline configuration, and automatic schema inference from arbitrary document formats.

## Implementation

Meridian is written in Go 1.22. The choice of Go was driven by strong concurrency primitives, a small deployment footprint, and existing team familiarity. The codebase is organized as a single Go module at `github.com/org/meridian`, with `internal/` packages for pipeline, document, queue, sink, adapter, and API components.

The system is deployed as a single binary. There is no separate worker binary and coordinator binary — the same process runs the worker pool, the management API, and the metrics endpoint. This simplifies deployment and reduces the operational surface area, at the cost of colocating concerns that could in principle be scaled independently. A future microservices split is not planned; the single-binary model has proven adequate for current scale.

Configuration is provided via a YAML file. The most important configuration decisions are the worker count (which controls parallelism and memory footprint) and the stage list (which determines what transformations are applied). Example:

```yaml
pipeline:
  workers: 16

stages:
  - name: deduplicate
  - name: validate_schema
  - name: redact_pii
  - name: enrich_metadata
  - name: classify
  - name: route
```

Stages run in the order they appear in the configuration. The ordering has functional implications: for example, `redact_pii` must run before `enrich_metadata` to ensure enrichment does not inadvertently restore redacted values by fetching them from an external source.

### Architecture

#### Overview

The pipeline is structured as a linear chain of named stages. At startup, the runner loads a YAML configuration file that specifies which stages are active and in what order. Each stage is a function conforming to the following interface:

```go
type Stage func(ctx context.Context, doc *Document) (*Document, error)
```

Stages are stateless by design. Any state required across documents (for example, a deduplication cache) must be injected as a dependency at registration time, not stored in global variables. This constraint simplifies testing and makes memory usage explicit.

The runner maintains a worker pool. Each worker pulls a job from the job queue, executes the full stage chain, and writes the result to the output sink. Workers are goroutines managed by a `sync.WaitGroup`. The pool size is configurable and defaults to the number of available CPU cores multiplied by two.

If any stage returns an error, the runner places the job on the dead-letter queue (DLQ) with the full document context, the stage name, the error message, and a timestamp. DLQ entries are retained for 72 hours and can be replayed via the management API.

#### Graceful Shutdown

On receiving SIGTERM, the runner stops accepting new jobs, waits up to 30 seconds for in-flight jobs to complete, flushes buffered output, closes connections, and exits. This ensures rolling deployments do not cause message loss: Kubernetes removes the pod from service endpoints before sending SIGTERM, so no new jobs will be routed to a terminating instance.

The 30-second shutdown window is configurable. In practice, most jobs complete in well under a second, so the window is rarely exercised. In the event of a stage hang, the runner will forcibly exit after the timeout and place the in-flight document on the DLQ during the next startup via a startup-time DLQ reconciliation scan.

### Data Model

A `Document` is the central data structure flowing through the pipeline:

```go
type Document struct {
    ID          string            `json:"id"`
    Source      string            `json:"source"`
    Format      string            `json:"format"`
    RawContent  []byte            `json:"-"`
    Parsed      map[string]any    `json:"parsed,omitempty"`
    Metadata    map[string]string `json:"metadata"`
    AuditTrail  []AuditEntry      `json:"audit_trail"`
    ProcessedAt time.Time         `json:"processed_at,omitempty"`
}
```

Each stage that modifies the document appends an `AuditEntry` recording what changed, the stage name, and the wall-clock timestamp. This trail is written to the audit log sink regardless of whether the document successfully completes the pipeline.

Documents are identified by a content-addressed ID derived from a SHA-256 hash of the raw input bytes. This makes ingestion idempotent: submitting the same file twice results in the same document ID, and the deduplication stage will discard the duplicate if configured to do so.

The `Metadata` map is a general-purpose bag for key-value pairs accumulated during processing. Stages should use namespaced keys (for example, `enrich.industry` or `classify.label`) to avoid collisions. The `Tags` slice is reserved for classification labels that drive routing decisions; stage authors should add to it rather than encoding labels in `Metadata`.

The `PIIFields` list contains dot-notation paths into the `Parsed` map (for example, `"contact.email"` or `"customer.name"`). The `redact_pii` stage replaces values at these paths with the string `[REDACTED]` before the document is written to the output sink. The original values are never written to any persistent store.

### API Design

Meridian exposes an HTTP API for operational purposes. The API is not intended for high-throughput ingestion; documents are ingested via the queue. The API provides:

| Endpoint | Method | Description |
|---|---|---|
| `/healthz` | GET | Liveness probe |
| `/readyz` | GET | Readiness probe (checks queue connectivity) |
| `/metrics` | GET | Prometheus metrics |
| `/api/v1/dlq` | GET | List dead-letter queue entries |
| `/api/v1/dlq/{id}/replay` | POST | Replay a DLQ entry |
| `/api/v1/pipeline/stages` | GET | List registered stages and their order |

Authentication on the management API is handled via a bearer token configured through an environment variable (`MERIDIAN_API_TOKEN`). In future releases this will migrate to mTLS.

The API listens on `:8080` by default for management traffic and `:9090` for metrics. These ports are configurable. The metrics endpoint is unauthenticated by convention, consistent with typical Prometheus scrape setups where network-level controls restrict access.

### Testing

The test suite is split into three layers:

**Unit tests** cover individual stages in isolation. Each stage test constructs a minimal `Document`, calls the stage function directly, and asserts on the returned document or error. No I/O occurs in unit tests. Unit tests run with `go test ./...` and must complete in under 30 seconds.

**Integration tests** spin up a local Redis instance using testcontainers-go and run the full pipeline against a set of fixture documents. These tests verify end-to-end behavior, including DLQ placement for documents that fail at a given stage. Integration tests use a `//go:build integration` build tag and are run in CI via Docker Compose.

**Benchmark tests** measure throughput and latency for the pipeline under synthetic load. They are not part of the standard `go test ./...` run and must be invoked explicitly with `-bench=.`. Results are tracked per commit in a separate results directory and compared against a stored baseline to detect regressions.

The test coverage target is 80% for `internal/` packages. Coverage for `stages/` is expected to be higher, as stage logic is the most likely source of correctness bugs.

## Results

### Performance

Load testing was conducted against a corpus of 50,000 documents ranging from 1 KB to 2 MB in size, distributed as a realistic approximation of production traffic. The test cluster consisted of three nodes, each with 8 vCPUs and 16 GB RAM.

Sustained throughput reached 1,200 documents per second at p50 latency of 12ms and p99 latency of 38ms. Under burst conditions (3x sustained load for 60 seconds), the pipeline maintained throughput without queue starvation, recovering to steady-state within 90 seconds of the burst ending.

Memory usage per worker was stable at approximately 22 MB RSS under sustained load. No memory leaks were detected over a 4-hour soak test.

In production, the system processed 2.8 million documents in the first 30 days with zero data loss. The `redact_pii` stage accounts for the largest share of per-document CPU time (~40%) due to regex evaluation over parsed document trees.

### Limitations

Several limitations were identified during the testing phase and are tracked as known issues:

- Documents larger than 10 MB are processed correctly but cause elevated p99 latency due to in-memory copying within the stage chain. A streaming document abstraction is planned for a future release.
- The deduplication stage relies on an in-memory LRU cache with a configurable capacity. In multi-node deployments, deduplication is per-node only; cross-node deduplication requires an external cache (for example, a Redis set), which is implemented but disabled by default pending performance validation.
- The replay API replays DLQ entries synchronously in the request handler. For large backlogs, callers should prefer `meridian-ctl dlq replay --all`, which batches replays and reports progress incrementally.
- PII redaction is best-effort: the `redact_pii` stage only redacts fields explicitly listed by the source adapter. Automatic PII detection is a backlog item.

## Future Work

Several promising directions emerge from this work. First, the architecture
could be extended to support distributed processing across multiple nodes.
Second, the validation pipeline would benefit from property-based testing
to catch edge cases. Third, integration with existing CI/CD systems would
reduce deployment friction.

## Conclusion

Meridian successfully replaced the legacy processing script with a system that meets all defined goals. The worker pool architecture provides horizontal scalability, the pluggable stage interface has been adopted by two additional teams, and the structured audit log has reduced mean time to diagnose processing failures from hours to minutes.

The design choices that proved most valuable in hindsight were the content-addressed document ID (which eliminated an entire class of duplicate-processing bugs) and the decision to make stages stateless (which dramatically simplified both testing and deployment of new stages).

The content-addressed ID also enabled a useful operational property: submitting the same document twice is harmless by default, because the deduplication stage will recognize and discard the duplicate. This has simplified integration for several upstream systems that could not guarantee exactly-once delivery.

Architecturally, the decision to constrain stages to be stateless has had the largest compounding benefit. It means any stage can be developed, tested, and reasoned about independently of the rest of the pipeline. It means stages can be reordered without hidden state-dependency bugs. And it means the worker pool can scale horizontally without coordination: all workers are equivalent and any worker can process any document.

Open items for the next development cycle include streaming source support, cross-node deduplication, and a web UI for dead-letter queue inspection. The streaming abstraction is the most important of these, as it unblocks processing of large documents without latency regression. The web UI is the highest-priority usability improvement based on operator feedback from the first quarter of production operation.

## References

- RFC-0041: Meridian Architecture Proposal (internal)
- RFC-0047: Meridian API Surface (internal)
- RFC-0052: Meridian Kafka Queue Backend (internal)
- ADR-0011: Choice of Redis for queue backend (internal)
- ADR-0014: Content-addressed document identity (internal)
- Go worker pool pattern: https://gobyexample.com/worker-pools
- testcontainers-go: https://github.com/testcontainers/testcontainers-go
- Prometheus client for Go: https://github.com/prometheus/client_golang
- Content-addressed storage concepts: https://en.wikipedia.org/wiki/Content-addressable_storage
- Helm chart best practices: https://helm.sh/docs/chart_best_practices/
- Redis BLPOP: https://redis.io/commands/blpop/
- Kubernetes graceful termination: https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-termination
