# PostgreSQL to EC2 to Event Portal Demo Prompt

Use this prompt when you want to film the cleanest database-driven version of the factory:

- PostgreSQL source
- generated micro-integration
- deployment to temporary EC2
- Solace event publication
- Event Portal registration and linking

## Source Notes

This database was validated on 2026-03-19.

Reference notes:

- `docs/agent/references/postgres_demo_source_notes.md`

Useful shape for the demo:

- schema: `public`
- strongest table for the filmed story: `products`
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

Tables that look less useful for the film:

- `alembic_version`
- `app_states`
- `events`
- `sessions`
- `user_states`
- `products_backup_20260220`

## Prompt

```text
Use this repository as your skill and execution guide.

Read docs/agent/SKILL.md first, then docs/agent/create_micro_integrations.md.
Activate `infra/demo/env/postgres.env` into the root `.env`, then use the active `.env` in this repo as the runtime and infrastructure configuration contract.

For this run, keep the path simple and demo-friendly:
- source mode: PostgreSQL
- database: defaultdb
- schema: public
- preferred source table: products
- deployment target: EC2
- event transport: Solace PubSub+
- governance target: Solace Event Portal

Your job is to take over the full lifecycle of the micro-integration and complete it end to end.

Do this in order:
1. inspect the PostgreSQL schema
2. confirm that public.products is the best primary source for the filmed demo
3. derive a canonical event model for product data
4. choose the simplest credible source pattern:
   - watermark-based polling on updated_at, or
   - initial snapshot plus incremental polling
5. generate or adapt the Solace MDK micro-integration
6. validate and test it locally
7. build the image
8. deploy it to a temporary EC2 instance
9. verify that the integration can read from PostgreSQL and publish product events to Solace
10. register and link the resulting application, schemas, events, and versions in Event Portal
11. write concise operator and consumer documentation for the run

Keep the demo focused on the concept:
- one database source
- one clear table
- one generated micro-integration
- one clean deployed runtime
- one clean Event Portal design graph

Prefer a read-only database strategy unless a write is explicitly required for the demo.
If you need to demonstrate a live change, explain the safest possible mutation before doing it.

Do not stop at code generation.
The run is only complete when runtime, governance, and documentation are all in place.

Return these outputs:
- source summary
- selected tables and why
- chosen polling or CDC strategy
- canonical events and topics
- generated artifact path
- deploy target and EC2 details
- runtime URL
- sample published events
- Event Portal artifact summary
- any blocking issue that would prevent filming
```

## Filming Goal

The audience should be able to understand the whole story from one short run:

1. point the agent at a real PostgreSQL database
2. watch the agent discover the schema
3. watch it choose the products table and the ingestion strategy
4. watch it generate and deploy the micro-integration
5. see product events flow on Solace
6. see the corresponding design artifacts appear in Event Portal

## Important Note

If the Event Portal token in the active `.env` is rejected, refresh it before filming so the governance part of the demo succeeds live.
