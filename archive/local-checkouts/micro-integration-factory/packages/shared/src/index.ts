export type SourceType =
  | "openapi"
  | "json_schema"
  | "database"
  | "graphql"
  | "custom";

export type RunStepName =
  | "uploaded"
  | "parsed"
  | "canonicalized"
  | "generated"
  | "ai_refined"
  | "validated"
  | "built"
  | "deployed"
  | "portal_synced"
  | "ready";

export type RunStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "partial"
  | "not_configured";

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

export type IngressType = "rest_controller" | "polling_consumer" | "event_subscriber";

export interface CanonicalModelSummary {
  serviceName: string;
  serviceVersion: string;
  title: string;
  servers: string[];
  authSchemes: string[];
  operations: OperationSummary[];
  topics: string[];
  schemaNames: string[];
  applicationNames: string[];
  stripeEnabled: boolean;
  testFixtures: TestFixture[];
  ingressType?: IngressType;
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
  sourceType: SourceType;
  serviceName: string;
  status: RunStatus;
  deploymentTarget: DeploymentTarget;
  imageTag?: string | null;
  serviceUrl?: string | null;
  createdAt: string;
  updatedAt: string;
  lastMessage?: string | null;
  canonicalModel?: CanonicalModelSummary | null;
  activeDeployment?: ActiveDeploymentSummary | null;
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
  litellmBaseUrl?: string | null;
  litellmModel?: string | null;
}

export interface LiteLlmTestResult {
  ok: boolean;
  message: string;
  model?: string | null;
}

export type SchemaPackFormat =
  | "hl7"
  | "generic_edi"
  | "edifact"
  | "odette"
  | "ansi_x12"
  | "json_schema"
  | "xml_schema"
  | "csv_layout"
  | "fixed_width";

export interface SchemaPackSummary {
  id: string;
  name: string;
  schemaFormat: SchemaPackFormat | string;
  version?: string | null;
  messageType?: string | null;
  industry?: string | null;
  filename?: string | null;
  summary: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
}

export interface SchemaPack extends SchemaPackSummary {
  rawContent: string;
}

export interface TimelineEvent {
  type: "run" | "event";
  payload: GenerationRunSummary | EventLogRecord;
}

export type TransformLanguage = "java_sdk" | "groovy" | "dataweave";

export type InputMessageFormat =
  | "json"
  | "xml"
  | "csv"
  | "fixed_width"
  | "hl7"
  | "edifact"
  | "ansi_x12"
  | "odette"
  | "text";

export interface SolaceSubscriptionSummary {
  id: string;
  topicFilter: string;
  status: string;
  message: string;
}

export interface CapturedEvent {
  id: string;
  subscriptionId: string;
  brokerUrl: string;
  topicFilter: string;
  topicName: string;
  headers: Record<string, unknown>;
  payload: Record<string, unknown>;
  createdAt: string;
}

export interface DraftFile {
  path: string;
  purpose: string;
  content?: string;
}

export interface BuilderDraft {
  transformLanguage: TransformLanguage;
  intentSummary: string;
  assistantMessage?: string;
  qualifyingQuestions?: string[];
  topicMapping?: {
    inputTopic?: string;
    outputTopic?: string;
  };
  headerMapping?: {
    inputHeaders?: Record<string, unknown>;
    outputHeaders?: Record<string, unknown>;
    topicHeader?: string;
    notes?: string[];
  };
  sampleOutput?: Record<string, unknown>;
  files?: DraftFile[];
  validationNotes?: string[];
  schemaContext?: string | null;
  schemaPackId?: string | null;
  schemaPack?: Record<string, unknown> | null;
  llmProvider?: {
    provider?: string;
    model?: string;
    mode?: string;
    status?: string;
    intent?: string;
    message?: string;
  };
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | string;
  content: string;
  draft?: BuilderDraft | null;
  createdAt: string;
}

export interface BuilderSession {
  id: string;
  transformLanguage: TransformLanguage;
  status: string;
  intentSummary?: string | null;
  draft?: BuilderDraft | null;
  preview?: Record<string, unknown> | null;
  generatedRunId?: string | null;
  capturedEvent: CapturedEvent;
  messages: ChatMessage[];
}

export interface PreviewResult {
  sessionId: string;
  transformLanguage: TransformLanguage;
  sampleOutput: Record<string, unknown>;
  draft?: BuilderDraft | null;
}

export interface WorkerJob {
  id: string;
  builderSessionId: string;
  jobType: string;
  status: string;
  projectPath?: string | null;
  imageTag?: string | null;
  logs: string;
  result: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
}

export interface GenerateBuilderResult {
  session: BuilderSession;
  run: GenerationRunSummary;
  workerJob: WorkerJob;
}

export const GOLDEN_STEPPER: Array<{ key: RunStepName; label: string }> = [
  { key: "uploaded", label: "Upload" },
  { key: "parsed", label: "Parse" },
  { key: "canonicalized", label: "Canonicalize" },
  { key: "generated", label: "Generate" },
  { key: "ai_refined", label: "Refine" },
  { key: "built", label: "Build" },
  { key: "deployed", label: "Deploy" },
  { key: "ready", label: "Test" }
];
