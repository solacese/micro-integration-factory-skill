# MI Factory

Describe an integration. Check whether it should be built. Confirm the API and transport. Download **Java MDK**, **Go**, one **shared YAML**, and a **test ZIP**.

[Open MI Factory](https://solacese.github.io/micro-integration-factory-skill/demo.html)

The dark IDE-style page keeps chat on the left and status, measured performance, and four downloads on the right. Square edges, three normal user actions, at most five conversational turns:

1. **Describe** the input, output and intended service. The factory checks all 111 downloaded [Solace Integration Hub](https://solace.com/integration-hub/) entries and qualifies the fit before writing code.
2. **Review** the recommendation. Reuse an existing asset when its API, direction and configurable transformations cover the request. For a justified custom gap, confirm the scope, official API, library and protocol together with one Yes. Java uses Solace MDK over SMF; Go uses SMF or AMQP as appropriate.
3. **Download** after **both generated projects** build, pass their contract examples, and pass a real **1,000 messages/s** delivery test. Java MDK is green, Go blue, shared configuration grey, and the test ZIP purple.

Compilation and performance testing take several minutes. Downloads stay locked if either runtime fails. The advisor researches primary sources before generation; its confirmed API plan and source provenance are recorded in generation.json. Native source triggers such as CDC require a real upstream connector; a payload processor is not silently presented as a complete source connector.

The fit check recommends **reuse**, requests an **architecture review**, asks one essential question, or approves a **custom build**. For example, ordinary Salesforce Pub/Sub event movement should use the Salesforce integration, and a plain Kafka bridge should use the broker-integrated bridge. Salesforce REST record CRUD is a different API; a vendor-name match alone does not establish coverage. A custom processor on top of an existing connector requires that upstream prerequisite to be explicitly confirmed.

Hard latency SLOs, input rates above the factory's tested 1,000/s profile, payloads above 1 MiB, strict ordering, cross-system atomicity/exactly-once, or durable workflows need further design and qualification. These are limits of this generated profile and its tests, not claims about all Solace micro-integrations. A reuse or architecture-review decision cannot approve generation. Refinements are requalified within the same five-turn conversation limit.

The complete Hub snapshot contains all **111 unique listings and their detail pages**, downloaded on 2026-11-04 across ten pages, with source URLs, HTML hashes, descriptions, directions, asset types, support, deployment and documentation links. The architect sees every entry, with expanded evidence for likely matches. It also attempts live refreshes; blocked access is labelled honestly. A missing result never proves that no integration exists elsewhere. Both generation.json files retain the signed, reviewed suitability decision and API plan.

Inspect the [complete catalog](apps/api/resources/catalog/integration-hub.json) and the [136-case qualification results](docs/validation/suitability-2026-11-04.md).

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

The fourth button downloads an MI-specific test kit: SDKPerf JCSMP publisher/subscriber scripts, exact generated input/output fixtures (including binary and invalid cases), Java/Go test sources, signed webhook samples, the reproducible 1,000 msg/s runner, and both measured reports/CSV files. SDKPerf binaries are installed separately; SDKPerf is optional for the other tests. The kit reads the same YAML and can run on the selected demo network without opening broker ports.

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

Use `--assessment assessment.json` to retain a reviewed custom-build assessment with CLI packaging. Direct packaging without it records `not_assessed`; a non-build assessment is rejected.

Refresh and evaluate the catalog:

```bash
apps/api/.venv/bin/python scripts/refresh-integration-hub.py --expected-count 111
apps/api/.venv/bin/python scripts/evaluate-suitability.py \
  --ai-core-env /private/path/ai-core.env --output ./output/suitability-evaluation.json
```

The downloader verifies pagination totals, unique URLs and successful detail downloads before replacing the snapshot. It keeps raw pages under .runtime/integration-hub-download. The evaluator exercises a recommendation for every entry plus natural-language reuse, API/direction mismatch, custom-gap and architecture cases through the real AI Core provider. It does not generate code, contact connected business systems or submit benchmark jobs. Use `--natural-only` for a shorter replay; these model evaluations are separate from deterministic CI tests.

## Deploy the factory

The browser receives no AI Core credentials. The Lambda advisor uses Secrets Manager; the isolated build worker receives no AI credentials. Private S3 artifacts expire after one day, downloads use short-lived signed URLs, and global/per-client budgets bound public usage. Code executes inside unprivileged containers without the worker Docker socket or AWS variables; metadata/private host networks are blocked.

```bash
PYTHONPATH=apps/api/src apps/api/.venv/bin/python infra/advisor/deploy.py \
  --ai-core-env /private/path/ai-core.env
```

Deployment requires the AWS CLI and crane (`brew install crane`). The deployer uses its existing Docker login to copy verified Linux/amd64 upstream image digests into a private ECR mirror. Workers pull from that mirror to avoid shared Docker Hub limits; images and registry credentials are not included in downloads.

The script provisions the Lambda advisor, private validation bucket and bounded CodeBuild worker, updates IAM for those resources, and writes docs/demo-config.json. GitHub Pages publishes docs/ when main is pushed. The worker is limited to one concurrent job, fifteen minutes per build and twenty submitted jobs per day. Build/benchmark time is additional to AI generation.

For local API development, export the [server credential fields](infra/advisor/.env.example), VALIDATION_BUCKET and VALIDATION_PROJECT, then run `PYTHONPATH=src uv run uvicorn spec2event.advisor_app:app --host 127.0.0.1 --port 8087` in apps/api. Point docs/demo-config.json at it and serve docs/ on port 8086; restore the deployed URL before publishing. An unconfigured worker fails closed.

## Verify repository changes

```bash
cd apps/api
uv sync --group dev
PYTHONPATH=src uv run pytest -q
```

Use Java 17 and Maven for generated-project compilation tests. Provider mocks and packaging tests are separate from actual broker and cloud qualification. CI exercises fresh Java and Go installations. The historical control plane remains in apps/web and archive/; it is not the public factory and its former EC2 deployment stays retired.
