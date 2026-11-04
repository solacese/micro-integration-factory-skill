# Deployment retirement

AWS deployment retirement requested on 17 September 2026. This commit preserves the final local source and configuration work before removal of the local checkout. Redeployment is manual; deployment documentation describes historical setups.

Supply credentials through your own environment or secret store. Embedded credentials have been replaced with `REPLACE_ME`. Local secrets, infrastructure state, dependency caches, generated archives, and generated document binaries are excluded from this source snapshot; originals were backed up privately.

## Current core Java v1 path

On 4 November 2026, the public demo was rebuilt around one Core.java file and a standard Java runtime. Its SAP AI Core advisor is a separate small Lambda deployment managed by `infra/advisor/deploy.py`. The old EC2 control plane is still retired and is not redeployed by this workflow.
