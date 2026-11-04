# MI Factory

Describe the behavior, build **Core.java**, and download **MI v1**.

[Open the factory](https://solacese.github.io/micro-integration-factory-skill/demo.html)

The dark, minimal website has chat on the left, build status on the right, and one download button. The advisor researches primary documentation and uses SAP AI Core to write the core Java business logic. A deterministic packager adds the standard runtime rather than asking the model to invent a framework.

## Use Claude Code

With Claude Code already connected to your AI Core provider:

```bash
./mi "Build an MI that uppercases the name field in JSON and rejects a missing name"
```

Or install the personal shortcut once:

```bash
python3 scripts/install-claude-skill.py
mi-factory "Build my integration"
```

The installer adds `/build-mi` and the `mi-factory` launcher. It preserves existing provider, authentication, and permission settings. [The workflow](docs/agent/core-java-workflow.md) tells Claude to research real APIs, package the core, run contract checks, and verify an actual broker round trip when a runtime test is requested.

## What the download contains

- **Core.java** — the one editable business-logic file.
- A fixed Java 17 runtime using the Solace MDK 4.3.11 dependency platform, Spring Boot 4, Jackson 3, and Spring Cloud Stream.
- Solace topic ingress/egress, HTTP `/ingest`, correlation IDs, failure propagation, health, and a separate error queue.
- Docker installation, executable input/output contract examples, and a real broker smoke test.
- `generation.json` with assumptions, fetched source provenance, and separate verification states.

After unzipping, run:

```bash
./scripts/install.sh --demo
./scripts/smoke.sh --demo
```

Docker and Compose are sufficient; host Java and Maven are optional. For an existing broker, run `install.sh` once, edit the generated `.env`, and run it again. The generated README includes host/container addressing and stopping instructions.

The smoke test publishes a unique input message, receives the correlated result on the output topic, and compares the bytes with the contract. A generated zip is **not** reported as compiled, deployed, or tested until those checks run. Native source triggers such as database CDC need a real upstream connector; the advisor must not silently replace them with a stub or payload processor.

## Run or deploy the advisor

The current advisor is independent of the historical PostgreSQL/Redis control plane. Supply SAP AI Core credentials only through the server environment or AWS Secrets Manager. The browser receives no credentials.

```bash
cd apps/api
uv sync
# Export SAP_CLIENT_ID, SAP_CLIENT_SECRET, SAP_AUTH_URL, SAP_API_BASE_URL,
# SAP_RESOURCE_GROUP, AI_CORE_DEPLOYMENT_ID, and AI_CORE_MODEL server-side.
PYTHONPATH=src uv run uvicorn spec2event.advisor_app:app --host 127.0.0.1 --port 8087
```

Set `docs/demo-config.json` to that API's base URL when previewing locally, then serve `docs/` on port 8086. Restore the deployed URL before publishing.

To deploy the small Lambda advisor using a private env file:

```bash
PYTHONPATH=apps/api/src apps/api/.venv/bin/python infra/advisor/deploy.py \
  --ai-core-env /private/path/ai-core.env
```

See [the credential field names](infra/advisor/.env.example). The script packages the backend and runtime templates, stores credentials in Secrets Manager, configures bounded public usage, and writes the endpoint into `docs/demo-config.json`. GitHub Pages publishes `docs/` on a push to `main`.

## Verify changes

```bash
cd apps/api
uv sync --group dev
PYTHONPATH=src uv run pytest -q
```

Use Java 17+ and Maven to enable the generated-project compilation tests. The new tests exercise project packaging, contract execution, AI Core OAuth refresh and tool-call continuity, source provenance, blocked redirects, soft 404s, and truthful build states. Live AI and broker checks are separate from mocked provider tests.

The old full control-plane UI and templates remain in `apps/web`, `apps/api`, and `archive/` for historical use; they are not the public v1 experience. The prior EC2 deployment remains retired. The current public advisor is a separate small deployment.
