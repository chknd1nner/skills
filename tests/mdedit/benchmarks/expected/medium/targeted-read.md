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



The pipeline is structured as a linear chain of named stages. At startup, the runner loads a YAML configuration file that specifies which stages are active and in what order. Each stage is a function conforming to the following interface:

```go
type Stage func(ctx context.Context, doc *Document) (*Document, error)
```

Stages are stateless by design. Any state required across documents (for example, a deduplication cache) must be injected as a dependency at registration time, not stored in global variables. This constraint simplifies testing and makes memory usage explicit.

The runner maintains a worker pool. Each worker pulls a job from the job queue, executes the full stage chain, and writes the result to the output sink. Workers are goroutines managed by a `sync.WaitGroup`. The pool size is configurable and defaults to the number of available CPU cores multiplied by two.

If any stage returns an error, the runner places the job on the dead-letter queue (DLQ) with the full document context, the stage name, the error message, and a timestamp. DLQ entries are retained for 72 hours and can be replayed via the management API.


On receiving SIGTERM, the runner stops accepting new jobs, waits up to 30 seconds for in-flight jobs to complete, flushes buffered output, closes connections, and exits. This ensures rolling deployments do not cause message loss: Kubernetes removes the pod from service endpoints before sending SIGTERM, so no new jobs will be routed to a terminating instance.

The 30-second shutdown window is configurable. In practice, most jobs complete in well under a second, so the window is rarely exercised. In the event of a stage hang, the runner will forcibly exit after the timeout and place the in-flight document on the DLQ during the next startup via a startup-time DLQ reconciliation scan.


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


The test suite is split into three layers:

**Unit tests** cover individual stages in isolation. Each stage test constructs a minimal `Document`, calls the stage function directly, and asserts on the returned document or error. No I/O occurs in unit tests. Unit tests run with `go test ./...` and must complete in under 30 seconds.

**Integration tests** spin up a local Redis instance using testcontainers-go and run the full pipeline against a set of fixture documents. These tests verify end-to-end behavior, including DLQ placement for documents that fail at a given stage. Integration tests use a `//go:build integration` build tag and are run in CI via Docker Compose.

**Benchmark tests** measure throughput and latency for the pipeline under synthetic load. They are not part of the standard `go test ./...` run and must be invoked explicitly with `-bench=.`. Results are tracked per commit in a separate results directory and compared against a stored baseline to detect regressions.

The test coverage target is 80% for `internal/` packages. Coverage for `stages/` is expected to be higher, as stage logic is the most likely source of correctness bugs.
