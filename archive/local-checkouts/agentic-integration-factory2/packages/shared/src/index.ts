export type RunStepName =
  | "uploaded"
  | "parsed"
  | "canonicalized"
  | "generated"
  | "ai_refined"
  | "validated"
  | "built"
  | "approval"
  | "deployed"
  | "portal_synced"
  | "ready";

export type RunStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "partial"
  | "not_configured"
  | "awaiting_approval";

export type DeploymentTarget =
  | "local_docker"
  | "ec2_docker_host"
  | "kubernetes_helm"
  | "ephemeral_ec2";

export interface TestFixture {
  operationId: string;
  label: string;
  method: string;
  path: string;
  payload: Record<string, unknown> | null;
}

export interface RunStepLog {
  id: string;
  stepName: RunStepName;
  status: RunStatus;
  message: string;
  createdAt: string;
}

export interface ArtifactSummary {
  id: string;
  runId: string;
  kind: string;
  path: string;
  language?: string | null;
  revision: number;
  createdAt: string;
}

export interface EventCandidate {
  operationId: string;
  canonicalEventName: string;
  topicName: string;
  schemaName: string;
  applicationName: string;
  emitsEvent: boolean;
}

export interface OperationSummary {
  operationId: string;
  method: string;
  path: string;
  summary?: string | null;
  requestSchemaName?: string | null;
  responseSchemaName?: string | null;
  emitsEvent: boolean;
  eventCandidates: EventCandidate[];
}

export interface CanonicalModelSummary {
  serviceName: string;
  serviceVersion: string;
  title: string;
  sourceMode?: string;
  adapterType?: string;
  runtimeBlueprint?: string;
  servers?: string[];
  authSchemes?: string[];
  operations: OperationSummary[];
  topics: string[];
  schemaNames: string[];
  applicationNames: string[];
  stripeEnabled: boolean;
  testFixtures: TestFixture[];
  sourceDetails?: Record<string, unknown>;
}

export interface ActiveDeploymentSummary {
  instanceId?: string | null;
  privateServiceUrl?: string | null;
  publicIp?: string | null;
  expiresAt?: string | null;
  target: DeploymentTarget;
  status: RunStatus;
}

export interface GenerationRunSummary {
  id: string;
  uploadId: string;
  serviceName: string;
  status: RunStatus;
  deploymentTarget: DeploymentTarget;
  sourceMode: string;
  adapterType?: string | null;
  runtimeBlueprint?: string | null;
  imageTag?: string | null;
  serviceUrl?: string | null;
  createdAt: string;
  updatedAt: string;
  lastMessage?: string | null;
  canonicalModel?: CanonicalModelSummary | null;
  activeDeployment?: ActiveDeploymentSummary | null;
  deploymentApprovalStatus: "not_requested" | "awaiting_approval" | "approved";
  deploymentApprovalNotes?: string | null;
  deploymentApprovalRequestedAt?: string | null;
  deploymentApprovedAt?: string | null;
  deploymentApprovedBy?: string | null;
  steps: RunStepLog[];
}

export interface ArtifactDetail extends ArtifactSummary {
  content: string;
}

export interface EventLogRecord {
  id: string;
  runId: string;
  correlationId: string;
  stage: string;
  topicName?: string | null;
  payload?: Record<string, unknown> | null;
  createdAt: string;
}

export interface DeploymentRecord {
  id: string;
  runId: string;
  target: DeploymentTarget;
  status: RunStatus;
  imageTag?: string | null;
  serviceUrl?: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface EventPortalSyncRecord {
  id: string;
  runId: string;
  artifactType: string;
  artifactName: string;
  externalId?: string | null;
  status: RunStatus;
  manualAction?: string | null;
  createdAt: string;
}

export interface SettingsView {
  hasAwsConfig: boolean;
  hasSolaceConfig: boolean;
  hasEventPortalConfig: boolean;
  hasLiteLlmConfig: boolean;
  hasRegistryConfig: boolean;
  hasEc2Config: boolean;
  publicBaseUrl?: string | null;
}

export interface TimelineEvent {
  type: "run" | "event";
  payload: GenerationRunSummary | EventLogRecord;
}

export const GOLDEN_STEPPER: Array<{ key: RunStepName; label: string }> = [
  { key: "uploaded", label: "Upload" },
  { key: "parsed", label: "Parse" },
  { key: "canonicalized", label: "Canonicalize" },
  { key: "generated", label: "Generate" },
  { key: "ai_refined", label: "Refine" },
  { key: "built", label: "Build" },
  { key: "approval", label: "Approve" },
  { key: "deployed", label: "Deploy" },
  { key: "ready", label: "Test" }
];
