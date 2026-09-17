# Lifecycle Pipeline

Use this file when executing the full end-to-end integration lifecycle.

## Stage 1: Intake

Inputs:
- source credentials or uploaded spec
- source transport details or file layout details
- target deployment credentials
- broker credentials
- Event Portal credentials
- optional AI endpoint credentials

Outputs:
- run record
- isolated workspace
- bound secret set

## Stage 2: Discovery

Tasks:
- inspect the source
- identify entities, operations, message boundaries, or batch boundaries
- assess source connectivity, reliability, and polling or CDC options

Outputs:
- discovery report
- chosen source mode and adapter pattern
- connector reuse candidates
- risk notes

## Stage 3: Canonical Modeling

Tasks:
- derive event candidates
- define topic taxonomy
- define schema names and application names
- choose event versions
- choose the correct source adapter shape

Outputs:
- canonical model JSON or YAML
- topic list
- schema list

## Stage 4: Generation

Tasks:
- render the MDK project
- generate the correct source adapter, mappings, tests, Dockerfile, and deployment assets
- optionally run a bounded AI refinement pass

Outputs:
- generated integration project
- generated fixtures
- generated docs

## Stage 5: Validation

Tasks:
- compile
- run tests
- verify broker publish path and source ingestion path
- reject invalid AI patches

Outputs:
- validation report
- accepted artifact revision

## Stage 6: Build

Tasks:
- build image
- push image to the registry
- persist image tags and build logs

Outputs:
- registry image reference
- build log

## Stage 7: Deploy

Tasks:
- deploy to EC2 or Kubernetes
- wait for health checks
- verify ingress or service reachability

Outputs:
- deployment metadata
- runtime URL
- rollout evidence

## Stage 8: Governance

Tasks:
- register or reconcile Event Portal artifacts
- attach schema or SerDes metadata
- record external IDs

Outputs:
- Event Portal sync report
- manual actions if some API operations are unsupported

## Stage 9: Live Verification

Tasks:
- invoke the generated integration
- verify ingestion, transformation, publish, consume, and UI observation

Outputs:
- end-to-end verification record
- correlation IDs

## Stage 10: Operate

Tasks:
- store logs and metrics references
- persist runbook and rollback notes
- schedule drift checks for source and governance artifacts

Outputs:
- operational handoff
- maintenance plan
