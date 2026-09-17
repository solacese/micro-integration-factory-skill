"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import type { EventPortalSyncRecord } from "@spec2event/shared";
import { getEventArtifacts } from "@/lib/api";

interface EventArtifactsData {
  canonicalModel?: {
    topics?: string[];
    schemaNames?: string[];
  } | null;
  portalSyncs: EventPortalSyncRecord[];
}

export default function EventArtifactsPage() {
  const params = useParams<{ id: string }>();
  const runId = params.id;
  const [data, setData] = useState<EventArtifactsData | null>(null);
  const [message, setMessage] = useState("Loading event artifacts...");

  useEffect(() => {
    if (!runId) return;
    getEventArtifacts(runId)
      .then((value) => {
        setData(value);
        setMessage("Derived topics, schemas, applications, and Event Portal sync state.");
      })
      .catch((error) =>
        setMessage(error instanceof Error ? error.message : "Unable to load event artifacts"),
      );
  }, [runId]);

  return (
    <main className="stack">
      <section className="panel">
        <span className="eyebrow">Event artifacts</span>
        <h1 className="page-title">Runtime topics plus Event Portal visibility.</h1>
        <p className="muted">{message}</p>
      </section>
      <section className="two-column">
        <article className="panel stack">
          <strong>Topics</strong>
          <div className="pill-list">
            {data?.canonicalModel?.topics?.map((topic: string) => (
              <span className="badge" key={topic}>
                {topic}
              </span>
            )) ?? <span className="muted">No topics available.</span>}
          </div>
          <strong>Schemas</strong>
          <div className="pill-list">
            {data?.canonicalModel?.schemaNames?.map((schema: string) => (
              <span className="badge" key={schema}>
                {schema}
              </span>
            )) ?? <span className="muted">No schemas available.</span>}
          </div>
        </article>
        <article className="panel stack">
          <strong>Event Portal sync</strong>
          <div className="timeline">
            {(data?.portalSyncs ?? []).map((sync) => (
              <div className="timeline-item" key={sync.id}>
                <div className="flex-between">
                  <strong>{sync.artifactName}</strong>
                  <span className="badge">{sync.status}</span>
                </div>
                <div className="muted">{sync.artifactType}</div>
                {sync.manualAction ? <pre className="code-block">{sync.manualAction}</pre> : null}
              </div>
            ))}
          </div>
        </article>
      </section>
    </main>
  );
}
