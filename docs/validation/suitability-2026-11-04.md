# Integration suitability qualification — 2026-11-04

The factory downloaded **all 111 unique Integration Hub entries**, including their detail pages, from **ten listing pages**. The checked-in snapshot retains API descriptions, source/target direction, asset type, support, deployment, documentation links, download time and HTML SHA-256 hashes. Raw HTML is retained locally under .runtime/integration-hub-download; `scripts/refresh-integration-hub.py --expected-count 111` reproduces the collection and fails on missing pages, duplicates or a changed total.

The real AI Core provider evaluated **136 request cases** against this complete snapshot:

| Requests | Observed result |
| --- | --- |
| 111 named catalog capability probes | 110 recommended reuse; the Flink community guide asked one clarification |
| 25 natural-language probes | All returned an allowed decision and the required matching asset, where applicable |
| Overall decisions | 123 reuse, 2 clarify, 4 custom build, 7 architecture review |

The natural probes cover Salesforce events versus REST CRUD, Kafka bridging, S3 source/target, SQS, SNS direction mismatch, three CDC databases, IBM MQ, native MQTT, standard transformations, signed Stripe routing, a proprietary processor after an existing connector, 100k inputs/s, hard p99 latency, atomic/exactly-once delivery, ordering, durable workflow, oversized payloads, withdrawn constraints, an undocumented vendor and an instruction to bypass qualification.

One provider read timeout for Kafka Connect Sink passed on replay. The Flink result was appropriate: an integration guide is not proof of a deployable connector. Guide probes therefore accept reuse or clarification, with generation blocked in either case. The initial outcomes are preserved in the [case report](suitability-2026-11-04.json).

These are recommendation evaluations, not installation or performance tests of the 111 third-party assets. They replay the full downloaded catalog without contacting business systems or submitting build jobs. Live refresh failures are explicitly labelled in the product. A complete dated Hub snapshot is not an inventory of every integration that could exist elsewhere.

Deterministic API tests separately cover the generation gate, old/blocked confirmation receipts, runtime limits, URL validation, private-query protection, catalog completeness, provenance and retention of the reviewed assessment in both Java/Go archives. Custom builds still require API confirmation and actual build/contract/broker/performance qualification before any download is enabled.
