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
