---
name: build-mi
description: "Build a focused Solace MI v1 with equivalent Java and Go business-logic files, primary-source research, a runnable Java 17 runtime, contract tests, and broker smoke verification. Use for creating or revising a micro integration quickly."
---

# Build MI v1

Create the user's first working micro integration quickly. Keep business logic in Core.java and core.go and use the standard runtime rather than generating another framework or control plane.

Read docs/agent/core-java-workflow.md in the factory repository. For a personal installation, read references/factory-root.txt to locate that repository. For the bundled project skill, the repository is the current working directory.

Use the existing Claude Code provider configuration; never ask for SAP credentials in chat or copy them into projects. Work directly in the main session. Ask a question only when a business contract cannot reasonably be inferred.

Before generating, read the full downloaded 111-entry catalog at apps/api/resources/catalog/integration-hub.json and check https://solace.com/integration-hub/ for current details. Qualify whether the request should be built at all. Recommend reuse with a specific link when an existing asset, native protocol, or configurable transformation covers it. Compare the actual API, source/target direction, support and deployment; Salesforce Pub/Sub is not arbitrary REST CRUD. Explain a concrete custom gap before approving a new MI. Push back on requirements beyond this stateless profile: rates above its tested 1,000 inputs/s, hard latency SLOs, payloads above 1 MiB, strict ordering, exactly-once/atomic multi-system delivery, or durable workflows. Propose an appropriate connector/stream processor/workflow/capacity design; do not claim all MIs are unsuitable. A plain yes cannot bypass this recommendation. Be explicit about catalog date and failed live refreshes.

Keep the normal flow to describe, review fit + API together, then download; no extra approval screen. One essential question when needed, five user turns maximum. Research the relevant primary vendor documentation and release metadata after the fit check. Use scripts/create-mi.py to package the standard runtime around the core. Choose SMF or AMQP for Go based on researched capabilities and the user requirement; Java uses Solace MDK over SMF. Run scripts/create-mi.py SPEC.json --both --validate --output OUTPUT to build and benchmark the actual generated runtimes. Do not deliver either download until both pass >=1,000 messages/s with complete output verification and zero errors/duplicates. Fix real failures. Show measured rates and latency with test conditions; do not call a fixed-load result maximum capacity. Report generation, compilation, and broker delivery as separate outcomes.

Do not silently substitute a payload processor for a requested native source connector. If a CDC, polling, or external trigger is needed, implement that real trigger or make its upstream prerequisite explicit before calling the MI complete. Do not claim synthetic fixtures prove production throughput or delivery guarantees.
