# Agentic Integration Factory

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Tests](https://github.com/solacese/agentic-integration-factory/actions/workflows/test.yml/badge.svg)](https://github.com/solacese/agentic-integration-factory/actions/workflows/test.yml)
[![Python](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/downloads/)
[![Code style: ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

Open-source starter repo for an agent-driven micro-integration factory:

`discover -> design -> generate -> validate -> deploy -> govern`

It turns **any source** — OpenAPI specs, JSON Schemas, database credentials, or custom inputs — into a production-ready **Solace MDK micro-integration** with canonical event models, workflow routing, and Event Portal governance.

## Key Capabilities

- **Source-agnostic ingestion** — pluggable source adapters handle parsing, summarization, and canonicalization for each input type
- **Real Solace MDK output** — generated projects use the `micro-integration-build-parent`, pre-created bindings, workflow routing, and `BindingCapabilitiesFactory` beans (based on Solace MDK Samples)
- **Multiple ingress patterns** — REST controllers, polling consumers, or event subscribers depending on the source type
- **Full lifecycle** — generation, build, deploy, test, Event Portal sync, and AI refinement in one pipeline
- **Agent-native** — comes with a skill definition and lifecycle runbook for autonomous operation

## Connector Matrix

| Connector | Direction | Input Format | Ingress Pattern | Streaming |
|-----------|-----------|-------------|-----------------|-----------|
| **OpenAPI** | Source | YAML/JSON spec | REST controller | - |
| **JSON Schema** | Source | `.schema.json` file | REST controller (CRUD) | - |
| **Database (CDC)** | Source | Connection spec JSON | Event subscriber | Yes (log-based CDC) |
| **Kafka** | Source | Broker spec JSON | Event subscriber | Yes (partitioned) |
| **Webhook** | Source | Endpoint spec JSON | REST controller | - |
| **REST Sink** | Target | Canonical model | Solace consumer | - |
| **Generic Target** | Target | Canonical model | Solace consumer | - |
| **Integration Spec** | Both | Declarative JSON | Auto-detected | Configurable |

### Transform Engines

| Engine | Description | Artifacts Generated |
|--------|-------------|-------------------|
| **Passthrough** | No transformation (default) | `PassthroughTransform.java` |
| **Field Mapping** | Declarative rename/select/flatten | `FieldMappingTransform.java` |
| **JOLT** | JSON-to-JSON transformation | `JoltTransform.java` + `jolt-spec.json` |
| **DataWeave** | MuleSoft DataWeave language | `DataWeaveTransform.java` + `transform.dwl` |
| **Scripting** | JavaScript/Groovy/SpEL | `ScriptTransform.java` + `transform-script.js` |
| **Custom Java** | User-implemented Function bean | `CustomTransform.java` |

### Adding a New Connector or Transform

```bash
# Scaffold a new connector
make new-connector NAME=mqtt DIRECTION=source

# Scaffold a new transform engine
make new-transform NAME=xml_to_json
```

Adding a new source type requires implementing three methods (`parse`, `summarize`, `canonicalize`) in a `SourceAdapter` subclass. Adding a renderer or transform requires no edits to the generator or pipeline; they are registry-driven.

## Start Here

1. Pick a demo mode:

```bash
./infra/scripts/use_demo_env.sh openapi
./infra/scripts/use_demo_env.sh postgres
./infra/scripts/use_demo_env.sh hybrid
```

2. Bootstrap the repo:

```bash
make bootstrap
```

3. Validate the active env:

```bash
make preflight
```

4. Start the local factory:

```bash
npm run dev
```

5. Or launch the public EC2 control plane:

```bash
make demo-ec2-up
```

## What Gets Generated

Every run produces a complete Solace MDK micro-integration project:

```
workspace/
├── pom.xml                          # MDK build parent (3.0.6)
├── Dockerfile                       # Multi-stage build with external config support
├── config/application-runtime.yml   # Workflow → destination mappings
├── src/main/resources/
│   └── application.yml              # MDK internal config (20 bindings, workflows, Solace defaults)
├── src/main/java/.../
│   ├── MicroIntegrationApplication.java           # Spring Boot + MDK bean declarations
│   ├── binding/
│   │   ├── SourceConsumerBindingCapabilitiesFactory.java  # Consumer ack mode
│   │   └── SourceProducerBindingCapabilitiesFactory.java  # Producer ack mode
│   ├── api/
│   │   └── GeneratedApiController.java            # REST ingress (when applicable)
│   └── service/
│       ├── CanonicalEventService.java             # Operation → event mapping
│       └── SolacePublisherService.java            # Solace StreamBridge publishing
├── helm/                            # Kubernetes Helm chart
└── scripts/demo-curls.sh            # Test fixtures
```

## Demo Bundles

All prepared demo inputs live in [infra/demo](infra/demo):

- OpenAPI demo env: [infra/demo/env/openapi.env](infra/demo/env/openapi.env)
- PostgreSQL demo env: [infra/demo/env/postgres.env](infra/demo/env/postgres.env)
- Hybrid demo env: [infra/demo/env/hybrid.env](infra/demo/env/hybrid.env)
- OpenAPI prompt: [infra/demo/prompts/openapi_ec2_event_portal.md](infra/demo/prompts/openapi_ec2_event_portal.md)
- PostgreSQL prompt: [infra/demo/prompts/postgres_ec2_event_portal.md](infra/demo/prompts/postgres_ec2_event_portal.md)
- Hybrid prompt: [infra/demo/prompts/openapi_postgres_ec2_event_portal.md](infra/demo/prompts/openapi_postgres_ec2_event_portal.md)

The helper script copies one of those env bundles into the active root `.env`.

## Sample Inputs

- [petstore.yaml](apps/api/resources/samples/openapi/petstore.yaml) - simple Petstore API
- [stripe-webhook-demo.yaml](apps/api/resources/samples/openapi/stripe-webhook-demo.yaml) - Stripe webhook integration
- [order.schema.json](apps/api/resources/samples/json_schema/order.schema.json) - e-commerce order schema
- [orders-cdc.json](apps/api/resources/samples/database/orders-cdc.json) - PostgreSQL CDC source
- [order-events.json](apps/api/resources/samples/kafka/order-events.json) - Kafka streaming source
- [payment-webhooks.json](apps/api/resources/samples/webhook/payment-webhooks.json) - generic webhook source
- [kafka-to-rest.json](apps/api/resources/samples/integration_spec/kafka-to-rest.json) - declarative integration spec (bidirectional)

## Main Folders

- [SKILL.md](docs/agent/SKILL.md)
  — agent entry point
- [create_micro_integrations.md](docs/agent/create_micro_integrations.md)
  — lifecycle runbook
- [docs/agent/references](docs/agent/references)
  — deeper design and Event Portal guidance
- [apps/api](apps/api)
  — FastAPI orchestrator, source adapters, and deployment adapters
- [apps/web](apps/web)
  — Next.js UI with source type selector
- [apps/api/resources/templates](apps/api/resources/templates)
  — Solace MDK and Helm generation templates
- [apps/api/resources/mdk-reference](apps/api/resources/mdk-reference)
  — local MDK baseline (from Solace MDK Samples)
- [apps/api/resources/samples](apps/api/resources/samples)
  — bundled source inputs (OpenAPI, JSON Schema)

## Architecture

```
Source Input (OpenAPI, JSON Schema, DB, MQTT, ...)
  │
  ▼
Source Adapter  ─── parse() → summarize() → canonicalize()
  │
  ▼
Canonical Event Model  (operations, topics, schemas, test fixtures)
  │
  ▼
Generator Service  ─── Jinja2 templates → Solace MDK project
  │                     (workflows, bindings, capabilities factories)
  ▼
Build Pipeline  ─── Docker build (local or ECR)
  │
  ▼
Deploy Pipeline  ─── Docker / EC2 / Kubernetes
  │
  ▼
Event Portal Sync  ─── domains, apps, schemas, events
```

## Minimal Agent Prompt

```text
Use this repository as your skill and execution guide.

Read docs/agent/SKILL.md first, then docs/agent/create_micro_integrations.md.
Use the active .env file in the repo as the configuration contract.
Prefer the bundled implementation in apps/ and infra/ instead of rebuilding the control plane from scratch.

Take over the micro-integration lifecycle:
- discover the source
- design the canonical events
- generate or adapt the micro-integration
- validate and test it
- deploy it
- register and link it in Solace Event Portal
- write the operator and consumer notes

The run is only complete when runtime, governance, and documentation are all in place.
```

## Notes

- Use [.env.example](.env.example) as the base config template.
- Use [petstore.yaml](apps/api/resources/samples/openapi/petstore.yaml) for the simplest API-first demo.
- Use [order.schema.json](apps/api/resources/samples/json_schema/order.schema.json) for a schema-first demo.
