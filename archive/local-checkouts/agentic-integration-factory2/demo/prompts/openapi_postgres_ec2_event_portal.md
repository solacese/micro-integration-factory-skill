# OpenAPI Plus PostgreSQL to EC2 to Event Portal Prompt

Use this as the default prompt when the request is effectively: `build 2 micro integrations for stripe and postgre sql`.

Use this prompt when you want the stronger hybrid version of the factory to behave like a complete integration program, not a light demo:

- one OpenAPI contract
- one PostgreSQL source
- two generated Java micro-integrations by default
- one shared governance story
- broad event coverage on both sides
- executable SerDes contracts and Event Portal documentation before deployment
- producer and consumer verification, not producer-only verification
- deployment to temporary EC2
- Solace event publication

## Source Notes

This hybrid run uses:

- OpenAPI contract: `samples/openapi/stripe-webhook-demo.yaml`
- PostgreSQL database: `defaultdb`
- schema: `public`
- best database table for the source story: `products`

Reference notes:

- `references/postgres_demo_source_notes.md`

The goal is not to mash unlike sources together blindly.
The goal is to show that different source technologies can be prepared, governed, implemented, and operated from one coherent factory.

## Prompt

```text
Use this repository as your skill and execution guide.

Read SKILL.md first, then create_micro_integrations.md.
Activate `demo/env/hybrid.env` into the root `.env`, then use the active `.env` in this repo as the runtime and infrastructure configuration contract.

For this run, treat the hybrid path as a complete multi-source micro-integration design and implementation task:
- source mode: multi
- source types: OpenAPI plus PostgreSQL
- OpenAPI contract: samples/openapi/stripe-webhook-demo.yaml
- database: defaultdb
- schema: public
- preferred database source table: products
- deployment target: EC2
- event transport: Solace PubSub+
- governance target: Solace Event Portal

Your job is to take over the full lifecycle of the integration design and complete it end to end.

Do this in order:
1. inspect the OpenAPI contract in detail
2. inspect the PostgreSQL schema in detail
3. confirm that public.products is the best primary database source for this run
4. keep the OpenAPI side focused on Stripe webhook ingress and the database side focused on product lifecycle events
5. decide what should be shared across the two sources:
   - governance structure
   - topic naming conventions
   - schema conventions
   - SerDes conventions
   - compatibility policy
   - message header contract
   - observability conventions
6. generate two separate micro-integrations unless there is a strong and clearly stated operational reason to combine them
7. derive broad canonical event models for both sources
8. on the OpenAPI side, target at least 15 Stripe event versions across multiple webhook families relevant to the payments lifecycle, including payment_intent, charge, refund, invoice, checkout.session, and dispute unless the source contract clearly rules one out
9. on the PostgreSQL side, target at least 12 product-oriented event versions derived from row-state transitions, per-column changes, and newly discovered business columns
10. treat every detected PostgreSQL update as an event, not just inserts or generic upserts
11. each changed row in the incremental path must produce at least one row-level event, and column-specific events when tracked business columns change
12. if new source columns are discovered during introspection, treat that as schema evolution:
   - extend the canonical model deliberately
   - add or version the relevant schemas in Event Portal
   - decide whether the column needs its own changed event or inclusion in a structured changed-fields model
13. do not collapse either side back to a tiny default event set
14. define the shared governance structure, schema set, topic taxonomy, Event Portal design graph, compatibility policy, message header contract, and SerDes strategy before build and deployment
15. document and reconcile those Event Portal artifacts before you build or deploy anything:
   - application domain
   - source-specific applications
   - application versions
   - schemas
   - schema versions
   - events
   - event versions
   - produced-event links
16. treat SerDes as executable contract design, not prose only
17. document SerDes for every event family in Event Portal metadata and in the run output:
   - schema format
   - serializer family
   - deserializer family
   - content type
   - required message headers:
     - content-type
     - event-type
     - schema-name
     - schema-version
     - source-system
     - source-record-id
     - correlation-id
     - occurred-at
   - schema subject or artifact naming convention
   - schema versioning policy
   - registry coordinates if an external registry exists, otherwise explicit Event Portal-only designation
18. generate or adapt the Solace MDK Java runtimes
19. make the Java implementation substantial on both sides:
   - richer controllers and webhook handling on the OpenAPI side
   - richer poller and transition logic on the database side
   - explicit per-event mapping logic in Java
   - explicit payload builders and header population
   - service-layer orchestration
   - no tiny catch-all mapper
20. validate and test both Java runtimes locally
21. include Java unit, schema contract, and happy-path verification for mapping, header population, schema compliance, and publish behavior
22. add a small consumer-side verification path that subscribes through Solace and proves representative messages from both runtimes can be deserialized and validated against the declared schemas
23. include negative-path and operational checks:
   - malformed webhook payload
   - unknown Stripe event type
   - duplicate Stripe delivery id
   - empty poll cycle
   - repeated poll cycle with no change
   - bad row data or unexpected nulls
   - publish retry or temporary broker failure
24. make idempotency explicit in the design and in the runtime behavior:
   - repeated Stripe deliveries must not create uncontrolled duplicate publishes
   - repeated PostgreSQL poll cycles must not create uncontrolled duplicate publishes for unchanged rows
25. only after governance is documented and the Java baselines are valid, build the image or images
26. deploy the runtimes to temporary EC2 instances
27. verify that:
   - the OpenAPI-oriented integration can publish the expected Stripe event set
   - the database-oriented integration can read from PostgreSQL and publish the expected product event set
   - published messages carry the expected headers, schema metadata, and compatibility information
   - the consumer-side path can deserialize representative messages from both sources
28. write operator and consumer documentation with explicit Java/runtime notes

Keep the hybrid story focused on a complete source estate:
- two source technologies
- two separate Java runtimes
- one coherent governed design story
- broad event coverage on both sides
- governance documented before deployment
- one credible producer-to-consumer proof path

Prefer separate deployable micro-integrations unless combining them materially improves the architecture.
Prefer a read-only database strategy unless a write is explicitly required for the run.
Do not require a live Stripe account; use mockable webhook fixtures for verification.
If you need to demonstrate a live database change, explain the safest possible mutation before doing it.

Do not stop at code generation.
The run is only complete when governance, Java implementation, runtime verification, and documentation are all in place.

Return these outputs:
- source summary for both sources
- selected database tables and why
- chosen API and database ingestion strategy
- Java implementation summary for both runtimes
- event inventory with counts for both runtimes
- schema and SerDes matrix
- header contract and compatibility policy summary
- Event Portal graph summary produced before deployment
- whether you generated one or multiple micro-integrations and why
- generated artifact path or paths
- deploy target and EC2 details
- runtime URL or URLs
- sample published events from both sources
- consumer verification summary
- negative-path and idempotency summary
- runtime verification summary after deployment
- any blocking issue that would prevent a credible showcase
```

## Implementation Goal

The audience should be able to understand this as a serious governed integration program:

1. point the agent at a real OpenAPI contract and a real PostgreSQL database
2. watch it discover both without forcing them into one shallow model
3. watch it define many events, schemas, SerDes conventions, headers, and compatibility rules before deployment
4. watch it generate the needed Java runtimes
5. watch it validate those runtimes locally
6. watch it prove producer and consumer compatibility from both sources
7. watch it deploy them to EC2
8. see events flow through Solace from both sources
9. see the related governed assets in Event Portal

## Important Note

If the Event Portal token in the active `.env` is rejected, refresh it before running this prompt so the governance-first part succeeds before build and deployment.
