"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import type { GenerationRunSummary } from "@spec2event/shared";
import { getRun, queueBuild, queueDeploy, runStreamUrl } from "@/lib/api";
import { RunStepper } from "@/components/run-stepper";

export default function RunDetailPage() {
  const params = useParams<{ id: string }>();
  const runId = params.id;
  const [run, setRun] = useState<GenerationRunSummary | null>(null);
  const [message, setMessage] = useState("Loading run...");

  useEffect(() => {
    if (!runId) return;
    getRun(runId)
      .then((value) => {
        setRun(value);
        setMessage(value.lastMessage ?? "Run loaded");
      })
      .catch((error) => setMessage(error instanceof Error ? error.message : "Failed to load run"));
  }, [runId]);

  useEffect(() => {
    if (!runId) return;
    const source = new EventSource(runStreamUrl(runId));
    source.onmessage = (event) => {
      const next = JSON.parse(event.data) as GenerationRunSummary;
      setRun(next);
      setMessage(next.lastMessage ?? "Run updated");
    };
    return () => source.close();
  }, [runId]);

  if (!run) {
    return (
      <main className="panel">
        <p className="muted">{message}</p>
      </main>
    );
  }

  return (
    <main className="stack">
      <section className="panel stack">
        <div className="flex-between">
          <div>
            <span className="eyebrow">Run Detail</span>
            <h1 className="page-title">{run.serviceName}</h1>
            <p className="muted">{message}</p>
          </div>
          <div className="flex">
            <button
              className="button-secondary"
              onClick={() => queueBuild(run.id).catch(console.error)}
            >
              Queue build
            </button>
            <button
              className="button-primary"
              onClick={() => queueDeploy(run.id).catch(console.error)}
            >
              Queue deploy
            </button>
          </div>
        </div>
        <RunStepper run={run} />
      </section>

      <section className="two-column">
        <article className="panel stack">
          <span className="eyebrow">Deployment</span>
          <div className="table-row columns-2">
            <div>
              <strong>Status</strong>
              <div className="muted">{run.status}</div>
            </div>
            <div>
              <strong>Target</strong>
              <div className="muted">{run.deploymentTarget}</div>
            </div>
          </div>
          <div className="table-row columns-2">
            <div>
              <strong>Image</strong>
              <div className="muted">{run.imageTag ?? "Not built yet"}</div>
            </div>
            <div>
              <strong>Service URL</strong>
              <div className="muted">{run.serviceUrl ?? "Not deployed yet"}</div>
            </div>
          </div>
        </article>

        <article className="panel stack">
          <span className="eyebrow">Derived event model</span>
          <div className="pill-list">
            {run.canonicalModel?.topics?.map((topic) => (
              <span className="badge" key={topic}>
                {topic}
              </span>
            )) ?? <span className="muted">No topics derived yet.</span>}
          </div>
        </article>
      </section>

      <section className="panel stack">
        <span className="eyebrow">Steps</span>
        <div className="timeline">
          {run.steps.map((step) => (
            <div className="timeline-item" data-stage={step.status} key={step.id}>
              <div className="flex-between">
                <strong>{step.stepName}</strong>
                <span className="badge">{step.status}</span>
              </div>
              <div className="muted">{step.message}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="three-column">
        <Link className="card" href={`/runs/${run.id}/artifacts`}>
          <span className="eyebrow">Inspect</span>
          <h3>Artifacts</h3>
          <p className="muted">Browse and edit the generated MDK project files.</p>
        </Link>
        <Link className="card" href={`/runs/${run.id}/test`}>
          <span className="eyebrow">Live test</span>
          <h3>Invoke API and stream events</h3>
          <p className="muted">
            Send generated requests or Stripe fixtures and observe event consumption.
          </p>
        </Link>
        <Link className="card" href={`/runs/${run.id}/event-artifacts`}>
          <span className="eyebrow">Portal</span>
          <h3>Event artifacts</h3>
          <p className="muted">See topics, schemas, applications, and Event Portal sync outcomes.</p>
        </Link>
      </section>
    </main>
  );
}
