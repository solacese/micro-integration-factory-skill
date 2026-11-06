# Factory scenario checks · 2026-11-06

The baseline used the public advisor API. The revised advisor used the same SAP AI Core provider from the development checkout. For the three custom scenarios, I confirmed the service plan, generated both packages, and ran the standard worker with synthetic fixtures and an isolated Solace broker.

| Scenario | Public baseline | Revised advisor |
| --- | --- | --- |
| Salesforce Account CDC to Solace | HTTP 502 | Reuse |
| Solace to Salesforce Account external-ID upsert | Confirm custom build | Architecture review |
| Custom account scoring after the Salesforce connector | Confirm custom build | Confirm custom build |
| Signed Stripe snapshot webhook and customer fan-out | Confirm custom build | Confirm custom build |
| Mandatory Stripe v2 thin events and resource retrieval | Confirm custom build | Architecture review |
| Registry validation for JSON Schema, XSD, Avro, and Protobuf | Clarification | Reuse |
| Inline order schema and SAMPLE- quantity limit | Confirm custom build | Confirm custom build |
| Unchanged Kafka orders and shipments into Solace | Reuse | Reuse |
| Solace queue archived to Amazon S3 | Reuse | Reuse |
| Atomic Salesforce/Stripe effects and global ordering at 100,000/s | Architecture review | Architecture review |

The registry-backed case links to the published four-format validator. The Salesforce CDC scoring case keeps the existing connector as the source and adds a broker-side processor. Salesforce REST writes and Stripe thin retrieval require an external API test endpoint, so the factory presents an architecture review before generation.

[Schema Validation MI v1.0.2](https://github.com/solacese/schema-validation-micro-integration/releases/tag/v1.0.2) · [Salesforce integration](https://solace.com/integration-hub/salesforce/) · [Stripe event formats](https://docs.stripe.com/events/how-events-work#event-formats)

## Generated runtime checks

| Custom scenario | Java inputs/s | Go inputs/s | Both runtimes qualified |
| --- | ---: | ---: | --- |
| Custom account scoring after the Salesforce connector | 1,016.4 | 1,018.5 | Yes |
| Signed Stripe snapshot webhook and customer fan-out | 1,019.6 | 1,020.0 | Yes |
| Inline order schema and SAMPLE- quantity limit | 1,018.2 | 1,019.9 | Yes |

The first Stripe Go benchmark missed 96 deliveries in short bursts. The retest used the same generated business logic with a 250 ms bounded wait for Go HTTP capacity. The load generator now reports request failures by category.

Independent contract checks exercised exact Salesforce thresholds, missing and unsafe Stripe customer IDs, preserved payload bytes, and JSON Schema integer values expressed as decimals or very large numbers.

Each benchmark used a ten-second measurement window after ten seconds of warmup. The worker verifies the output bytes and every expected topic, and counts delivery errors and duplicates. Salesforce, Stripe, Kafka and S3 accounts were outside this fixture run.

Earlier candidates failed on incompatible Jackson imports, a wrong schema-library result type, nested broker headers and a topic pattern that rejected hyphens. The revised factory builds known profiles directly after approval, supplies the pinned schema APIs, and checks fixture headers before starting the worker.

## Replay prompts

1. Stream Salesforce AccountChangeEvent CDC to Solace topic crm/accounts/changed using the Salesforce Pub/Sub API. Keep the events unchanged.
2. Consume account updates already on a Solace queue and upsert Salesforce Account records by External_Id__c over the Salesforce REST API. Map externalId to the external key and companyName to Name. Plan the integration first. We will provide an OAuth token and a Salesforce sandbox later.
3. Our existing Salesforce connector already delivers decoded Salesforce AccountChangeEvent CDC JSON onto Solace. Build only a custom stateless scoring processor: if AnnualRevenue is at least 1000000 and NumberOfEmployees is at least 50 publish the original bytes to crm/qualified, otherwise publish to crm/review. Reject invalid field types.
4. Receive signed Stripe snapshot webhooks. Verify Stripe-Signature against the raw request body, then route the unchanged payment events to payments/by-type/<event.type> and payments/by-customer/<customer-id>. Require data.object.customer and reject requests without a valid customer ID.
5. Use Stripe v2 thin event webhooks, verify Stripe signatures and retrieve the related resource over Stripe API before sending the enriched event to Solace. We cannot switch to snapshot events.
6. I need the existing Solace Schema Registry validation MI to validate JSON Schema, XML/XSD, Avro and Protobuf before forwarding events. Can I reuse https://github.com/solacese/schema-validation-micro-integration instead of generating one? Use the published release when appropriate.
7. Build a local JSON Schema plus custom business validation MI for order messages from a Solace queue. The JSON Schema requires orderId (nonempty string) and quantity (integer, minimum 1), and disallows extra fields. A business rule also rejects quantities over 5 for order IDs starting with SAMPLE-. Preserve valid bytes and publish to orders/validated. Use an inline schema with no external registry.
8. Bridge Kafka orders and shipments topics into the Solace event mesh without changing the payload. Use existing integrations where possible.
9. Archive events from a Solace queue as objects in Amazon S3 using a supported existing connector. No custom processing.
10. Build an integration that updates Salesforce, charges Stripe and publishes to two topics atomically, with global ordering, exactly-once effects and 100,000 inputs/s.
