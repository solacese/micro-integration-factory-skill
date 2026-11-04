# Micro Integration Factory

The current product is a minimal dark website with chat on the left, status on the right, and four download buttons: Java MDK (green), Go (blue), shared YAML (grey), and tests/SDKPerf ZIP (purple). Use square IDE styling. Business logic stays in Core.java or core.go. First qualify the request against all downloaded Integration Hub entries: recommend reuse, or a different architecture for requirements beyond this profile. Only build for a justified custom gap. Fold that decision into the same short confirmation. Research and confirm the service/API and protocol, then build and run actual >=1,000 messages/s tests on BOTH generated runtimes before unlocking downloads. Show measured performance with conditions. Keep this experience simple.

Use .claude/skills/build-mi/SKILL.md and docs/agent/core-java-workflow.md when generating an MI. The standard runtime templates are under apps/api/resources/templates/core-java and core-go. Do not regenerate the old full control plane as part of an ordinary v1.

The web advisor uses SAP AI Core with credentials supplied only server-side. Claude Code uses its existing global AI Core proxy configuration. Never print, embed, or commit credential files.

Tests: `cd apps/api && PYTHONPATH=src uv run pytest -q` (Java 17+ and Maven enable generated-project checks). The new advisor entry point is spec2event.advisor_app:app; it does not need PostgreSQL or Redis. The old apps/web control plane remains for historical use and is not the public demo.
