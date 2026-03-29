---
title: Meridian Document Processing Pipeline
date: 2024-11-12
status: stable
---

# Meridian

Meridian is a lightweight document processing pipeline designed to ingest, transform, and route structured documents at scale. It was developed to address reliability and throughput gaps in our legacy batch processing system.

## Background

Document processing at our organization historically relied on a single-threaded Python script that consumed files from a watched directory. As ingestion volume grew past 10,000 documents per day, processing lag became a recurring production issue.

Meridian was scoped to replace this with a pipeline that could handle burst traffic, support pluggable transformation stages, and emit structured audit logs for compliance purposes.

The project kicked off in Q3 2024 and reached stable release in November of the same year. Development took approximately three months with a two-engineer team.

The name "Meridian" reflects the goal of creating a single, well-defined passage point for all document traffic — a line every document crosses on its way to downstream systems.

## Implementation

Meridian is implemented in Go. The core pipeline is a linear chain of stage functions, each receiving a document context and returning a modified context or an error. Stages are registered at startup via a configuration file.

The pipeline runner manages a configurable worker pool. Each worker pulls jobs from a shared queue backed by Redis. Failed jobs are placed on a dead-letter queue with full context preserved for later inspection or replay.

Deployment is managed via a Helm chart. The service exposes Prometheus metrics on port 9090 and a health check endpoint at `/healthz`. Configuration is provided via a YAML file mounted into the pod at `/etc/meridian/config.yaml`.

The standard stage set includes: deduplication, schema validation, PII redaction, metadata enrichment, classification, and output routing. Each stage is independently testable and can be disabled via configuration.

## Results

In load testing against a synthetic corpus of 50,000 mixed-format documents, Meridian sustained 1,200 documents per second on a three-node cluster with p99 latency under 40ms.

Production deployment in December 2024 reduced processing lag from an average of 18 minutes to under 30 seconds. No data loss events have been recorded since rollout.

The dead-letter queue rate in production is below 0.02%. All DLQ entries are reviewed weekly; most are attributable to upstream schema changes in partner data feeds rather than pipeline defects.

## Conclusion

This project demonstrated significant improvements in processing speed
and memory efficiency. Future work will focus on scaling to larger
datasets and improving the user interface.

## References

- Internal RFC: Meridian Architecture Proposal (RFC-0041)
- Internal RFC: Meridian API Surface (RFC-0047)
- Go worker pool pattern: https://gobyexample.com/worker-pools
- Prometheus client library: https://github.com/prometheus/client_golang
- Helm chart documentation: https://helm.sh/docs/chart_template_guide/
- Redis BLPOP: https://redis.io/commands/blpop/
