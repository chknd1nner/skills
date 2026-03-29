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

### Architecture Overview

The rewritten implementation adopts an event-driven architecture to decouple components and improve scalability. Core events flow through a central message broker, allowing services to subscribe selectively and process asynchronously. This design eliminates tight coupling and enables independent deployment of service modules.

### Configuration Management

Configuration is now declarative via YAML, allowing operators to tune behavior without code changes. The configuration schema validates at startup, catching errors early. Environment variable substitution enables environment-specific overrides while maintaining a single canonical configuration file.

### Event Processing Pipeline

Events arrive at the ingestion layer where they are validated against schemas. Valid events proceed through a series of transformation stages—enrichment, deduplication, and aggregation. Each stage is independently scalable; high-volume event types can be processed on dedicated worker pools while others share capacity.

### Error Handling and Resilience

The system employs circuit breakers to prevent cascade failures. When a downstream service becomes unavailable, the circuit opens and requests are rejected fast rather than timing out. Once the service recovers, the circuit gradually reopens through a half-open state, verifying health before resuming normal traffic flow.

Transient errors trigger exponential backoff with jitter, reducing thundering herd problems during recovery. Dead-letter queues capture messages that cannot be processed, enabling later investigation and replay without losing data.

### Observability

Comprehensive logging and metrics instrumentation provide visibility into system behavior. Structured logging enables easy filtering and correlation of related events. Metrics cover request latencies, error rates, queue depths, and circuit breaker state—all essential for production monitoring.

Distributed tracing follows request flows across service boundaries, critical for understanding performance characteristics in the multi-service architecture. All tracing and metrics integrate with standard monitoring platforms.

### Deployment and Operations

The service is containerized with clear resource requirements. Kubernetes manifests define pod specifications, service configuration, and horizontal scaling policies. Blue-green deployments enable zero-downtime updates. Readiness and liveness probes ensure only healthy instances receive traffic.

Database migrations run in a separate init container before application startup, ensuring schema consistency. Configuration is mounted from ConfigMaps and Secrets, keeping sensitive data separate from container images.

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

## Conclusion

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
