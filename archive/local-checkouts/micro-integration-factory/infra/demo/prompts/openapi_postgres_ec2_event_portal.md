# OpenAPI Plus PostgreSQL to EC2 to Event Portal Demo Prompt

Use this prompt when you want to film the stronger hybrid version of the factory:

- one OpenAPI contract
- one PostgreSQL source
- two generated micro-integrations or one very clearly justified combined design
- one shared canonical event model
- deployment to temporary EC2
- Solace event publication
- Event Portal registration and linking

## Source Notes

This hybrid demo uses:

- OpenAPI contract: `apps/api/resources/samples/openapi/petstore.yaml`
- PostgreSQL database: `defaultdb`
- schema: `public`
- best database table for the filmed story: `products`

Reference notes:

- `docs/agent/references/postgres_demo_source_notes.md`

The goal is not to mash unlike sources together blindly.
The goal is to show that different source technologies can feed one coherent event-driven architecture.

## Prompt

```text
Use this repository as your skill and execution guide.

Read docs/agent/SKILL.md first, then docs/agent/create_micro_integrations.md.
Activate `infra/demo/env/hybrid.env` into the root `.env`, then use the active `.env` in this repo as the runtime and infrastructure configuration contract.

For this run, keep the path simple and demo-friendly:
- source mode: multi
- source types: OpenAPI plus PostgreSQL
- OpenAPI contract: apps/api/resources/samples/openapi/petstore.yaml
- database: defaultdb
- schema: public
- preferred database source table: products
- deployment target: EC2
- event transport: Solace PubSub+
- governance target: Solace Event Portal

Your job is to take over the full lifecycle of the integration design and complete it end to end.

Do this in order:
1. inspect the OpenAPI contract
2. inspect the PostgreSQL schema
3. confirm that public.products is the best primary database source for the filmed demo
4. identify the shared business-domain story across both inputs
5. derive one canonical event model and one topic taxonomy
6. decide whether to generate:
   - two micro-integrations that share the same event model, or
   - one combined integration only if there is a strong and clearly stated reason
7. generate or adapt the Solace MDK micro-integration runtime or runtimes
8. validate and test them locally
9. build the image or images
10. deploy them to temporary EC2 instances
11. verify that:
   - the API-oriented integration can publish events from the OpenAPI-driven side
   - the database-oriented integration can read from PostgreSQL and publish product events to Solace
12. register and link the resulting application domains, applications, application versions, schemas, schema versions, events, event versions, and produced-event links in Event Portal
13. write concise operator and consumer documentation for the run

Keep the hybrid story focused:
- two source technologies
- one shared event backbone
- one coherent governed design
- one short filmed narrative

Prefer separate deployable micro-integrations unless combining them materially improves the architecture.
Prefer a read-only database strategy unless a write is explicitly required for the demo.
If you need to demonstrate a live database change, explain the safest possible mutation before doing it.

Do not stop at code generation.
The run is only complete when runtime, governance, and documentation are all in place.

Return these outputs:
- source summary for both sources
- selected database tables and why
- chosen API and database ingestion strategy
- canonical events and topics
- whether you generated one or multiple micro-integrations and why
- generated artifact path or paths
- deploy target and EC2 details
- runtime URL or URLs
- sample published events from both sources
- Event Portal artifact summary
- any blocking issue that would prevent filming
```

## Filming Goal

The audience should be able to understand this story in one short run:

1. point the agent at a real OpenAPI contract and a real PostgreSQL database
2. watch it discover both
3. watch it define one canonical event model
4. watch it generate the needed micro-integration runtimes
5. watch it deploy them to EC2
6. see events flow through Solace
7. see the same design appear in Event Portal

## Important Note

If the Event Portal token in the active `.env` is rejected, refresh it before filming so the governance part of the demo succeeds live.
