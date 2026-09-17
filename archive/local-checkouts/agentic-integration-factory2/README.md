# Agentic Integration Factory

Self-contained starter repo for preparing and later executing source-to-Solace micro-integrations.

This checkout is prepared for two future end-to-end runs:

- Stripe webhook ingress from `samples/openapi/stripe-webhook-demo.yaml`
- PostgreSQL `public.products` discovery and polling using the existing root `.env`

The factory itself is runnable now. The two source-specific micro-integrations are intentionally not generated or deployed until a later execution request.

## What Is Included

- a runnable control-plane app in `apps/`
- an agent skill and lifecycle runbook in `SKILL.md` and `create_micro_integrations.md`
- bundled Solace MDK generation templates in `templates/`
- prepared demo bundles in `demo/`
- bundled sample inputs in `samples/`
- EC2, ECR, Solace, and Event Portal plumbing in `apps/api` and `infra/`
- preflight validation in `scripts/preflight.py`

## Start Here

1. Keep the current root `.env`, or create one from `.env.example`.
2. Optionally activate a demo bundle:

```bash
./scripts/use_demo_env.sh openapi
./scripts/use_demo_env.sh postgres
./scripts/use_demo_env.sh hybrid
```

The activation script substitutes this repo's absolute path and preserves any non-empty secret or infrastructure values already present in the current root `.env`.

3. Bootstrap the repo:

```bash
make bootstrap
```

4. Validate the active env:

```bash
make preflight
```

5. Start the local factory:

```bash
npm run dev
```

6. Build both prepared micro-integrations locally without deployment:

```bash
make hybrid-validate
```

This activates the hybrid demo env, generates the Stripe and PostgreSQL Java workspaces, validates
both with Maven, writes a shared batch summary under `generated-runs/`, and skips image build,
deployment, Solace live verification, and Event Portal sync.

7. When you are ready for a later live run, use the prepared prompts under `demo/prompts/`.

## Hybrid Run Modes

Use the hybrid runner directly from `apps/api` when you need a specific scope:

```bash
uv run python -m spec2event.one_shot_hybrid --mode generate
uv run python -m spec2event.one_shot_hybrid --mode validate
uv run python -m spec2event.one_shot_hybrid --mode full
```

- `generate`
  - generate both prepared runtimes only
- `validate`
  - build both micro-integrations through local Maven validation
- `full`
  - preserve the original deploy-oriented hybrid flow

## Prepared Demo Bundles

- `demo/env/openapi.env`
  - Stripe webhook sample, offline/mockable ingress story
- `demo/env/postgres.env`
  - PostgreSQL `public.products` source story
- `demo/env/hybrid.env`
  - optional wrapper for running both prepared source paths from one factory
- `demo/prompts/openapi_ec2_event_portal.md`
  - Stripe webhook to EC2 to Event Portal prompt
- `demo/prompts/postgres_ec2_event_portal.md`
  - PostgreSQL to EC2 to Event Portal prompt
- `demo/prompts/openapi_postgres_ec2_event_portal.md`
  - combined factory prompt for later orchestration

## Main Folders

- `apps/api`
  - FastAPI orchestrator, generation pipeline, deployment adapters, and Event Portal sync
- `apps/web`
  - Next.js UI for uploads, runs, artifacts, and settings
- `packages/shared`
  - shared frontend and backend DTOs
- `templates/`
  - MDK and Helm templates for REST, webhook, connector, and database paths
- `samples/`
  - bundled Stripe webhook and generic OpenAPI examples
- `references/`
  - source discovery, deployment, and governance notes

## Prepared Future Targets

### Stripe

- primary input: `samples/openapi/stripe-webhook-demo.yaml`
- runtime pattern: webhook ingress
- validation pattern: local fixture invocation, not live Stripe tenant discovery
- live Stripe secrets remain optional until a real webhook verification run is requested

### PostgreSQL

- primary source: `public.products`
- discovery notes: `references/postgres_demo_source_notes.md`
- default strategy: initial snapshot plus incremental polling on `updated_at`
- the current root `.env` remains the source of truth for the real PostgreSQL connection details

## Minimal Agent Prompt

```text
Use this repository as your skill and execution guide.

Read SKILL.md first, then create_micro_integrations.md.
Use the active .env file in the repo as the configuration contract.
Prefer the bundled implementation in apps/, templates/, and infra/ instead of rebuilding the control plane from scratch.

For this repository, do not prepare a second control-plane app.
Use the prepared Stripe webhook sample and PostgreSQL products source as the primary future targets.

Only generate the source-specific micro-integrations when explicitly requested.
```

## Notes

- Use `.env.example` as the base configuration template.
- `samples/openapi/stripe-webhook-demo.yaml` is the primary API-first prepared sample.
- `samples/openapi/petstore.yaml` remains bundled as a generic reference sample.
- `make preflight` is the fastest way to see which prerequisites are already satisfied and which still block a live EC2 or Event Portal run.
