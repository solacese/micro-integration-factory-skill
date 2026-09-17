# Demo Bundles

Prepared demo bundles for the fastest paths through the factory.

These env bundles are sanitized templates. Activating one of them preserves any
non-empty secret and infrastructure values already present in the current root
`.env`.

## Modes

- `openapi`
  - env: `env/openapi.env`
  - prompt: `prompts/openapi_ec2_event_portal.md`
- `postgres`
  - env: `env/postgres.env`
  - prompt: `prompts/postgres_ec2_event_portal.md`
- `hybrid`
  - env: `env/hybrid.env`
  - prompt: `prompts/openapi_postgres_ec2_event_portal.md`

## Activate

```bash
./scripts/use_demo_env.sh openapi
./scripts/use_demo_env.sh postgres
./scripts/use_demo_env.sh hybrid
```

That writes the selected demo env into `.env.active` and `.env`, while keeping
existing secrets and substituting this repo's absolute path.

## Build Both Prepared Micro-Integrations

Use the hybrid validate path when the goal is to build both prepared micro-integrations without
deployment:

```bash
make hybrid-validate
```

That activates `env/hybrid.env`, generates the Stripe and PostgreSQL runtimes, runs local Maven
validation for both, and writes a shared summary under `generated-runs/`.

If you need to call the runner directly, use:

```bash
cd apps/api
uv run python -m spec2event.one_shot_hybrid --mode validate
```
