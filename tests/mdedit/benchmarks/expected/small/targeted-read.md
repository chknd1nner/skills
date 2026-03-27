Meridian is implemented in Go. The core pipeline is a linear chain of stage functions, each receiving a document context and returning a modified context or an error. Stages are registered at startup via a configuration file.

The pipeline runner manages a configurable worker pool. Each worker pulls jobs from a shared queue backed by Redis. Failed jobs are placed on a dead-letter queue with full context preserved for later inspection or replay.

Deployment is managed via a Helm chart. The service exposes Prometheus metrics on port 9090 and a health check endpoint at `/healthz`. Configuration is provided via a YAML file mounted into the pod at `/etc/meridian/config.yaml`.

The standard stage set includes: deduplication, schema validation, PII redaction, metadata enrichment, classification, and output routing. Each stage is independently testable and can be disabled via configuration.
