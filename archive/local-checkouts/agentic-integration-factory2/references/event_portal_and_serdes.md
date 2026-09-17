# Event Portal and SerDes

Use this file when the integration must be governed cleanly in Solace Event Portal and related schema or SerDes registries.

## Event Portal Scope

Treat Event Portal as the design-time system of record for:

- domains
- applications
- application versions
- events
- event versions
- schemas
- schema versions
- topic addresses
- version relationships

Do not treat Event Portal as the runtime message sink.

## Registration Goal

The objective is not to leave behind isolated artifacts.

The objective is to create a usable design graph that clearly shows:

- which application produces which event versions
- which event versions use which schema versions
- which topic addresses those event versions are published on

## Required Registration Order

1. reconcile the application domain
2. reconcile the producing application
3. reconcile the application version
4. reconcile the schema
5. reconcile the schema version with real schema content
6. reconcile the event
7. reconcile the event version with topic address and schema version
8. patch the application version so it declares the produced event version IDs

If step 8 is missing, the application may exist but still look empty in Event Portal Designer.

## Reconcile Rules

- prefer exact-name lookups for top-level artifacts
- prefer version-aware matching for versioned artifacts
- when filters are weak or ignored by the API, paginate and reconcile deterministically
- prefer idempotent upsert behavior over blind create calls
- capture external IDs for every artifact and version

## Topic and Delivery Modeling

Event versions should carry runtime delivery metadata that matches the actual topic taxonomy.

For Solace topics:

- use `deliveryDescriptor.brokerType = solace`
- use `address.addressType = topic`
- populate `addressLevels` from the canonical topic path

## Schema and SerDes Registry

If a separate schema or SerDes registry exists:

- publish the canonical schema there
- capture registry coordinates and version
- attach those references to the Event Portal sync metadata

Minimum metadata to retain:

- registry type
- subject or artifact name
- schema version
- serializer and deserializer family
- external URL or resource ID

## Versioning Rules

- version events from the start
- version schemas from the start
- prefer additive schema evolution
- create new versions instead of mutating incompatible artifacts
- keep the runtime topic taxonomy and Event Portal topic definitions aligned

## Required Output

Every sync should produce:

- created or updated artifacts
- created or updated versions
- external IDs
- skipped artifacts
- partial artifacts
- manual follow-up payloads where API support is incomplete

## Completion Standard

An Event Portal sync is only complete when the following are true:

- the application version exists
- every produced event has an event version
- every event version references a schema version
- the application version declares the produced event version IDs
- topic addresses align with the runtime configuration
