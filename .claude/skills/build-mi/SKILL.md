---
name: build-mi
description: "Build a focused Solace MI v1 with equivalent Java and Go business-logic files, primary-source research, a runnable Java 17 runtime, contract tests, and broker smoke verification. Use for creating or revising a micro integration quickly."
---

# Build MI v1

Create the user's first working micro integration quickly. Keep business logic in Core.java and core.go and use the standard runtime rather than generating another framework or control plane.

Read docs/agent/core-java-workflow.md in the factory repository. For a personal installation, read references/factory-root.txt to locate that repository. For the bundled project skill, the repository is the current working directory.

Use the existing Claude Code provider configuration; never ask for SAP credentials in chat or copy them into projects. Work directly in the main session. Ask a question only when a business contract cannot reasonably be inferred.

Research the relevant primary vendor documentation, inspect existing proven connectors and release metadata, and then generate a v1. Use scripts/create-mi.py to package the standard runtime around the core. Choose SMF or AMQP for Go based on researched capabilities and the user requirement; Java uses Solace MDK over SMF. Run scripts/create-mi.py SPEC.json --both --validate --output OUTPUT to build and benchmark the actual generated runtimes. Do not deliver either download until both pass >=1,000 messages/s with complete output verification and zero errors/duplicates. Fix real failures. Show measured rates and latency with test conditions; do not call a fixed-load result maximum capacity. Report generation, compilation, and broker delivery as separate outcomes.

Do not silently substitute a payload processor for a requested native source connector. If a CDC, polling, or external trigger is needed, implement that real trigger or make its upstream prerequisite explicit before calling the MI complete. Do not claim synthetic fixtures prove production throughput or delivery guarantees.
