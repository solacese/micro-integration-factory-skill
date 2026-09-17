# Source Adapter Matrix

Use this file when the agent must decide how to ingest a source into an event-driven architecture.

## Goal

Choose the narrowest correct adapter pattern for the source instead of forcing every source into an API-first model.

## Supported Source Modes

- `openapi`
- `database`
- `file`
- `mqtt`
- `kafka`
- `amqp`
- `jms`
- `queue`
- `webhook`
- `graphql`
- `grpc`
- `sftp`
- `ftp`
- `object_storage`
- `saas_api`
- `custom`

## Adapter Selection Rules

### OpenAPI or REST API

Use when:

- the source is a synchronous API contract
- the platform needs to expose or consume HTTP operations

Preferred adapter:

- REST ingress
- polling REST client
- webhook receiver when supported

### Database

Use when:

- the source of truth is relational data
- the business events should come from row or entity changes

Preferred adapter:

- CDC first
- polling second
- trigger-based extraction only when necessary

### File

Use when:

- the source is CSV, JSON, XML, Avro, EDI, fixed-width, PLA, or another structured file
- data arrives by drop folder, attachment, batch export, or object storage

Preferred adapter:

- file poller
- object storage listener
- SFTP or FTP fetcher

Key design points:

- file identity and idempotency
- archive or quarantine behavior
- schema evolution for batch payloads

### MQTT

Use when:

- the source emits messages on MQTT topics
- QoS and retained-message behavior matter

Preferred adapter:

- MQTT subscriber bridge

Key design points:

- qos handling
- retained messages
- topic wildcards
- session durability

### Kafka

Use when:

- the source emits messages on Kafka topics
- partitions, offsets, and replay behavior matter

Preferred adapter:

- Kafka consumer bridge

Key design points:

- consumer group strategy
- partition ordering
- offset commits
- dead-letter strategy

### AMQP, JMS, or Queues

Use when:

- the source is queue-based
- the integration needs queue-to-topic or queue-to-event conversion

Preferred adapter:

- queue consumer bridge

Key design points:

- ack or nack semantics
- poison message handling
- redelivery policy

### Webhooks

Use when:

- the external system can call a public endpoint

Preferred adapter:

- webhook ingress

Key design points:

- signature verification
- replay protection
- correlation IDs

### GraphQL or gRPC

Use when:

- the source exposes non-REST service contracts

Preferred adapter:

- GraphQL poller or mutation gateway
- gRPC client or server wrapper

### SaaS APIs

Use when:

- the source is a business SaaS platform with rate limits and auth rules

Preferred adapter:

- polling client
- webhook receiver
- hybrid polling plus webhook pattern

### Custom

Use when:

- the source format or protocol is domain-specific
- no reusable connector exists

Preferred adapter:

- generate a custom adapter, but only after searching for reusable patterns first

## Discovery Questions by Source

Always answer these before generation:

1. what is the source transport?
2. what is the payload shape?
3. what is the delivery or polling model?
4. what defines identity and idempotency?
5. what defines ordering?
6. what defines retries and replay?
7. what event boundaries should be emitted?

## Output Required From Adapter Selection

- chosen source mode
- chosen adapter pattern
- reason for that pattern
- fallback pattern if the preferred one is not viable
- main operational risks
