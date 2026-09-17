"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { GenerationRunSummary } from "@spec2event/shared";
import { listRuns } from "@/lib/api";

export default function RunsPage() {
  const [runs, setRuns] = useState<GenerationRunSummary[]>([]);
  const [message, setMessage] = useState("Loading runs...");

  useEffect(() => {
    listRuns()
      .then((items) => {
        setRuns(items);
        setMessage(items.length ? "Recent runs" : "No runs yet");
      })
      .catch((error) => setMessage(error instanceof Error ? error.message : "Unable to load runs"));
  }, []);

  return (
    <main className="stack">
      <section className="panel">
        <span className="eyebrow">Runs</span>
        <h1 className="page-title">Generation, build, deploy, and live test runs.</h1>
        <p className="muted">{message}</p>
      </section>
      <section className="grid-table">
        {runs.map((run) => (
          <Link key={run.id} href={`/runs/${run.id}`} className="table-row columns-3">
            <div>
              <strong>{run.serviceName}</strong>
              <div className="muted">{run.id}</div>
            </div>
            <div>
              <span className="badge">{run.status}</span>
              <div className="muted">{run.deploymentTarget}</div>
            </div>
            <div>
              <div>{new Date(run.createdAt).toLocaleString()}</div>
              <div className="muted">{run.lastMessage}</div>
            </div>
          </Link>
        ))}
      </section>
    </main>
  );
}
