"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import type { EventLogRecord, GenerationRunSummary } from "@spec2event/shared";
import { eventStreamUrl, getRun, invokeTest } from "@/lib/api";

const STRIPE_FIXTURE = {
  id: "evt_demo_payment_intent_succeeded",
  type: "payment_intent.succeeded",
  data: {
    object: {
      id: "pi_demo_123",
      amount: 1299,
      currency: "usd",
      status: "succeeded",
    },
  },
};

export default function RunTestPage() {
  const params = useParams<{ id: string }>();
  const runId = params.id;
  const [run, setRun] = useState<GenerationRunSummary | null>(null);
  const [operationId, setOperationId] = useState("");
  const [method, setMethod] = useState("POST");
  const [path, setPath] = useState("/webhooks/stripe/payment");
  const [payload, setPayload] = useState(JSON.stringify(STRIPE_FIXTURE, null, 2));
  const [events, setEvents] = useState<EventLogRecord[]>([]);
  const [message, setMessage] = useState("Loading run...");

  useEffect(() => {
    if (!runId) return;
    getRun(runId)
      .then((value) => {
        setRun(value);
        const firstOp = value.canonicalModel?.operations?.[0];
        if (firstOp) {
          setOperationId(firstOp.operationId);
          setMethod(firstOp.method);
          setPath(firstOp.path);
        }
      })
      .catch((error) => setMessage(error instanceof Error ? error.message : "Unable to load run"));
  }, [runId]);

  useEffect(() => {
    if (!runId) return;
    const source = new EventSource(eventStreamUrl(runId));
    source.onmessage = (event) => {
      const next = JSON.parse(event.data) as EventLogRecord;
      setEvents((current) => [...current, next].slice(-50));
    };
    return () => source.close();
  }, [runId]);

  const operations = useMemo(() => run?.canonicalModel?.operations ?? [], [run]);

  return (
    <main className="two-column">
      <section className="panel stack">
        <div>
          <span className="eyebrow">Live test</span>
          <h1 className="page-title">Invoke the generated API and observe event flow.</h1>
        </div>
        <label className="input">
          <span>Operation</span>
          <select
            value={operationId}
            onChange={(event) => {
              const selected = operations.find(
                (operation) => operation.operationId === event.target.value,
              );
              if (!selected) return;
              setOperationId(selected.operationId);
              setMethod(selected.method);
              setPath(selected.path);
            }}
          >
            {operations.map((operation) => (
              <option key={operation.operationId} value={operation.operationId}>
                {operation.method} {operation.path}
              </option>
            ))}
            <option value="stripe-webhook-payment">POST /webhooks/stripe/payment</option>
          </select>
        </label>
        <label className="input">
          <span>HTTP method</span>
          <input value={method} onChange={(event) => setMethod(event.target.value)} />
        </label>
        <label className="input">
          <span>Path</span>
          <input value={path} onChange={(event) => setPath(event.target.value)} />
        </label>
        <label className="textarea">
          <span>JSON payload</span>
          <textarea value={payload} onChange={(event) => setPayload(event.target.value)} />
        </label>
        <div className="flex">
          <button
            className="button-primary"
            onClick={async () => {
              setMessage("Invoking generated service...");
              try {
                const response = await invokeTest(runId, {
                  operationId,
                  method,
                  path,
                  payload: JSON.parse(payload),
                });
                setMessage(`Invocation ${response.correlationId} returned HTTP ${response.responseStatus}`);
              } catch (error) {
                setMessage(error instanceof Error ? error.message : "Invocation failed");
              }
            }}
            type="button"
          >
            Invoke API
          </button>
          <button
            className="button-secondary"
            onClick={() => setPayload(JSON.stringify(STRIPE_FIXTURE, null, 2))}
            type="button"
          >
            Load Stripe fixture
          </button>
        </div>
        <div className="card">
          <strong>{message}</strong>
          <div className="muted">Service URL: {run?.serviceUrl ?? "Deploy first"}</div>
        </div>
      </section>
      <section className="panel stack">
        <span className="eyebrow">Live event timeline</span>
        <div className="timeline">
          {events.map((event) => (
            <div className="timeline-item" key={event.id}>
              <div className="flex-between">
                <strong>{event.stage}</strong>
                <span className="badge">{event.correlationId}</span>
              </div>
              <div className="muted">{event.topicName ?? "no topic"}</div>
              <pre className="code-block">{JSON.stringify(event.payload, null, 2)}</pre>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}
