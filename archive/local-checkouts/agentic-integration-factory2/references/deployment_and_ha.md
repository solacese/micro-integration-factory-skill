# Deployment and High Availability

Use this file when the agent must turn a generated integration into a durable runtime.

## Deployment Targets

- **EC2**
  - best for demos, temporary environments, or isolated runtime verification
  - use short-lived instances with explicit TTL

- **Kubernetes**
  - default for production and HA deployment
  - use Helm or equivalent declarative packaging

## HA Minimum Bar

For long-lived production deployment, require:
- at least 2 replicas
- readiness and liveness probes
- rolling deployment strategy
- PodDisruptionBudget
- anti-affinity or topology spread
- secret injection through the platform
- structured logs and metrics
- autoscaling where appropriate

## Deployment Validation

Before considering deployment complete:
- runtime is healthy
- ingress or service endpoint is reachable
- publish path to Solace is confirmed
- environment-based config is loaded
- image tag and rollout metadata are persisted

## Operational Hardening

Add:
- retry and backoff policy
- dead-letter or quarantine path
- correlation IDs
- dashboards and alert thresholds
- rollback notes

## Preferred Policy

- EC2 for demo or ephemeral paths
- Kubernetes for anything that must survive operator absence, scale, or upgrades cleanly
