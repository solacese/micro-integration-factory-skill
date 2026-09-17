---
name: agentic-integration-factory
description: Use when asked to take over the full lifecycle of a micro-integration from OpenAPI, database credentials, or existing systems: discover the source, find reusable connectors, derive canonical events, generate a Solace MDK integration, validate it, deploy it to EC2 or Kubernetes, register events and schemas in Solace Event Portal, and operate the integration end to end.
---

# Agentic Integration Factory

Use this skill when the user wants an agent to own the micro-integration lifecycle instead of only generating code.

## First Moves

1. Read [create_micro_integrations.md](create_micro_integrations.md).
2. Use [.env.example](../../.env.example) as the base configuration contract.
3. If `apps/` and `infra/` are present in this repo, treat them as the primary runnable factory implementation and adapt them before creating anything from scratch.
4. Load only the references needed for the current source and target:
   - Source discovery: [references/source_discovery.md](references/source_discovery.md)
   - Source adapter matrix: [references/source_adapter_matrix.md](references/source_adapter_matrix.md)
   - Lifecycle execution: [references/lifecycle_pipeline.md](references/lifecycle_pipeline.md)
   - Deployment and HA: [references/deployment_and_ha.md](references/deployment_and_ha.md)
   - Event Portal, schemas, and SerDes: [references/event_portal_and_serdes.md](references/event_portal_and_serdes.md)
   - Event Portal linking order and reconcile details: [references/event_portal_linking_playbook.md](references/event_portal_linking_playbook.md)

## Bundled Runtime

When this repository includes:

- `apps/api` (includes `resources/templates/`, `resources/samples/`, `resources/mdk-reference/`)
- `apps/web`
- `packages/shared`
- `infra/docker`

you should use that bundled implementation as the default execution path for the factory itself.
Only generate new micro-integrations for source-specific runtimes, not a second control-plane application.

## Demo Inputs

Prepared demo bundles live under:

- `infra/demo/env/`
- `infra/demo/prompts/`
- `apps/api/resources/samples/`

If one of those demo bundles is being used, activate it into the root `.env` first or treat the active `.env` as authoritative.

## Non-Negotiables

- Start with read-only discovery credentials when possible.
- Prefer connector reuse before generating a new connector.
- Treat OpenAPI, schemas, brokers, queues, and file layouts as source contracts.
- Generate deterministic artifacts first; AI refinement is secondary.
- Do not deploy without validation and test evidence.
- Keep runtime transport on Solace PubSub+ and design-time governance in Event Portal.
- Never leak secrets to browser logs, generated docs, or prompts.
- Produce an audit trail for every run.

## Minimum Output Set

- Source discovery report
- Integration design summary
- Canonical event model
- Generated micro-integration project
- Validation and test evidence
- Deployment metadata
- Event Portal sync summary
- Operational runbook and follow-up actions
- Delivery documentation for operators and consumers
