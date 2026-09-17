# PostgreSQL to EC2 to Event Portal Prompt

Use this prompt when you want a more complete database-driven micro-integration, not a thin polling demo:

- PostgreSQL source
- Java-first generated micro-integration
- richer product event model
- executable SerDes contracts and Event Portal documentation before deployment
- producer and consumer verification, not producer-only verification
- deployment to temporary EC2
- Solace event publication

## Source Notes

This database was validated on 2026-03-19.

Reference notes:

- `references/postgres_demo_source_notes.md`

Useful shape for the run:

- schema: `public`
- strongest table for the source story: `products`
- approximate rows in `public.products`: `1,000,000`
- useful columns:
  - `id`
  - `sku`
  - `name`
  - `category`
  - `price`
  - `stock_quantity`
  - `created_at`
  - `updated_at`

Tables that are less useful for this run:

- `alembic_version`
- `app_states`
- `events`
- `sessions`
- `user_states`
- `products_backup_20260220`

## Prompt

```text
Use this repository as your skill and execution guide.

Read SKILL.md first, then create_micro_integrations.md.
Activate `demo/env/postgres.env` into the root `.env`, then use the active `.env` in this repo as the runtime and infrastructure configuration contract.

For this run, treat the PostgreSQL path as a complete Java micro-integration design and implementation task:
- source mode: PostgreSQL
- database: defaultdb
- schema: public
- preferred source table: products
- deployment target: EC2
- event transport: Solace PubSub+
- governance target: Solace Event Portal

Your job is to take over the full lifecycle of the micro-integration and complete it end to end.

Do this in order:
1. inspect the PostgreSQL schema in detail
2. confirm that public.products is the best primary source for the run
3. choose the source strategy deliberately:
   - initial snapshot plus incremental polling, or
   - a stronger CDC-like pattern if you can justify it with the current environment
4. derive a broad canonical event model for product lifecycle behavior
5. do not stop at a single upserted event; target at least 12 product-oriented event versions derived from row-state transitions, per-column changes, and newly discovered business columns
6. treat every detected update as an event, not just inserts or generic upserts
7. each changed row in the incremental path must produce at least one row-level event, and column-specific events when tracked business columns change
8. explicitly cover per-column or per-transition events for business-relevant fields such as:
   - sku
   - name
   - category
   - price
   - stock_quantity
   - any additional business column discovered during schema inspection
9. if new source columns are discovered during introspection, treat that as schema evolution:
   - extend the canonical model deliberately
   - add or version the relevant schemas in Event Portal
   - decide whether the column needs its own changed event or inclusion in a structured changed-fields model
10. if transitions require prior-state comparison, make that explicit in the design and in the Java implementation plan
11. define the topic taxonomy, schema set, Event Portal design graph, compatibility policy, message header contract, and SerDes strategy before build and deployment
12. document and reconcile those Event Portal artifacts before you build or deploy anything:
   - application domain
   - application
   - application version
   - schemas
   - schema versions
   - events
   - event versions
   - produced-event links
13. treat SerDes as executable contract design, not prose only
14. document SerDes for every event family in Event Portal metadata and in the run output:
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
15. generate or adapt the Solace MDK Java micro-integration
16. make the Java implementation substantial:
   - richer poller logic
   - explicit row-diff or state-transition mapping logic
   - explicit payload builders and header population
   - service-layer orchestration for event selection
   - no single generic mapper that collapses the model back to one event
17. validate and test the Java runtime locally
18. include Java unit, schema contract, and happy-path verification for mapping, header population, schema compliance, and publish behavior
19. add a small consumer-side verification path that subscribes through Solace and proves representative messages can be deserialized and validated against the declared schemas
20. include negative-path and operational checks:
   - empty poll cycle
   - repeated poll cycle with no change
   - duplicate source row state
   - bad row data or unexpected nulls
   - publish retry or temporary broker failure
21. make idempotency explicit in the design and in the runtime behavior; repeated poll cycles must not create uncontrolled duplicate publishes for unchanged rows
22. only after governance is documented and the Java baseline is valid, build the image
23. deploy it to a temporary EC2 instance
24. verify that the integration can read from PostgreSQL and publish the broader product event set to Solace
25. verify that published messages carry the expected headers, schema metadata, and compatibility information
26. verify that the consumer-side path can deserialize representative messages successfully
27. write operator and consumer documentation with explicit Java/runtime notes

Keep the implementation focused on a complete micro-integration:
- one database source
- one clear table
- one Java runtime
- many distinct event versions, not one generic event
- one governed Event Portal design graph documented before deployment
- one credible producer-to-consumer proof path

Prefer a read-only database strategy unless a write is explicitly required for the run.
If you need to demonstrate a live change, explain the safest possible mutation before doing it.

Do not stop at code generation.
The run is only complete when governance, Java implementation, runtime verification, and documentation are all in place.

Return these outputs:
- source summary
- selected tables and why
- chosen polling or CDC strategy
- Java implementation summary
- canonical event inventory with counts
- schema and SerDes matrix
- header contract and compatibility policy summary
- Event Portal graph summary produced before deployment
- generated artifact path
- deploy target and EC2 details
- runtime URL
- sample published events
- consumer verification summary
- negative-path and idempotency summary
- runtime verification summary after deployment
- any blocking issue that would prevent a credible showcase
```

## Implementation Goal

The audience should be able to understand this as a serious Java-based source integration:

1. point the agent at a real PostgreSQL database
2. watch it discover the schema and select the right source table
3. watch it derive many product event families instead of one generic event
4. watch it treat every meaningful update as an event and handle newly discovered columns as schema evolution
5. watch it document schemas, SerDes, headers, and Event Portal relationships before deployment
6. watch it generate and validate meaningful Java code
7. watch it prove producer and consumer compatibility, not only producer publish success
8. watch it deploy to EC2
9. see product events flow on Solace
10. see the corresponding governed assets in Event Portal

## Important Note

If the Event Portal token in the active `.env` is rejected, refresh it before running this prompt so the governance-first part succeeds before build and deployment.
