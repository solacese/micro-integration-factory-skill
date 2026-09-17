# Create Micro Integrations

This runbook is for an agent that must take a micro-integration from source credentials or an uploaded contract all the way to a running, governed, documented integration.

## Mission

Design, build, validate, deploy, govern, document, and operate a production-ready micro-integration with:

- Solace PubSub+ as the runtime event transport
- Solace Event Portal as the design-time governance surface
- deterministic generation as the default path
- bounded AI refinement only after a valid baseline exists

## Supported Starting Points

- OpenAPI YAML or JSON
- database credentials and schema access
- file inputs such as CSV, JSON, XML, Avro, EDI, fixed-width, PLA, or custom structured files
- MQTT topics and broker credentials
- Kafka topics and cluster credentials
- AMQP, JMS, or queue endpoints
- webhooks and SaaS APIs
- SFTP, FTP, object storage, or drop-folder based feeds
- existing connector or micro-integration codebase
- existing API endpoint plus credentials
- multiple sources at once, such as OpenAPI plus database, when the goal is a shared canonical event model across more than one ingress path

## Golden Lifecycle

1. **Discover**
   - ingest the source contract or source credentials
   - persist the raw artifact and create an isolated workspace
   - inspect the source before making design decisions

2. **Design**
   - derive the canonical business entities and event model
   - when multiple sources are provided, unify them under one domain model before choosing how many runtimes to generate
   - choose connector reuse versus new generation
   - define topics, schemas, applications, and versioning

3. **Generate**
   - generate or adapt the MDK-based micro-integration
   - render the correct source adapter, runtime config, mapping logic, tests, build files, and deployment assets

4. **Validate**
   - compile the code
   - run tests
   - verify publish behavior and input fixtures

5. **Deploy**
   - build the image
   - push it to the registry
   - deploy it to EC2 or Kubernetes
   - confirm runtime readiness and event flow

6. **Govern**
   - reconcile Event Portal artifacts and version links
   - attach schema and topic metadata cleanly

7. **Document**
   - produce operator notes, consumer-facing event details, and follow-up actions
   - leave a clear audit trail for future reruns and maintenance

8. **Operate**
   - monitor health, metrics, retries, drift, and schema changes
   - propose safe updates when the source or runtime changes

## Short Factory Flow

1. **Spec ingestion**
   - store the uploaded contract or source metadata in the database
   - persist the raw source artifact and create an isolated workspace
   - record run metadata, credentials mode, and intended deployment target

2. **Parse and canonicalize**
   - validate the source contract or source shape
   - extract operations, message layouts, schemas, auth hints, transport details, and business entities
   - derive a canonical model with events, topics, schemas, applications, test fixtures, and adapter type
   - if more than one source is present, identify overlaps and produce one shared event model with source-specific ingress notes

3. **Generate with MDK**
   - reuse an existing connector if possible
   - otherwise generate a new Solace MDK-based Java/Maven micro-integration
   - render REST ingress, broker listeners, queue consumers, file watchers, pollers, or custom source adapters as needed
   - render mapping logic, Dockerfile, deployment assets, tests, and docs
   - if the sources are materially different, prefer multiple small micro-integrations over one oversized runtime

4. **Test**
   - compile and validate the generated project
   - run unit, contract, and happy-path publish tests
   - produce runnable input fixtures and sample invocations

5. **Deploy**
   - build and push the image
   - deploy to the chosen target
   - prefer HA Kubernetes for long-lived production paths; allow EC2 for demo or short-lived runtime paths

6. **Add to Event Portal**
   - register or reconcile domains, applications, application versions, events, event versions, schemas, schema versions, and topic links
   - persist Event Portal IDs and sync outcomes

7. **Document and hand off**
   - publish a design summary, deployment summary, event catalog summary, and operational notes
   - record manual follow-up actions if any artifact cannot be fully automated

## Full Agentic Lifecycle

1. **Intake and secret binding**
   - bind source, broker, deployment, AI, and governance credentials server-side
   - keep discovery credentials read-only until a deploy plan is approved

2. **Source discovery**
   - if the source is OpenAPI, parse the contract
   - if the source is a database, inspect schemas, tables, foreign keys, update columns, row counts, and CDC readiness
   - if the source is a file feed, inspect file format, schema shape, naming convention, arrival pattern, and idempotency strategy
   - if the source is MQTT, Kafka, AMQP, JMS, or a queue, inspect topics, queues, payload format, qos or ack semantics, ordering, and replay behavior
   - if the source is SFTP, FTP, or object storage, inspect file naming, directory patterns, archive rules, and polling cadence
   - if the source is an existing system, inspect the connector surface, auth model, rate limits, and operational constraints

3. **Connector reuse search**
   - search for existing connectors, templates, generated runs, and reusable adapters
   - choose one of:
     - reuse existing connector
     - adapt an existing connector
     - generate a new connector

4. **Integration design**
   - infer business entities and lifecycle transitions
   - if multiple sources exist, decide whether they should become:
     - one shared integration with multiple adapters, or
     - multiple integrations that publish into the same canonical event model
   - choose the correct source adapter pattern:
     - REST ingress
     - webhook ingress
     - database CDC
     - database polling
     - file polling
     - file drop or object storage listener
     - MQTT subscriber
     - Kafka consumer
     - AMQP or JMS consumer
     - queue bridge
     - custom adapter
   - generate event names, topic taxonomy, schema names, application names, and version baselines
   - define the producer/consumer ownership and deployment target

5. **Micro-integration generation**
   - generate an MDK-native runtime
   - add the chosen source adapter, event mapping, Solace publishing, health, metrics, structured logs, containerization, and deployment assets

6. **Validation and tests**
   - compile and run tests
   - generate sample payloads or seed data
   - fail closed on invalid code, broken mappings, missing config, or unverifiable output

7. **Build and packaging**
   - build the container image
   - push to the configured registry
   - emit deployment metadata, Helm values, image tags, and rollback coordinates

8. **Deploy and harden**
   - deploy to EC2 or Kubernetes
   - for production or high-availability paths, include replicas, probes, disruption budgets, anti-affinity, scaling, and secret injection

9. **Govern in Event Portal**
   - create or reconcile domains, applications, application versions, schemas, schema versions, events, event versions, and produced-event links
   - attach schema or SerDes registry coordinates when available

10. **Document the result**
   - produce operator documentation, event catalog notes, consumer-facing usage notes, and known limitations
   - leave enough detail for a future engineer or agent to rerun the lifecycle safely

## Multi-Source Rule

When more than one source is provided, such as an OpenAPI contract and a PostgreSQL database:

1. discover both independently
2. identify the shared business entities
3. define one canonical topic and schema taxonomy
4. keep source-specific mappings separate
5. prefer separate deployable micro-integrations unless there is a strong operational reason to combine them
6. register the resulting artifacts as one coherent Event Portal design graph

11. **Operate continuously**
   - monitor logs, metrics, traces, correlation IDs, retries, dead-letter flow, drift, and schema changes
   - re-run discovery periodically and propose safe updates

## Event Portal Completion Standard

An Event Portal sync is not complete when only the top-level Application exists.

It is complete when the following graph is linked:

1. application domain
2. application
3. application version
4. schema
5. schema version
6. event
7. event version
8. application version `declaredProducedEventVersionIds`

If this graph is not built, the Application may appear in Designer but still look empty or incomplete.

## Required Documentation From Every Run

Every completed run must leave:

- a discovery summary
- an integration design summary
- the canonical event model
- the generated project path or archive
- validation output
- deployment target and URL
- Event Portal registration summary
- a short operator runbook
- known limitations and manual follow-up items

## Default Decision Rules

- prefer deterministic code generation over free-form AI output
- use AI after a baseline project exists and only for bounded refinement
- prefer connector reuse over generating a new connector
- prefer the narrowest correct adapter over a generic catch-all adapter
- prefer Kubernetes for HA, EC2 for demos or short-lived runtime paths
- prefer Event Portal reconciliation over blind creation when artifacts already exist
- do not call the lifecycle complete until runtime, governance, and documentation are all in place

## Acceptance Standard

The run is only complete when the agent can show:

- source understood
- integration design captured
- integration generated
- tests passed
- deployment live
- events flowing on Solace
- Event Portal artifacts linked cleanly
- operator and consumer documentation written
- operations metadata captured for future maintenance
