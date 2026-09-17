"use client";

import { useState } from "react";
import {
  createRun,
  discoverDatabaseSource,
  uploadConnectorSpec,
  uploadSpec
} from "@/lib/api";

type DeploymentTarget =
  | "local_docker"
  | "ec2_docker_host"
  | "kubernetes_helm"
  | "ephemeral_ec2";
type SourceKind = "openapi" | "database" | "connector";

const CONNECTOR_BLUEPRINTS = {
  webhook: {
    sourceMode: "webhook",
    name: "Shopify Returns Webhook",
    version: "1.0.0",
    description: "Accept return webhooks and publish canonical return lifecycle events.",
    applicationDomainName: "Commerce Source Integrations",
    topicRoot: "commerce",
    sourceDetails: {
      publicPath: "/webhooks/shopify/returns"
    },
    events: [
      {
        name: "ReturnRequested",
        entity: "return",
        action: "requested",
        payloadExample: {
          returnId: "ret_123",
          orderId: "ord_456",
          status: "requested"
        }
      }
    ]
  },
  file: {
    sourceMode: "file",
    name: "Nightly Inventory Drops",
    version: "1.0.0",
    description: "Poll CSV or JSON inventory drops and publish stock events.",
    applicationDomainName: "Supply Chain Source Integrations",
    topicRoot: "supply",
    sourceDetails: {
      inputDirectory: "./demo/inventory/inbox",
      archiveDirectory: "./demo/inventory/archive",
      pollIntervalSeconds: 30
    },
    events: [
      {
        name: "InventorySnapshotObserved",
        entity: "inventory",
        action: "observed",
        payloadExample: {
          sku: "SKU-100",
          quantity: 42,
          warehouse: "paris"
        }
      }
    ]
  },
  kafka: {
    sourceMode: "kafka",
    name: "Orders Topic Bridge",
    version: "1.0.0",
    description: "Bridge upstream Kafka orders into Solace canonical order events.",
    applicationDomainName: "Commerce Source Integrations",
    topicRoot: "commerce",
    sourceDetails: {
      stream: "orders.events",
      consumerGroup: "solace-orders-bridge",
      clientId: "orders-bridge"
    },
    events: [
      {
        name: "OrderCreated",
        entity: "order",
        action: "created",
        payloadExample: {
          orderId: "ord_789",
          customerId: "cus_001",
          total: 199.5
        }
      }
    ]
  },
  mqtt: {
    sourceMode: "mqtt",
    name: "Warehouse Sensor Bridge",
    version: "1.0.0",
    description: "Bridge sensor telemetry into Solace operational events.",
    applicationDomainName: "Operations Integrations",
    topicRoot: "operations",
    sourceDetails: {
      topic: "warehouse/+/telemetry",
      clientId: "warehouse-sensor-bridge"
    },
    events: [
      {
        name: "SensorTelemetryObserved",
        entity: "sensor",
        action: "observed",
        payloadExample: {
          sensorId: "sensor-17",
          temperatureCelsius: 21.4,
          humidityPercent: 48
        }
      }
    ]
  }
} as const;

const DEFAULT_CONNECTOR_BLUEPRINT = JSON.stringify(CONNECTOR_BLUEPRINTS.kafka, null, 2);

export default function GeneratePage() {
  const [sourceKind, setSourceKind] = useState<SourceKind>("openapi");
  const [file, setFile] = useState<File | null>(null);
  const [target, setTarget] = useState<DeploymentTarget>("ephemeral_ec2");
  const [autoBuild, setAutoBuild] = useState(true);
  const [autoDeploy, setAutoDeploy] = useState(false);
  const [message, setMessage] = useState<string>(
    "Choose an intake path and generate a Solace micro-integration."
  );
  const [loading, setLoading] = useState(false);
  const [connectorSpec, setConnectorSpec] = useState(DEFAULT_CONNECTOR_BLUEPRINT);
  const [databaseForm, setDatabaseForm] = useState({
    host: "",
    port: "5432",
    databaseName: "",
    username: "",
    password: "",
    schema: "public",
    preferredTable: "products",
    sslmode: "require",
    applicationDomainName: "Commerce Source Integrations",
    topicRoot: "commerce"
  });

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);

    try {
      let upload: { uploadId: string; filename: string; serviceName: string };
      if (sourceKind === "openapi") {
        if (!file) {
          throw new Error("Choose an OpenAPI file before starting a run.");
        }
        setMessage("Uploading OpenAPI contract...");
        upload = await uploadSpec(file);
      } else if (sourceKind === "database") {
        setMessage("Inspecting database source...");
        upload = await discoverDatabaseSource({
          host: databaseForm.host,
          port: Number(databaseForm.port),
          databaseName: databaseForm.databaseName,
          username: databaseForm.username,
          password: databaseForm.password,
          schema: databaseForm.schema,
          preferredTable: databaseForm.preferredTable,
          sslmode: databaseForm.sslmode,
          applicationDomainName: databaseForm.applicationDomainName,
          topicRoot: databaseForm.topicRoot
        });
      } else {
        setMessage("Uploading connector blueprint...");
        upload = await uploadConnectorSpec(JSON.parse(connectorSpec) as Parameters<
          typeof uploadConnectorSpec
        >[0]);
      }

      setMessage(`Prepared ${upload.filename}. Creating run...`);
      const run = await createRun({
        uploadId: upload.uploadId,
        deploymentTarget: target,
        autoBuild,
        autoDeploy
      });
      window.location.href = `/runs/${run.id}`;
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Generation setup failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="stack">
      <section className="panel">
        <span className="eyebrow">Upload / Generate</span>
        <h1 className="page-title">Build broader Solace micro-integrations from more than OpenAPI.</h1>
        <p className="lead">
          Use a contract upload, database discovery, or a connector blueprint to generate an MDK-native runtime,
          then build it and hold deployment behind explicit human approval.
        </p>
      </section>

      <form className="two-column" onSubmit={onSubmit}>
        <section className="panel stack">
          <label className="input">
            <span>Source intake</span>
            <select value={sourceKind} onChange={(event) => setSourceKind(event.target.value as SourceKind)}>
              <option value="openapi">OpenAPI contract</option>
              <option value="database">Database discovery</option>
              <option value="connector">Connector blueprint</option>
            </select>
          </label>

          {sourceKind === "openapi" ? (
            <label className="input">
              <span>OpenAPI file</span>
              <input
                type="file"
                accept=".yaml,.yml,.json"
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              />
            </label>
          ) : null}

          {sourceKind === "database" ? (
            <>
              <label className="input">
                <span>Database host</span>
                <input
                  value={databaseForm.host}
                  onChange={(event) => setDatabaseForm((current) => ({ ...current, host: event.target.value }))}
                />
              </label>
              <div className="two-column">
                <label className="input">
                  <span>Port</span>
                  <input
                    value={databaseForm.port}
                    onChange={(event) => setDatabaseForm((current) => ({ ...current, port: event.target.value }))}
                  />
                </label>
                <label className="input">
                  <span>Database name</span>
                  <input
                    value={databaseForm.databaseName}
                    onChange={(event) =>
                      setDatabaseForm((current) => ({ ...current, databaseName: event.target.value }))
                    }
                  />
                </label>
              </div>
              <div className="two-column">
                <label className="input">
                  <span>Username</span>
                  <input
                    value={databaseForm.username}
                    onChange={(event) =>
                      setDatabaseForm((current) => ({ ...current, username: event.target.value }))
                    }
                  />
                </label>
                <label className="input">
                  <span>Password</span>
                  <input
                    type="password"
                    value={databaseForm.password}
                    onChange={(event) =>
                      setDatabaseForm((current) => ({ ...current, password: event.target.value }))
                    }
                  />
                </label>
              </div>
              <div className="two-column">
                <label className="input">
                  <span>Schema</span>
                  <input
                    value={databaseForm.schema}
                    onChange={(event) => setDatabaseForm((current) => ({ ...current, schema: event.target.value }))}
                  />
                </label>
                <label className="input">
                  <span>Preferred table</span>
                  <input
                    value={databaseForm.preferredTable}
                    onChange={(event) =>
                      setDatabaseForm((current) => ({ ...current, preferredTable: event.target.value }))
                    }
                  />
                </label>
              </div>
              <div className="two-column">
                <label className="input">
                  <span>Application domain</span>
                  <input
                    value={databaseForm.applicationDomainName}
                    onChange={(event) =>
                      setDatabaseForm((current) => ({
                        ...current,
                        applicationDomainName: event.target.value
                      }))
                    }
                  />
                </label>
                <label className="input">
                  <span>Topic root</span>
                  <input
                    value={databaseForm.topicRoot}
                    onChange={(event) =>
                      setDatabaseForm((current) => ({ ...current, topicRoot: event.target.value }))
                    }
                  />
                </label>
              </div>
            </>
          ) : null}

          {sourceKind === "connector" ? (
            <>
              <div className="flex" style={{ flexWrap: "wrap" }}>
                <button
                  className="button-secondary"
                  onClick={() => setConnectorSpec(JSON.stringify(CONNECTOR_BLUEPRINTS.webhook, null, 2))}
                  type="button"
                >
                  Load Webhook
                </button>
                <button
                  className="button-secondary"
                  onClick={() => setConnectorSpec(JSON.stringify(CONNECTOR_BLUEPRINTS.file, null, 2))}
                  type="button"
                >
                  Load File
                </button>
                <button
                  className="button-secondary"
                  onClick={() => setConnectorSpec(JSON.stringify(CONNECTOR_BLUEPRINTS.kafka, null, 2))}
                  type="button"
                >
                  Load Kafka
                </button>
                <button
                  className="button-secondary"
                  onClick={() => setConnectorSpec(JSON.stringify(CONNECTOR_BLUEPRINTS.mqtt, null, 2))}
                  type="button"
                >
                  Load MQTT
                </button>
              </div>
              <label className="textarea">
                <span>Connector blueprint JSON</span>
                <textarea value={connectorSpec} onChange={(event) => setConnectorSpec(event.target.value)} />
              </label>
            </>
          ) : null}

          <label className="input">
            <span>Deployment target</span>
            <select value={target} onChange={(event) => setTarget(event.target.value as DeploymentTarget)}>
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
            <span>Auto queue deploy after build</span>
          </label>
          <button className="button-primary" disabled={loading || (sourceKind === "openapi" && !file)} type="submit">
            {loading ? "Working..." : "Start Generation Run"}
          </button>
        </section>

        <aside className="panel stack">
          <span className="eyebrow">Status</span>
          <div className="card">
            <strong>{message}</strong>
          </div>
          <div className="card stack">
            <span className="eyebrow">Supported paths</span>
            <div className="pill-list">
              <span className="badge">OpenAPI ingress</span>
              <span className="badge">Database polling</span>
              <span className="badge">Webhook starter</span>
              <span className="badge">File polling</span>
              <span className="badge">MQTT bridge starter</span>
              <span className="badge">Kafka bridge starter</span>
              <span className="badge">Queue / AMQP / JMS starters</span>
            </div>
          </div>
          <div className="card">
            <span className="eyebrow">Approval gate</span>
            <p className="muted">
              Deploys now stop in an approval state until a human approves the run from the detail page.
            </p>
          </div>
        </aside>
      </form>
    </main>
  );
}
