# Source Discovery

Use this file when the source is not already a clean OpenAPI contract, or when the agent must decide how to build the connector.

## OpenAPI Discovery

Inspect:
- title, version, servers
- operations, request and response schemas
- auth schemes
- tags and webhook-like operations

Infer:
- event-producing operations
- canonical entities
- sample payloads
- candidate topics

## Database Discovery

Inspect:
- database kind and version
- schemas and tables
- primary keys and foreign keys
- created or updated timestamps
- soft-delete patterns
- row counts and change volumes
- CDC capability

Infer:
- source entities
- lifecycle transitions
- polling, CDC, or trigger strategy
- idempotency keys
- event ordering requirements

## File Discovery

Inspect:
- file format and encoding
- field layout and schema shape
- filename pattern and directory layout
- arrival cadence and batch windows
- archive, retry, and quarantine behavior

Infer:
- file ingestion strategy
- idempotency key
- record versus batch event boundary
- schema evolution risk

## MQTT and Broker Discovery

Inspect:
- broker type and version
- topic namespace
- qos and retained-message behavior
- payload format
- authentication and tls mode

Infer:
- subscriber pattern
- ordering expectations
- replay behavior
- topic to event mapping

## Queue and Stream Discovery

Inspect:
- queue or topic names
- ack, nack, or commit semantics
- dead-letter path
- replay and retention behavior
- partition or ordering model

Infer:
- consumer bridge pattern
- redelivery strategy
- poison message handling
- idempotency and offset strategy

## SFTP, FTP, and Object Storage Discovery

Inspect:
- host, bucket, or share layout
- directory or prefix pattern
- file arrival behavior
- archive and delete rules
- authentication model

Infer:
- polling cadence
- watermark strategy
- duplicate prevention strategy
- source-to-event batch policy

## Existing Connector Reuse

Search for:
- existing micro-integrations
- reusable adapters
- polling or CDC templates
- schema mappers
- prior generated runs for similar domains

Decision order:
1. reuse as-is
2. adapt with minimal changes
3. generate new

## Output Contract

Discovery must produce:
- source summary
- source mode and adapter type
- chosen connector pattern
- risk notes
- proposed event set
- proposed deployment pattern

## Guardrails

- Use read-only credentials first.
- Do not mutate source systems during discovery.
- Do not guess schema semantics when the source can be inspected directly.
- Flag unclear ownership, missing timestamps, or poor CDC support as risks.
- Flag weak delivery guarantees, replay ambiguity, or file duplication risk as risks.
