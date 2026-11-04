# MI Factory

Describe an integration. Confirm the API and transport. Download **Java**, **Go**, and one **shared YAML**.

[Open MI Factory](https://solacese.github.io/micro-integration-factory-skill/demo.html)

The dark IDE-style page keeps chat on the left and status, measured performance, and downloads on the right. Square edges, three normal user actions, at most five conversational turns:

1. **Describe** the input, output and intended service.
2. **Confirm** the official API documentation, library and protocol proposal. Java uses the Solace MI SDK dependency platform over SMF. The agent chooses Go SMF or AMQP based on the required capabilities; AMQP is not mandatory.
3. **Download** after **both generated projects** build, pass their contract examples, and pass a real **1,000 messages/s** delivery test. Java is green, Go blue, shared configuration grey.

Compilation and performance testing take several minutes. Downloads stay locked if either runtime fails. The advisor researches primary sources before generation; its confirmed API plan and source provenance are recorded in generation.json. Native source triggers such as CDC require a real upstream connector; a payload processor is not silently presented as a complete source connector.

## Install an MI

Docker with Compose is sufficient. Unzip either runtime, then:

```bash
./scripts/install.sh --demo
./scripts/smoke.sh --demo
```

This starts an isolated local broker and verifies correlated output bytes and every expected destination. Demo credentials and Stripe signatures are synthetic. It does not contact your Stripe or Salesforce account.

For your broker, complete **config/mi-config.yaml** and run:

```bash
./scripts/install.sh
./scripts/smoke.sh
```

The grey YAML download is byte-identical to the file included in both ZIPs. Fill it once and copy it into either project. It holds SMF/AMQP endpoints, VPN, username/password, topics, webhook signing secret and declared external API credentials. Use the AMQP endpoint for the selected VPN; its port or TLS virtual hostname selects that VPN. Keep completed configuration private.

The editable business logic is **Core.java** or **core.go**. The surrounding runtime supplies ingress, output acknowledgements, bounded concurrency, health, installation and tests. Go AMQP is a portable static binary. Go SMF uses the official Solace Go API and its native CGO library, packaged in Docker. Java uses Java 17, Solace MDK 4.3.11, Spring Boot 4 and the native Solace JCSMP API. Both support raw bytes and declared JSON Schema, XML/XSD, Avro or Protobuf logic; actual format coverage depends on the generated core and its tests.

Stripe projects verify raw-body HMAC signatures with a five-minute window, use HTTP-only ingress, and test fan-out with signed fixtures. Their README explains Stripe CLI and deployed HTTPS setup. Retries can produce duplicates; fan-out is not atomic. Deduplicate by source event ID when needed.

## What performance results mean

The private worker builds and executes the **actual generated cores**, not a previously tested template. Each runtime runs separately with a 2 CPU limit against an isolated broker (4 CPU), with a separate 2 CPU load generator, after ten seconds of warmup. It offers 1,020 inputs/s for ten seconds so the measured end-to-end delivery rate must remain at least 1,000/s even after tail drain. Every expected output topic and output bytes are checked; missing messages, duplicate routes or errors fail the gate.

The page shows achieved rate, peak one-second rate, p95/p99 latency and peak sampled memory for Java and Go. Each ZIP includes **validation.json**, **benchmark.csv**, and verification states in **generation.json**. This fixed-load qualification is not maximum capacity, a long soak, live vendor capacity, production readiness or exactly-once proof. Required external API credentials/mocks must be available for tests; unsupported or unverified code remains locked. Changes to a core, its dependencies or configuration require fresh testing.

## Use Claude Code

Keep the existing AI Core provider setup:

```bash
python3 scripts/install-claude-skill.py
mi-factory "Listen to signed Stripe webhooks and route customer transactions to Solace topics"
```

Or run `./mi "Build my integration"`. The installer updates `/build-mi` and the launcher while preserving provider authentication and permission settings. The [workflow](docs/agent/core-java-workflow.md) requires researched APIs, an appropriate transport, equivalent cores, and real tests before delivery.

Package and qualify a supplied spec locally:

```bash
uv sync --project apps/api
apps/api/.venv/bin/python scripts/create-mi.py SPEC.json --both --validate --output ./output
```

Without `--validate`, CLI packaging is explicitly unverified and generation.json records not_run. Samples are in apps/api/resources/samples/core-java. Do not treat a source ZIP as runtime evidence.

## Deploy the factory

The browser receives no AI Core credentials. The Lambda advisor uses Secrets Manager; the isolated build worker receives no AI credentials. Private S3 artifacts expire after one day, downloads use short-lived signed URLs, and global/per-client budgets bound public usage. Code executes inside unprivileged containers without the worker Docker socket or AWS variables; metadata/private host networks are blocked.

```bash
PYTHONPATH=apps/api/src apps/api/.venv/bin/python infra/advisor/deploy.py \
  --ai-core-env /private/path/ai-core.env
```

The script provisions the Lambda advisor, private validation bucket and bounded CodeBuild worker, updates IAM for those resources, and writes docs/demo-config.json. GitHub Pages publishes docs/ when main is pushed. The worker is limited to one concurrent job, fifteen minutes per build and twenty submitted jobs per day. Build/benchmark time is additional to AI generation.

For local API development, export the [server credential fields](infra/advisor/.env.example), VALIDATION_BUCKET and VALIDATION_PROJECT, then run `PYTHONPATH=src uv run uvicorn spec2event.advisor_app:app --host 127.0.0.1 --port 8087` in apps/api. Point docs/demo-config.json at it and serve docs/ on port 8086; restore the deployed URL before publishing. An unconfigured worker fails closed.

## Verify repository changes

```bash
cd apps/api
uv sync --group dev
PYTHONPATH=src uv run pytest -q
```

Use Java 17 and Maven for generated-project compilation tests. Provider mocks and packaging tests are separate from actual broker and cloud qualification. CI exercises fresh Java and Go installations. The historical control plane remains in apps/web and archive/; it is not the public factory and its former EC2 deployment stays retired.
