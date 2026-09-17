"use client";

import type {
  ArtifactDetail,
  ArtifactSummary,
  EventLogRecord,
  GenerationRunSummary,
  SettingsView
} from "@spec2event/shared";

function apiBase() {
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (configured) {
    return configured;
  }
  if (typeof window !== "undefined") {
    const { hostname, port } = window.location;
    if ((hostname === "localhost" || hostname === "127.0.0.1") && port === "3000") {
      return "http://127.0.0.1:8000";
    }
  }
  return "";
}

function adminHeaders(): HeadersInit {
  if (typeof window === "undefined") {
    return {};
  }
  const password = window.sessionStorage.getItem("demo-admin-password");
  return password ? { "X-Demo-Admin-Password": password } : {};
}

async function ensureOk(response: Response) {
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response;
}

export async function uploadSpec(file: File) {
  const formData = new FormData();
  formData.append("file", file);
  const base = apiBase();
  const response = await ensureOk(
    await fetch(`${base}/api/uploads`, {
      // requests resolve through nginx in production and directly to FastAPI in local dev
      method: "POST",
      headers: adminHeaders(),
      body: formData
    })
  );
  return response.json();
}

export async function discoverDatabaseSource(payload: {
  databaseUrl?: string;
  host?: string;
  port?: number;
  databaseName?: string;
  username?: string;
  password?: string;
  schema?: string;
  preferredTable?: string;
  sslmode?: string;
  applicationDomainName?: string;
  topicRoot?: string;
}) {
  const base = apiBase();
  const response = await ensureOk(
    await fetch(`${base}/api/uploads/database/discover`, {
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

export async function uploadConnectorSpec(payload: {
  sourceMode:
    | "webhook"
    | "file"
    | "mqtt"
    | "kafka"
    | "queue"
    | "amqp"
    | "jms"
    | "sftp"
    | "ftp"
    | "object_storage";
  name: string;
  version?: string;
  description?: string;
  applicationDomainName?: string;
  connectorPattern?: string;
  topicRoot?: string;
  sourceDetails?: Record<string, unknown>;
  events?: Array<{
    name: string;
    entity?: string;
    action?: string;
    summary?: string;
    topicName?: string;
    schemaName?: string;
    payloadExample?: Record<string, unknown>;
  }>;
}) {
  const base = apiBase();
  const response = await ensureOk(
    await fetch(`${base}/api/uploads/connector-spec`, {
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

export async function approveDeployment(runId: string, payload?: {
  notes?: string;
  approvedBy?: string;
}): Promise<GenerationRunSummary> {
  const base = apiBase();
  const response = await ensureOk(
    await fetch(`${base}/api/runs/${runId}/approve-deployment`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...adminHeaders()
      },
      body: JSON.stringify(payload ?? {})
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

export function runStreamUrl(runId: string) {
  return `${apiBase()}/api/runs/${runId}/stream`;
}

export function eventStreamUrl(runId: string) {
  return `${apiBase()}/api/runs/${runId}/event-stream`;
}
