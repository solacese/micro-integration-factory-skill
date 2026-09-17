# Stripe Webhook to EC2 to Event Portal Prompt

Use this prompt when you want a more complete OpenAPI-driven micro-integration, not a minimal demo:

- OpenAPI source
- Java-first generated micro-integration
- broad Stripe event catalogue
- executable SerDes contracts and Event Portal documentation before deployment
- producer and consumer verification, not producer-only verification
- deployment to temporary EC2
- Solace event publication

Bundled local contract:

- `samples/openapi/stripe-webhook-demo.yaml`

## Prompt

```text
Use this repository as your skill and execution guide.

Read SKILL.md first, then create_micro_integrations.md.
Activate `demo/env/openapi.env` into the root `.env`, then use the active `.env` in this repo as the runtime and infrastructure configuration contract.

For this run, treat the OpenAPI path as a complete Stripe-oriented micro-integration design and implementation task:
- source mode: OpenAPI
- source file: samples/openapi/stripe-webhook-demo.yaml
- deployment target: EC2
- event transport: Solace PubSub+
- governance target: Solace Event Portal

Your job is to take over the full lifecycle of the micro-integration and complete it end to end.

Do this in order:
1. inspect the OpenAPI contract in detail
2. treat it as a Stripe webhook ingress design, not a live Stripe account discovery task
3. derive a broad canonical event model for the Stripe payments lifecycle
4. do not stop at the default 2-3 event candidates; target at least 15 event versions across multiple webhook families that are relevant to the payments lifecycle
5. make the target event catalogue explicit across at least these Stripe families unless the source contract clearly rules one out:
   - payment_intent
   - charge
   - refund
   - invoice
   - checkout.session
   - dispute
6. if the provided contract is thinner than the desired event surface, document the assumptions explicitly and extend the canonical model in a defensible way instead of falling back to a tiny event set
7. define the topic taxonomy, schema set, application structure, Event Portal design graph, compatibility policy, message header contract, and SerDes strategy before build and deployment
8. document and reconcile those Event Portal artifacts before you build or deploy anything:
   - application domain
   - application
   - application version
   - schemas
   - schema versions
   - events
   - event versions
   - produced-event links
9. treat SerDes as executable contract design, not prose only
10. document SerDes for every event family in Event Portal metadata and in the run output:
   - schema format
   - serializer family
   - deserializer family
   - content type
   - required message headers:
     - content-type
     - event-type
     - schema-name
     - schema-version
     - source-system
     - source-record-id
     - correlation-id
     - occurred-at
   - schema subject or artifact naming convention
   - schema versioning policy
   - registry coordinates if an external registry exists, otherwise explicit Event Portal-only designation
11. generate or adapt the Solace MDK Java micro-integration
12. make the Java implementation substantial:
   - richer controller logic
   - per-event mapping logic in Java
   - explicit payload builders and header population
   - explicit service-layer orchestration
   - no tiny catch-all mapper that collapses the event model back to a handful of events
13. validate and test the Java runtime locally with fixture webhook payloads
14. include Java unit, schema contract, and happy-path verification for event mapping, header population, schema compliance, and publish behavior
15. add a small consumer-side verification path that subscribes through Solace and proves representative messages can be deserialized and validated against the declared schemas
16. include negative-path and operational checks:
   - malformed webhook payload
   - unknown Stripe event type
   - duplicate Stripe delivery id
   - publish retry or temporary broker failure
17. make idempotency explicit in the design and in the runtime behavior; repeated Stripe deliveries must not create uncontrolled duplicate publishes
18. only after governance is documented and the Java baseline is valid, build the image
19. deploy it to a temporary EC2 instance
20. verify that the generated webhook endpoint can be invoked with sample Stripe payloads
21. verify that invoking it publishes the expected broad event set to Solace
22. verify that published messages carry the expected headers, schema metadata, and compatibility information
23. verify that the consumer-side path can deserialize representative messages successfully
24. write operator and consumer documentation with explicit Java/runtime notes

Keep the implementation focused on a complete micro-integration:
- one source contract
- one Java runtime
- many event versions, not a tiny showcase
- one governed Event Portal design graph documented before deployment
- one credible producer-to-consumer proof path

Do not stop at code generation.
The run is only complete when governance, Java implementation, runtime verification, and documentation are all in place.

Return these outputs:
- source summary
- Java implementation summary
- canonical event inventory with counts
- schema and SerDes matrix
- header contract and compatibility policy summary
- Event Portal graph summary produced before deployment
- generated artifact path
- deploy target and EC2 details
- runtime URL
- sample test invocation
- published topics and captured event examples
- consumer verification summary
- negative-path and idempotency summary
- runtime verification summary after deployment
- any blocking issue that would prevent a credible showcase
```

## Implementation Goal

The audience should be able to understand this as a serious Java-based source integration:

1. point the agent at an OpenAPI contract
2. watch it design a much broader event model than the default sample
3. watch it document schemas, SerDes, headers, and Event Portal relationships before deployment
4. watch it generate and validate meaningful Java code
5. watch it prove producer and consumer compatibility, not only producer publish success
6. watch it deploy to EC2
7. see the event flow on Solace
8. see the corresponding governed assets in Event Portal

## Important Note

If the Event Portal token in the active `.env` is rejected, refresh it before running this prompt so the governance-first part succeeds before build and deployment.
