"use client";

import type {
  ArtifactDetail,
  ArtifactSummary,
  BuilderSession,
  CapturedEvent,
  EventLogRecord,
  GenerateBuilderResult,
  GenerationRunSummary,
  InputMessageFormat,
  LiteLlmTestResult,
  PreviewResult,
  SchemaPack,
  SchemaPackFormat,
  SchemaPackSummary,
  SettingsView,
  SolaceSubscriptionSummary,
  TransformLanguage,
  WorkerJob
} from "@spec2event/shared";

function apiBase() {
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (configured) {
    return configured;
  }
  if (typeof window !== "undefined") {
    const { hostname, port } = window.location;
    if ((hostname === "localhost" || hostname === "127.0.0.1") && port && port !== "8000") {
      return "http://127.0.0.1:8000";
    }
  }
  return "";
}

function adminHeaders(): HeadersInit {
  return {};
}

async function ensureOk(response: Response) {
  if (!response.ok) {
    const text = await response.text();
    let message: string | undefined;
    try {
      const parsed = JSON.parse(text) as { detail?: unknown; message?: unknown };
      const detail = parsed.detail ?? parsed.message;
      if (typeof detail === "string" && detail.trim()) {
        message = detail;
      }
    } catch {}
    throw new Error(message ?? (text.trim() || `Request failed with ${response.status}`));
  }
  return response;
}

export async function uploadSpec(file: File, sourceType: string = "openapi") {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("source_type", sourceType);
  const base = apiBase();
  const response = await ensureOk(
    await fetch(`${base}/api/uploads`, {
      method: "POST",
      headers: adminHeaders(),
      body: formData
    })
  );
  return response.json();
}

export async function getSourceTypes(): Promise<string[]> {
  const base = apiBase();
  const response = await ensureOk(await fetch(`${base}/api/source-types`, { cache: "no-store" }));
  return response.json();
}

export async function createSolaceSubscription(payload: {
  brokerUrl: string;
  vpn: string;
  username: string;
  password: string;
  topicFilter: string;
}): Promise<SolaceSubscriptionSummary> {
  const base = apiBase();
  const response = await ensureOk(
    await fetch(`${base}/api/solace/subscriptions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...adminHeaders()
      },
      body: JSON.stringify(payload)
    })
  );
  return response.json();
}

export async function listCapturedEvents(subscriptionId: string): Promise<CapturedEvent[]> {
  const base = apiBase();
  const response = await ensureOk(
    await fetch(`${base}/api/solace/subscriptions/${subscriptionId}/captured-events`, {
      cache: "no-store"
    })
  );
  return response.json();
}

export function capturedEventsStreamUrl(subscriptionId: string) {
  return `${apiBase()}/api/solace/subscriptions/${subscriptionId}/events`;
}

export async function createInputMessageEvent(payload: {
  topicName: string;
  sourceName?: string;
  inputFormat: InputMessageFormat;
  payload: unknown;
  headers?: Record<string, unknown>;
}): Promise<CapturedEvent> {
  const base = apiBase();
  const response = await ensureOk(
    await fetch(`${base}/api/builder/input-events`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...adminHeaders()
      },
      body: JSON.stringify(payload)
    })
  );
  return response.json();
}

export async function createBuilderSession(payload: {
  capturedEventId: string;
  transformLanguage: TransformLanguage;
}): Promise<BuilderSession> {
  const base = apiBase();
  const response = await ensureOk(
    await fetch(`${base}/api/builder/sessions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...adminHeaders()
      },
      body: JSON.stringify(payload)
    })
  );
  return response.json();
}

export async function sendBuilderMessage(
  builderSessionId: string,
  payload: {
    content: string;
    transformLanguage?: TransformLanguage;
    schemaContext?: string;
    schemaPackId?: string;
  }
): Promise<BuilderSession> {
  const base = apiBase();
  const response = await ensureOk(
    await fetch(`${base}/api/builder/sessions/${builderSessionId}/messages`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...adminHeaders()
      },
      body: JSON.stringify(payload)
    })
  );
  return response.json();
}

export async function designBuilderSession(
  builderSessionId: string,
  payload: {
    content: string;
    transformLanguage?: TransformLanguage;
    schemaContext?: string;
    schemaPackId?: string;
  }
): Promise<BuilderSession> {
  const base = apiBase();
  const response = await ensureOk(
    await fetch(`${base}/api/builder/sessions/${builderSessionId}/design`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...adminHeaders()
      },
      body: JSON.stringify(payload)
    })
  );
  return response.json();
}

export async function createBuilderPreview(builderSessionId: string): Promise<PreviewResult> {
  const base = apiBase();
  const response = await ensureOk(
    await fetch(`${base}/api/builder/sessions/${builderSessionId}/preview`, {
      method: "POST",
      headers: adminHeaders()
    })
  );
  return response.json();
}

export async function generateBuilderSession(builderSessionId: string): Promise<GenerateBuilderResult> {
  const base = apiBase();
  const response = await ensureOk(
    await fetch(`${base}/api/builder/sessions/${builderSessionId}/generate`, {
      method: "POST",
      headers: adminHeaders()
    })
  );
  return response.json();
}

export async function getWorkerJob(workerJobId: string): Promise<WorkerJob> {
  const base = apiBase();
  const response = await ensureOk(
    await fetch(`${base}/api/worker/jobs/${workerJobId}`, { cache: "no-store" })
  );
  return response.json();
}

export async function createRun(payload: {
  uploadId: string;
  deploymentTarget: "local_docker" | "ec2_docker_host" | "kubernetes_helm" | "ephemeral_ec2";
  autoBuild: boolean;
  autoDeploy: boolean;
}): Promise<GenerationRunSummary> {
  const base = apiBase();
  const response = await ensureOk(
    await fetch(`${base}/api/runs`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...adminHeaders()
      },
      body: JSON.stringify(payload)
    })
  );
  return response.json();
}

export async function listRuns(): Promise<GenerationRunSummary[]> {
  const base = apiBase();
  const response = await ensureOk(await fetch(`${base}/api/runs`, { cache: "no-store" }));
  return response.json();
}

export async function getRun(runId: string): Promise<GenerationRunSummary> {
  const base = apiBase();
  const response = await ensureOk(await fetch(`${base}/api/runs/${runId}`, { cache: "no-store" }));
  return response.json();
}

export async function getEventLogs(runId: string): Promise<EventLogRecord[]> {
  const base = apiBase();
  const response = await ensureOk(await fetch(`${base}/api/runs/${runId}/events`, { cache: "no-store" }));
  return response.json();
}

export async function getArtifacts(runId: string): Promise<ArtifactSummary[]> {
  const base = apiBase();
  const response = await ensureOk(await fetch(`${base}/api/runs/${runId}/artifacts`, { cache: "no-store" }));
  return response.json();
}

export function workspaceArchiveUrl(runId: string) {
  return `${apiBase()}/api/runs/${runId}/workspace.zip`;
}

export function transformFileUrl(runId: string) {
  return `${apiBase()}/api/runs/${runId}/transform-file`;
}

export function imageArchiveUrl(runId: string) {
  return `${apiBase()}/api/runs/${runId}/image.tar`;
}

export async function getArtifact(runId: string, artifactId: string): Promise<ArtifactDetail> {
  const base = apiBase();
  const response = await ensureOk(await fetch(`${base}/api/runs/${runId}/artifacts/${artifactId}`, { cache: "no-store" }));
  return response.json();
}

export async function updateArtifact(runId: string, artifactId: string, content: string): Promise<ArtifactDetail> {
  const base = apiBase();
  const response = await ensureOk(
    await fetch(`${base}/api/runs/${runId}/artifacts/${artifactId}`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        ...adminHeaders()
      },
      body: JSON.stringify({ content })
    })
  );
  return response.json();
}

export async function queueBuild(runId: string) {
  const base = apiBase();
  const response = await ensureOk(
    await fetch(`${base}/api/runs/${runId}/build`, {
      method: "POST",
      headers: adminHeaders()
    })
  );
  return response.json();
}

export async function queueDeploy(runId: string) {
  const base = apiBase();
  const response = await ensureOk(
    await fetch(`${base}/api/runs/${runId}/deploy`, {
      method: "POST",
      headers: adminHeaders()
    })
  );
  return response.json();
}

export async function invokeTest(runId: string, payload: {
  operationId?: string;
  method: string;
  path: string;
  payload?: Record<string, unknown>;
  headers?: Record<string, string>;
}) {
  const base = apiBase();
  const response = await ensureOk(
    await fetch(`${base}/api/runs/${runId}/test-invocations`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...adminHeaders()
      },
      body: JSON.stringify(payload)
    })
  );
  return response.json();
}

export async function getEventArtifacts(runId: string) {
  const base = apiBase();
  const response = await ensureOk(await fetch(`${base}/api/runs/${runId}/event-artifacts`, { cache: "no-store" }));
  return response.json();
}

export async function getSettings(): Promise<SettingsView> {
  const base = apiBase();
  const response = await ensureOk(
    await fetch(`${base}/api/settings`, {
      headers: adminHeaders(),
      cache: "no-store"
    })
  );
  return response.json();
}

export async function saveSettings(payload: Record<string, unknown>): Promise<SettingsView> {
  const base = apiBase();
  const response = await ensureOk(
    await fetch(`${base}/api/settings`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        ...adminHeaders()
      },
      body: JSON.stringify(payload)
    })
  );
  return response.json();
}

export async function testLiteLlmSettings(payload: {
  litellmBaseUrl?: string;
  litellmApiKey?: string;
  litellmModel?: string;
}): Promise<LiteLlmTestResult> {
  const base = apiBase();
  const response = await ensureOk(
    await fetch(`${base}/api/settings/litellm/test`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...adminHeaders()
      },
      body: JSON.stringify(payload)
    })
  );
  return response.json();
}

export async function listSchemaPacks(): Promise<SchemaPackSummary[]> {
  const base = apiBase();
  const response = await ensureOk(
    await fetch(`${base}/api/schema-packs`, { cache: "no-store" })
  );
  return response.json();
}

export async function getSchemaPack(schemaPackId: string): Promise<SchemaPack> {
  const base = apiBase();
  const response = await ensureOk(
    await fetch(`${base}/api/schema-packs/${schemaPackId}`, { cache: "no-store" })
  );
  return response.json();
}

export async function createSchemaPack(payload: {
  name: string;
  schemaFormat: SchemaPackFormat;
  version?: string;
  messageType?: string;
  industry?: string;
  rawContent: string;
  filename?: string;
  contentType?: string;
}): Promise<SchemaPack> {
  const base = apiBase();
  const response = await ensureOk(
    await fetch(`${base}/api/schema-packs`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...adminHeaders()
      },
      body: JSON.stringify(payload)
    })
  );
  return response.json();
}

export async function deleteSchemaPack(schemaPackId: string): Promise<void> {
  const base = apiBase();
  await ensureOk(
    await fetch(`${base}/api/schema-packs/${schemaPackId}`, {
      method: "DELETE",
      headers: adminHeaders()
    })
  );
}

export function runStreamUrl(runId: string) {
  return `${apiBase()}/api/runs/${runId}/stream`;
}

export function eventStreamUrl(runId: string) {
  return `${apiBase()}/api/runs/${runId}/event-stream`;
}
