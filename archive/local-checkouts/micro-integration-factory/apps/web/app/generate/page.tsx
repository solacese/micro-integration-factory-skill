"use client";

import { useEffect, useState } from "react";
import { createRun, getSourceTypes, uploadSpec } from "@/lib/api";

export default function GeneratePage() {
  const [file, setFile] = useState<File | null>(null);
  const [sourceType, setSourceType] = useState("openapi");
  const [sourceTypes, setSourceTypes] = useState<string[]>(["openapi"]);
  const [target, setTarget] = useState<"local_docker" | "ec2_docker_host" | "kubernetes_helm" | "ephemeral_ec2">("ephemeral_ec2");
  const [autoBuild, setAutoBuild] = useState(true);
  const [autoDeploy, setAutoDeploy] = useState(false);
  const [message, setMessage] = useState<string>("Upload a source file (OpenAPI, JSON Schema, etc.).");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    getSourceTypes().then(setSourceTypes).catch(() => {});
  }, []);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) return;
    setLoading(true);
    setMessage("Uploading source...");
    try {
      const upload = await uploadSpec(file, sourceType);
      setMessage(`Uploaded ${upload.filename}. Creating run...`);
      const run = await createRun({
        uploadId: upload.uploadId,
        deploymentTarget: target,
        autoBuild,
        autoDeploy
      });
      window.location.href = `/runs/${run.id}`;
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Upload failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="stack">
      <section className="panel">
        <span className="eyebrow">Upload / Generate</span>
        <h1 className="page-title">Turn a source specification into a working integration run.</h1>
        <p className="lead">
          The platform will parse the source, derive canonical topics and event artifacts, generate an MDK-native Java service,
          optionally run LiteLLM refinement, and then let you build and deploy it.
        </p>
      </section>

      <form className="two-column" onSubmit={onSubmit}>
        <section className="panel stack">
          <label className="input">
            <span>Source type</span>
            <select value={sourceType} onChange={(event) => setSourceType(event.target.value)}>
              {sourceTypes.map((st) => (
                <option key={st} value={st}>{st.replace(/_/g, " ")}</option>
              ))}
            </select>
          </label>
          <label className="input">
            <span>Source file</span>
            <input
              type="file"
              accept=".yaml,.yml,.json,.schema.json"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
          </label>
          <label className="input">
            <span>Deployment target</span>
            <select value={target} onChange={(event) => setTarget(event.target.value as typeof target)}>
              <option value="local_docker">Local Docker</option>
              <option value="ec2_docker_host">EC2 Docker Host</option>
              <option value="ephemeral_ec2">Ephemeral EC2</option>
              <option value="kubernetes_helm">Kubernetes / Helm</option>
            </select>
          </label>
          <label className="flex">
            <input type="checkbox" checked={autoBuild} onChange={(event) => setAutoBuild(event.target.checked)} />
            <span>Auto build after generation</span>
          </label>
          <label className="flex">
            <input type="checkbox" checked={autoDeploy} onChange={(event) => setAutoDeploy(event.target.checked)} />
            <span>Auto deploy after build</span>
          </label>
          <button className="button-primary" disabled={loading || !file} type="submit">
            {loading ? "Working..." : "Start Generation Run"}
          </button>
        </section>

        <aside className="panel stack">
          <span className="eyebrow">Status</span>
          <div className="card">
            <strong>{message}</strong>
          </div>
          <div className="card">
            <span className="eyebrow">Suggested inputs</span>
            <div className="pill-list">
              <span className="badge">stripe-webhook-demo.yaml</span>
              <span className="badge">petstore.yaml</span>
              <span className="badge">order.schema.json</span>
            </div>
          </div>
        </aside>
      </form>
    </main>
  );
}
