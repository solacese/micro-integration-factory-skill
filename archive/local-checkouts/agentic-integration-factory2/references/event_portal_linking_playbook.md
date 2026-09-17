# Event Portal Linking Playbook

Use this playbook when the goal is to make an Event Portal application actually usable in Designer instead of leaving it as a shell.

## Why Applications Look Empty

An application can exist in Event Portal and still look incomplete if only the top-level Application was created.

The missing pieces are usually:

- application version
- schema versions
- event versions
- produced-event links from the application version

## The Minimum Working Graph

Build this graph in order:

1. `applicationDomain`
2. `application`
3. `applicationVersion`
4. `schema`
5. `schemaVersion`
6. `event`
7. `eventVersion`
8. `applicationVersion.declaredProducedEventVersionIds`

## Practical Reconcile Flow

### 1. Reconcile the domain

- lookup by exact domain name
- create only if it does not already exist

### 2. Reconcile the application

- lookup by exact application name
- scope it to the resolved domain
- create only if missing

### 3. Reconcile the application version

- match on `applicationId + version`
- create a real description and state
- keep one clean version baseline such as `0.1.0` if none exists yet

### 4. Reconcile schemas

- create top-level schemas by canonical schema name
- use `jsonSchema` and `json` content type for JSON payloads

### 5. Reconcile schema versions

- create schema versions with actual schema content, not placeholders
- store the schema content as a string payload when required by the API
- match on `schemaId + version`

### 6. Reconcile events

- create top-level events by canonical event name
- scope them to the resolved domain

### 7. Reconcile event versions

- match on `eventId + version`
- link each event version to the correct `schemaVersionId`
- attach the delivery descriptor so the topic address is explicit

### 8. Link the application version

- collect all produced event version IDs for the producing application version
- patch the application version with `declaredProducedEventVersionIds`

This final patch is what makes the Application show a meaningful event flow in Designer.

## Data You Should Persist

For every artifact and version, persist:

- local run ID
- artifact type
- artifact name
- Event Portal external ID
- version
- topic name
- schema name
- status
- request payload
- response payload

## Validation Checklist

Before declaring success, verify:

- the application version exists
- the application version description is populated
- the produced event version list is not empty
- each produced event version references a schema version
- each event version has a Solace topic delivery descriptor

## Design Note

The goal is not just “push some artifacts into Event Portal.”

The goal is to publish a clean design model that another engineer can discover, understand, and trust:

- what the integration is
- what it publishes
- what schemas it uses
- how those events are versioned
- which topics carry them
