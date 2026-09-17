# OpenAPI to EC2 to Event Portal Demo Prompt

Use this prompt when you want to film the simplest compelling version of the factory:

- OpenAPI source
- generated micro-integration
- deployment to temporary EC2
- Solace event publication
- Event Portal registration and linking

Bundled local contract:

- `apps/api/resources/samples/openapi/petstore.yaml`

## Prompt

```text
Use this repository as your skill and execution guide.

Read docs/agent/SKILL.md first, then docs/agent/create_micro_integrations.md.
Activate `infra/demo/env/openapi.env` into the root `.env`, then use the active `.env` in this repo as the runtime and infrastructure configuration contract.

For this run, keep the path simple and demo-friendly:
- source mode: OpenAPI
- source file: apps/api/resources/samples/openapi/petstore.yaml
- deployment target: EC2
- event transport: Solace PubSub+
- governance target: Solace Event Portal

Your job is to take over the full lifecycle of the micro-integration and complete it end to end.

Do this in order:
1. inspect the OpenAPI contract
2. derive the canonical event model
3. generate or adapt the Solace MDK micro-integration
4. validate and test it locally
5. build the image
6. deploy it to a temporary EC2 instance
7. verify the generated API can be invoked
8. verify that invoking it publishes events to Solace
9. register and link the resulting application, schemas, events, and versions in Event Portal
10. write concise operator and consumer documentation for the run

Keep the demo focused on the concept:
- one source contract
- one generated micro-integration
- one clean deployed runtime
- one clean Event Portal design graph

Do not stop at code generation.
The run is only complete when runtime, governance, and documentation are all in place.

Return these outputs:
- source summary
- integration design summary
- generated artifact path
- deploy target and EC2 details
- runtime URL
- sample test invocation
- published topics
- Event Portal artifact summary
- any blocking issue that would prevent filming
```

## Filming Goal

The audience should be able to understand the whole story from one short run:

1. upload or point to an OpenAPI contract
2. watch the agent design and generate the integration
3. watch it deploy to EC2
4. see the event flow on Solace
5. see the corresponding assets appear in Event Portal

## Important Note

If the Event Portal token in the active `.env` is rejected, refresh it before filming so the governance part of the demo succeeds live.
