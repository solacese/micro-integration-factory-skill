# Micro Integration Factory

The current product is a minimal dark website with chat on the left, status on the right, and a Download MI v1 button. It targets one Core.java business-logic file. Keep this experience simple.

Use .claude/skills/build-mi/SKILL.md and docs/agent/core-java-workflow.md when generating an MI. The standard runtime templates are under apps/api/resources/templates/core-java. Do not regenerate the old full control plane as part of an ordinary v1.

The web advisor uses SAP AI Core with credentials supplied only server-side. Claude Code uses its existing global AI Core proxy configuration. Never print, embed, or commit credential files.

Tests: `cd apps/api && PYTHONPATH=src uv run pytest -q` (Java 17+ and Maven enable generated-project checks). The new advisor entry point is spec2event.advisor_app:app; it does not need PostgreSQL or Redis. The old apps/web control plane remains for historical use and is not the public demo.
