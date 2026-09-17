"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { RunStepper } from "@/components/run-stepper";
import type { EventLogRecord, GenerationRunSummary, TestFixture } from "@spec2event/shared";
import {
  createRun,
  getEventLogs,
  getRun,
  getSettings,
  invokeTest,
  uploadSpec,
} from "@/lib/api";

function prettyJson(value: unknown) {
  return JSON.stringify(value ?? {}, null, 2);
}

export default function HomePage() {
  const [password, setPassword] = useState("");
  const [authenticated, setAuthenticated] = useState(false);
  const [authMessage, setAuthMessage] = useState("Locked");
  const [uploadName, setUploadName] = useState<string | null>(null);
  const [run, setRun] = useState<GenerationRunSummary | null>(null);
  const [events, setEvents] = useState<EventLogRecord[]>([]);
  const [message, setMessage] = useState("Ready");
  const [activeFixtureId, setActiveFixtureId] = useState<string | null>(null);
  const [working, setWorking] = useState(false);
  const pollRef = useRef<number | null>(null);

  useEffect(() => {
    const saved = window.sessionStorage.getItem("demo-admin-password");
    if (!saved) return;
    setPassword(saved);
    getSettings()
      .then(() => {
        setAuthenticated(true);
        setAuthMessage("Unlocked");
      })
      .catch(() => {
        window.sessionStorage.removeItem("demo-admin-password");
      });
  }, []);

  useEffect(() => {
    if (!run?.id) return;
    const runId = run.id;
    let cancelled = false;

    async function refreshRunState() {
      try {
        const [nextRun, nextEvents] = await Promise.all([getRun(runId), getEventLogs(runId)]);
        if (cancelled) return;
        setRun(nextRun);
        setEvents(nextEvents);
        setMessage(nextRun.lastMessage ?? "Run updated");
      } catch (error) {
        if (cancelled) return;
        setMessage(error instanceof Error ? error.message : "Unable to refresh run");
      }
    }

    void refreshRunState();
    pollRef.current = window.setInterval(() => {
      void refreshRunState();
    }, 2000);

    return () => {
      cancelled = true;
      if (pollRef.current !== null) {
        window.clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [run?.id]);

  const fixtures = useMemo(() => run?.canonicalModel?.testFixtures ?? [], [run]);

  const deploymentUrl =
    run?.serviceUrl ??
    (run?.activeDeployment?.publicIp ? `http://${run.activeDeployment.publicIp}:8080` : null) ??
    run?.activeDeployment?.privateServiceUrl ??
    null;
  const runtimeLabel =
    run?.activeDeployment?.status === "completed" ? "Running on EC2" : "Deploying to EC2";

  async function unlockDemo() {
    window.sessionStorage.setItem("demo-admin-password", password);
    try {
      await getSettings();
      setAuthenticated(true);
      setAuthMessage("Unlocked");
    } catch (error) {
      window.sessionStorage.removeItem("demo-admin-password");
      setAuthenticated(false);
      setAuthMessage(error instanceof Error ? error.message : "Invalid demo password");
    }
  }

  async function startRun(file: File) {
    setWorking(true);
    setUploadName(file.name);
    setMessage(`Uploading ${file.name}`);
    setEvents([]);
    setActiveFixtureId(null);
    try {
      const upload = await uploadSpec(file);
      setMessage("Generating");
      const nextRun = await createRun({
        uploadId: upload.uploadId,
        deploymentTarget: "ephemeral_ec2",
        autoBuild: true,
        autoDeploy: true,
      });
      const hydrated = await getRun(nextRun.id);
      setRun(hydrated);
      setMessage(hydrated.lastMessage ?? "Run created");
    } catch (error) {
      setUploadName(null);
      setMessage(error instanceof Error ? error.message : "Unable to start the run");
    } finally {
      setWorking(false);
    }
  }

  function handleFileSelected(file: File | null) {
    if (!file || !authenticated || working) return;
    void startRun(file);
  }

  async function triggerFixture(fixture: TestFixture) {
    if (!run?.id) return;
    setWorking(true);
    setActiveFixtureId(fixture.operationId);
    try {
      const response = await invokeTest(run.id, {
        operationId: fixture.operationId,
        method: fixture.method,
        path: fixture.path,
        payload: fixture.payload ?? {},
      });
      setMessage(`Invocation ${response.responseStatus}`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Invocation failed");
    } finally {
      setWorking(false);
    }
  }

  return (
    <main className="stack minimal-main">
      <section className={`minimal-hero${run ? " minimal-hero-compact" : ""}`}>
        <div className="hero-mark" />
        <span className="eyebrow">Solace Demo</span>
        <h1 className="minimal-title">Event Micro Integration Factory</h1>

        {!run ? (
          <div className="upload-panel">
            {!authenticated ? (
              <div className="unlock-row">
                <input
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="Admin password"
                />
                <button
                  className="button-primary"
                  disabled={!password}
                  onClick={unlockDemo}
                  type="button"
                >
                  Unlock
                </button>
              </div>
            ) : null}

            {authenticated && !working ? (
              <label className="upload-drop upload-drop-large">
                <input
                  accept=".yaml,.yml,.json"
                  disabled={!authenticated || working}
                  onChange={(event) => {
                    const nextFile = event.target.files?.[0] ?? null;
                    event.currentTarget.value = "";
                    handleFileSelected(nextFile);
                  }}
                  type="file"
                />
                <span>Upload spec</span>
              </label>
            ) : null}

            {authenticated && working ? (
              <div className="boot-panel">
                <div className="boot-line">
                  <strong>{uploadName ?? "Preparing run"}</strong>
                  <span className="muted">{message}</span>
                </div>
                <div className="progress-track progress-track-boot" aria-hidden="true">
                  <div className="progress-fill progress-fill-boot" />
                </div>
              </div>
            ) : null}

            <div className="status-strip">
              <span className="status-pill">{authMessage}</span>
              <span className="status-text">{message}</span>
            </div>
          </div>
        ) : null}
      </section>

      {run ? (
        <section className="stack">
          <article className="panel stack">
            <div className="section-head">
              <div className="panel-title">
                <strong>{run.serviceName}</strong>
                <span className="muted">{run.deploymentTarget}</span>
              </div>
              <span className="badge">{run.status}</span>
            </div>
            <div className="muted">{message}</div>
            <RunStepper run={run} />
          </article>

          <section className="full-bleed lower-stage">
            <div className="runtime-grid">
              <article className="panel lower-panel actions-panel">
                <div className="lower-panel-head">
                  <div className="section-head">
                    <strong>Trigger Events</strong>
                    <span className="muted">{fixtures.length}</span>
                  </div>
                </div>

                <div className="lower-panel-body stack">
                  {fixtures.length ? (
                    <div className="action-rail">
                      {fixtures.map((fixture) => (
                        <button
                          className={
                            fixture.operationId === activeFixtureId
                              ? "action-button action-button-active"
                              : "action-button"
                          }
                          disabled={!authenticated || !deploymentUrl || working}
                          key={fixture.operationId}
                          onClick={() => {
                            void triggerFixture(fixture);
                          }}
                          type="button"
                        >
                          <span className="action-label">{fixture.label}</span>
                          <span className="action-meta">{fixture.operationId}</span>
                        </button>
                      ))}
                    </div>
                  ) : (
                    <div className="events-empty">Waiting for generated test inputs.</div>
                  )}
                </div>
              </article>

              <article className="panel lower-panel">
                <div className="lower-panel-head">
                  <div className="section-head">
                    <strong>Custom Micro Integration on EC2</strong>
                  </div>
                </div>

                <div className="lower-panel-body stack">
                  <div className="table-row columns-2">
                    <div>
                      <strong>Status</strong>
                      <div className="muted">{runtimeLabel}</div>
                    </div>
                    <div>
                      <strong>Instance</strong>
                      <div className="muted">{run.activeDeployment?.instanceId ?? "Pending"}</div>
                    </div>
                  </div>

                  <div className="table-row columns-2">
                    <div>
                      <strong>Expires</strong>
                      <div className="muted">{run.activeDeployment?.expiresAt ?? "Pending"}</div>
                    </div>
                    <div>
                      <strong>Image</strong>
                      <div className="muted">{run.imageTag ?? "Building"}</div>
                    </div>
                    <div>
                      <strong>Topics</strong>
                      <div className="muted">{run.canonicalModel?.topics.length ?? 0}</div>
                    </div>
                  </div>

                  <div className="runtime-surface">
                    <div className="runtime-line">
                      <span>Runtime</span>
                      <strong>{runtimeLabel}</strong>
                    </div>
                    <div className="runtime-line">
                      <span>Broker</span>
                      <strong>Solace PubSub+</strong>
                    </div>
                    <div className="runtime-line">
                      <span>Mode</span>
                      <strong>HTTP to event bridge</strong>
                    </div>
                  </div>
                </div>
              </article>

              <article className="panel lower-panel events-panel">
                <div className="lower-panel-head">
                  <div className="section-head">
                    <strong>Events</strong>
                    <span className="muted">{events.length}</span>
                  </div>
                </div>

                <div className="lower-panel-body event-stream">
                  {events.length ? (
                    <div className="timeline compact-timeline">
                      {events.map((event) => (
                        <div className="timeline-item" key={event.id}>
                          <div className="flex-between">
                            <strong>{event.stage}</strong>
                            <span className="badge">{event.correlationId}</span>
                          </div>
                          {event.topicName ? <div className="muted">{event.topicName}</div> : null}
                          <pre className="code-block">{prettyJson(event.payload)}</pre>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="events-empty events-empty-stream">
                      Events will appear here once the integration is invoked.
                    </div>
                  )}
                </div>
              </article>
            </div>
          </section>
        </section>
      ) : null}
    </main>
  );
}
