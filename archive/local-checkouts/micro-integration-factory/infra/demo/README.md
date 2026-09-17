# Demo Bundles

Prepared demo bundles for the fastest paths through the factory.

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

That copies the selected demo env into the active root `.env`.
