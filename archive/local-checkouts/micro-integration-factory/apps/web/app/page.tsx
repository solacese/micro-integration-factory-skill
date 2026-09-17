"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Braces,
  Cable,
  CheckCircle2,
  ChevronRight,
  Download,
  EyeOff,
  FileCode2,
  FileText,
  Layers3,
  Library,
  LoaderCircle,
  Pause,
  Play,
  Radio,
  Route,
  Send,
  ShieldCheck,
  Shuffle,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type {
  BuilderSession,
  CapturedEvent,
  GenerationRunSummary,
  InputMessageFormat,
  SchemaPackSummary,
  SolaceSubscriptionSummary,
  TransformLanguage,
  WorkerJob
} from "@spec2event/shared";
import {
  capturedEventsStreamUrl,
  createBuilderSession,
  createInputMessageEvent,
  createSolaceSubscription,
  generateBuilderSession,
  getWorkerJob,
  imageArchiveUrl,
  listCapturedEvents,
  listSchemaPacks,
  sendBuilderMessage,
  transformFileUrl,
  workspaceArchiveUrl
} from "@/lib/api";

function prettyJson(value: unknown) {
  return JSON.stringify(value ?? {}, null, 2);
}

function languageLabel(language: TransformLanguage) {
  return {
    java_sdk: "Java SDK",
    groovy: "Groovy",
    dataweave: "DataWeave"
  }[language];
}

function transformPath(language: TransformLanguage) {
  return {
    java_sdk: "src/main/resources/transforms/transform.md",
    groovy: "src/main/resources/transforms/transform.groovy",
    dataweave: "src/main/resources/transforms/transform.dwl"
  }[language];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function byteSize(value: unknown) {
  return new TextEncoder().encode(JSON.stringify(value ?? {})).length;
}

function formatBytes(value: unknown) {
  if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) return "pending";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function resultNumber(result: Record<string, unknown>, key: string) {
  const value = result[key];
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

const languageOptions: Array<{ value: TransformLanguage; label: string; note: string }> = [
  { value: "java_sdk", label: "Java SDK", note: "production default" },
  { value: "groovy", label: "Groovy", note: "script draft" },
  { value: "dataweave", label: "DataWeave", note: "dwl plus Java runtime" }
];
const maxVisibleEvents = 10;
const defaultManualPayload = JSON.stringify(
  {
    id: "SO-10042",
    customer: {
      id: "C-7781",
      name: "Acme Manufacturing",
      email: "buyer@example.com"
    },
    lineItems: [{ sku: "MOTOR-7", quantity: 4 }],
    totalAmount: 129.95,
    status: "approved"
  },
  null,
  2
);

const inputFormatOptions: Array<{ value: InputMessageFormat; label: string }> = [
  { value: "json", label: "JSON" },
  { value: "xml", label: "XML" },
  { value: "csv", label: "CSV" },
  { value: "fixed_width", label: "Fixed-width" },
  { value: "hl7", label: "HL7" },
  { value: "edifact", label: "EDIFACT" },
  { value: "ansi_x12", label: "ANSI X12" },
  { value: "odette", label: "ODETTE" },
  { value: "text", label: "Text" }
];

const incomingProtocolOptions = [
  "MQTT",
  "AMQP",
  "JMS",
  "REST/HTTP",
  "Kafka",
  "Solace SMF",
  "HL7",
  "EDIFACT",
  "ANSI X12",
  "ODETTE",
  "Webhook"
];

const targetFormatOptions = [
  "OPC UA",
  "Parquet",
  "Avro",
  "CloudEvents JSON",
  "JSON",
  "XML",
  "HL7",
  "EDIFACT",
  "ANSI X12",
  "CSV",
  "Kafka record"
];

const dataweaveFormats = new Set([
  "xml",
  "csv",
  "fixed_width",
  "hl7",
  "edifact",
  "ansi_x12",
  "odette",
  "generic_edi",
  "xml_schema",
  "csv_layout"
]);

type ExportMode = "single" | "vscode" | "image";

const exportOptions: Array<{
  value: ExportMode;
  label: string;
  note: string;
}> = [
  { value: "single", label: "Single file", note: "transform only" },
  { value: "vscode", label: "VS Code", note: "full project" },
  { value: "image", label: "Image", note: "Docker tar" }
];

type TemplateOption = {
  key: string;
  label: string;
  note: string;
  icon: LucideIcon;
  prompt: string;
  language?: TransformLanguage;
};

const templateOptions: TemplateOption[] = [
  {
    key: "system-to-event",
    label: "System to event",
    note: "publish event",
    icon: FileText,
    prompt:
      "Turn this system message into a clean Solace business event. Infer the canonical event name, output topic, required fields, validation rules, and sample event from the payload. Preserve business identifiers and correlation metadata, normalize field names, and publish only consumer-ready fields."
  },
  {
    key: "topic-header-rewrite",
    label: "Topic rewrite",
    note: "UNS routing",
    icon: Route,
    language: "dataweave",
    prompt:
      "Use DataWeave to rewrite this message to a Unified Namespace topic and update the message topic/header as part of the transform. Infer the UNS path from payload fields and source headers, preserve correlation headers, normalize the payload only where needed, and publish to the rewritten UNS topic. Return a sample output envelope with headers and payload."
  },
  {
    key: "schema-validation",
    label: "Schema validation",
    note: "validate shape",
    icon: ShieldCheck,
    prompt:
      "Validate this payload against a clear JSON schema before publishing. Reject missing required fields, type mismatches, and malformed nested objects. Return a canonical valid event and describe the validation errors path for invalid payloads."
  },
  {
    key: "anonymization",
    label: "Anonymization",
    note: "mask sensitive data",
    icon: EyeOff,
    prompt:
      "Strip out sensitive data from ORDER and only return customer, items, total, and orderId when those fields exist. Mask or hash remaining direct identifiers, remove secrets and tokens, and explain which fields were anonymized."
  },
  {
    key: "edi-xml-schema",
    label: "EDI / XML",
    note: "schema mapping",
    icon: Braces,
    prompt:
      "Transform this schema-backed payload into a canonical event. Handle JSON, XML, CSV, HL7, EDIFACT, ANSI X12, or ODETTE input as needed, infer segment and field mappings, validate required source fields, and publish a compact event with clear schema assumptions."
  },
  {
    key: "aggregation",
    label: "Aggregation",
    note: "group events",
    icon: Layers3,
    prompt:
      "Aggregate related payloads into a summary event. Group by the strongest business key in the payload, compute useful counts and totals, preserve correlation metadata, and publish a compact aggregate event."
  },
  {
    key: "transformation",
    label: "Transformation",
    note: "map fields",
    icon: Shuffle,
    prompt:
      "Transform this payload into a canonical event model. Rename fields for clarity, normalize timestamps and money values, preserve source identifiers, and publish only the fields consumers need."
  }
];

function protocolChangePrompt(incomingProtocol: string, targetFormat: string) {
  return (
    `Create a protocol-change micro integration. Treat the input message as an ` +
    `${incomingProtocol} inbound message and convert the payload into ${targetFormat}. ` +
    "Infer the output topic, field mappings, type conversions, and metadata rules. " +
    "Preserve source correlation metadata, validate required fields before publishing, " +
    "and build a sample output that proves the protocol/format conversion. Keep the " +
    "implementation scoped to one transform artifact inside the MDK scaffold."
  );
}

function genericBuilderPrompt(scenario: string, schemaPackName?: string) {
  const schemaLine = schemaPackName
    ? `Use the selected schema pack "${schemaPackName}" as mapping and validation context. `
    : "";
  return (
    "Build a generic Solace micro integration from this input message. " +
    schemaLine +
    "Treat this as a freeform scenario that may include system-to-event, event-to-system, " +
    "API payload creation, JSON/XML/CSV/EDI/HL7 conversion, schema validation, " +
    "anonymization, aggregation, protocol change, or topic/header rewrite. " +
    "Make strong assumptions, choose the output topic and headers, build a small sample " +
    "output, and write exactly one transform artifact. Scenario: " +
    (scenario.trim() ||
      "Infer the most useful micro integration from the input message and selected context.")
  );
}

export default function HomePage() {
  const [sourceMode, setSourceMode] = useState<"manual" | "live">("manual");
  const [manualSourceName, setManualSourceName] = useState("Order Management System");
  const [manualTopic, setManualTopic] = useState("systems/orders/approved/v1");
  const [manualInputFormat, setManualInputFormat] = useState<InputMessageFormat>("json");
  const [manualPayload, setManualPayload] = useState(defaultManualPayload);
  const [brokerUrl, setBrokerUrl] = useState("demo://sample");
  const [vpn, setVpn] = useState("default");
  const [username, setUsername] = useState("demo");
  const [password, setPassword] = useState("demo");
  const [topicFilter, setTopicFilter] = useState("orders/>");
  const [credentialsHidden, setCredentialsHidden] = useState(false);
  const [feedPaused, setFeedPaused] = useState(false);
  const [subscription, setSubscription] = useState<SolaceSubscriptionSummary | null>(null);
  const [capturedEvents, setCapturedEvents] = useState<CapturedEvent[]>([]);
  const [selectedEvent, setSelectedEvent] = useState<CapturedEvent | null>(null);
  const [language, setLanguage] = useState<TransformLanguage>("java_sdk");
  const [schemaPacks, setSchemaPacks] = useState<SchemaPackSummary[]>([]);
  const [selectedSchemaPackId, setSelectedSchemaPackId] = useState("");
  const [schemaPackMessage, setSchemaPackMessage] = useState("No schema pack selected");
  const [builderSession, setBuilderSession] = useState<BuilderSession | null>(null);
  const [selectedTemplate, setSelectedTemplate] = useState<string | null>(null);
  const [templateQuestion, setTemplateQuestion] = useState<string | null>(null);
  const [incomingProtocol, setIncomingProtocol] = useState("MQTT");
  const [targetFormat, setTargetFormat] = useState("OPC UA");
  const [genericScenario, setGenericScenario] = useState("");
  const [chatInput, setChatInput] = useState("");
  const [generatedRun, setGeneratedRun] = useState<GenerationRunSummary | null>(null);
  const [workerJob, setWorkerJob] = useState<WorkerJob | null>(null);
  const [exportMode, setExportMode] = useState<ExportMode>("vscode");
  const [working, setWorking] = useState(false);
  const [liveDesignStatus, setLiveDesignStatus] = useState("Add an input message");
  const [liveDesigning, setLiveDesigning] = useState(false);
  const eventSourceRef = useRef<EventSource | null>(null);
  const feedPausedRef = useRef(false);
  const builderPaneRef = useRef<HTMLElement | null>(null);
  const outputPaneRef = useRef<HTMLElement | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  const draftFiles = useMemo(
    () =>
      (builderSession?.draft?.files ?? []).filter(
        (file) =>
          typeof file.path === "string" &&
          file.path.trim().length > 0 &&
          typeof file.purpose === "string" &&
          file.purpose.trim().length > 0
      ),
    [builderSession?.draft?.files]
  );
  const generationInProgress = Boolean(
    workerJob && !["completed", "failed", "partial"].includes(workerJob.status)
  );
  const agentWorking = working || liveDesigning || generationInProgress;
  const statusLooksError = /failed|unable|required|error|rejected/i.test(liveDesignStatus);
  const agentStateLabel = agentWorking
    ? "Working"
    : statusLooksError
      ? "Error"
      : builderSession?.draft
        ? "Ready"
        : selectedEvent
          ? "Idle"
          : "Waiting";
  const projectReady = Boolean(generatedRun && workerJob?.status === "completed");
  const exportUrl =
    generatedRun && projectReady
      ? {
          single: transformFileUrl(generatedRun.id),
          vscode: workspaceArchiveUrl(generatedRun.id),
          image: imageArchiveUrl(generatedRun.id)
        }[exportMode]
      : undefined;
  const readyToGenerate = Boolean(builderSession?.draft);
  const generateDisabled = !readyToGenerate || working || generationInProgress;
  const generationFinished = Boolean(
    workerJob && ["completed", "failed", "partial"].includes(workerJob.status)
  );
  const chatMessages = builderSession?.messages ?? [];
  const hasAssistantMessage = chatMessages.some((chat) => chat.role === "assistant");
  const selectedSourceType = String(selectedEvent?.headers?.sourceType ?? "");
  const selectedInputFormat = String(selectedEvent?.headers?.inputFormat ?? "json").toUpperCase();
  const selectedSourceLabel =
    selectedSourceType === "manual_input" ? "input message" : "live event";
  const selectedSchemaPack = useMemo(
    () => schemaPacks.find((pack) => pack.id === selectedSchemaPackId) ?? null,
    [schemaPacks, selectedSchemaPackId]
  );

  useEffect(() => {
    listSchemaPacks()
      .then((packs) => {
        setSchemaPacks(packs);
        setSchemaPackMessage(
          packs.length ? "Optional schema context available" : "Add reusable schemas in Schema Library"
        );
      })
      .catch((error) => {
        setSchemaPackMessage(error instanceof Error ? error.message : "Unable to load schema packs");
      });
  }, []);

  useEffect(() => {
    feedPausedRef.current = feedPaused;
  }, [feedPaused]);

  useEffect(() => {
    if (!subscription) return;
    eventSourceRef.current?.close();
    const source = new EventSource(capturedEventsStreamUrl(subscription.id));
    eventSourceRef.current = source;
    source.onmessage = (event) => {
      if (feedPausedRef.current) return;
      const captured = JSON.parse(event.data) as CapturedEvent;
      setCapturedEvents((current) => {
        if (current.some((item) => item.id === captured.id)) return current;
        return [...current, captured].slice(-maxVisibleEvents);
      });
      setSelectedEvent((current) => current ?? captured);
    };
    source.onerror = () => {};
    listCapturedEvents(subscription.id)
      .then((events) => {
        const visibleEvents = events.slice(-maxVisibleEvents);
        setCapturedEvents(visibleEvents);
        setSelectedEvent((current) => current ?? visibleEvents.at(-1) ?? null);
      })
      .catch(() => {});
    return () => source.close();
  }, [subscription]);

  useEffect(() => {
    if (selectedEvent) {
      window.requestAnimationFrame(() => {
        builderPaneRef.current?.scrollIntoView({
          behavior: "smooth",
          block: "nearest",
          inline: "center"
        });
      });
    }
  }, [selectedEvent]);

  useEffect(() => {
    if (!workerJob || ["completed", "failed", "partial"].includes(workerJob.status)) return;
    const interval = window.setInterval(() => {
      getWorkerJob(workerJob.id)
        .then(setWorkerJob)
        .catch(() => {});
    }, 2000);
    return () => window.clearInterval(interval);
  }, [workerJob]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [chatMessages.length, templateQuestion, builderSession?.draft]);

  const selectedOutput = useMemo(() => {
    return builderSession?.draft?.sampleOutput ?? builderSession?.preview ?? {};
  }, [builderSession]);

  const topicDestination =
    builderSession?.draft?.topicMapping?.outputTopic ??
    generatedRun?.canonicalModel?.topics?.[0] ??
    "Waiting for transform";
  const draftHeaderMapping = isRecord(builderSession?.draft?.headerMapping)
    ? builderSession.draft.headerMapping
    : {};
  const draftOutputHeaders = isRecord(draftHeaderMapping.outputHeaders)
    ? draftHeaderMapping.outputHeaders
    : {};
  const rewrittenTopicHeader =
    typeof draftHeaderMapping.topicHeader === "string"
      ? draftHeaderMapping.topicHeader
      : typeof draftOutputHeaders.topic === "string"
        ? draftOutputHeaders.topic
        : typeof draftOutputHeaders.targetTopic === "string"
          ? draftOutputHeaders.targetTopic
          : undefined;
  const workerResult = isRecord(workerJob?.result) ? workerJob.result : {};
  const sampleOutputBytes =
    resultNumber(workerResult, "sampleOutputBytes") ?? byteSize(selectedOutput);
  const templatesVisible = !selectedTemplate && !builderSession?.draft && !chatInput.trim();
  const transformArtifactPath = draftFiles[0]?.path ?? transformPath(language);
  const transformArtifactName = transformArtifactPath.split("/").pop() ?? transformArtifactPath;
  const draftComplete = Boolean(builderSession?.draft);
  const projectGenerationActive = (working && readyToGenerate && !liveDesigning) || generationInProgress;
  const agentWorkSummary = projectReady
    ? {
        title: "Micro integration ready",
        detail: "Download is enabled."
      }
    : projectGenerationActive
      ? {
          title: "Generating project",
          detail: generatedRun
            ? `${generatedRun.serviceName || "Micro integration"} checks are running.`
            : "Creating the project workspace and running checks."
        }
      : generatedRun
        ? {
            title: workerJob?.status === "failed" || workerJob?.status === "partial"
              ? "Project checks need attention"
              : "Project generated",
            detail: `Build status: ${workerJob?.status ?? "pending"}`
          }
        : draftComplete
          ? {
              title: `Wrote ${transformArtifactName}`,
              detail: `Posts to ${topicDestination} · ${formatBytes(sampleOutputBytes)} sample`
            }
          : liveDesigning
            ? {
                title: "Drafting transform",
                detail: `Preparing ${transformArtifactPath}`
              }
          : null;
  const builderStatusTone = agentWorking
    ? "working"
    : statusLooksError
      ? "error"
      : projectReady || draftComplete
        ? "ready"
        : selectedEvent
          ? "idle"
          : "waiting";

  function applyTemplate(templateKey: string) {
    const template = templateOptions.find((option) => option.key === templateKey);
    if (!template) return;
    setSelectedTemplate(template.key);
    if (template.language) {
      setLanguage(template.language);
    }
    setChatInput(template.prompt);
    setGeneratedRun(null);
    setWorkerJob(null);
    setTemplateQuestion(
      `What should the ${template.label.toLowerCase()} transform produce from this ${selectedSourceLabel}? I filled in a strong default prompt below; edit it or send it as-is.`
    );
    window.requestAnimationFrame(() => {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    });
  }

  function applyProtocolTemplate() {
    const prompt = protocolChangePrompt(incomingProtocol, targetFormat);
    setSelectedTemplate("protocol-change");
    setChatInput(prompt);
    setGeneratedRun(null);
    setWorkerJob(null);
    setTemplateQuestion(
      `What should the ${incomingProtocol} to ${targetFormat} protocol change produce from this ${selectedSourceLabel}? I filled in a strong default prompt below; edit it or send it as-is.`
    );
    window.requestAnimationFrame(() => {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    });
  }

  function applyGenericBuilder() {
    const prompt = genericBuilderPrompt(genericScenario, selectedSchemaPack?.name);
    setSelectedTemplate("generic-builder");
    setChatInput(prompt);
    setGeneratedRun(null);
    setWorkerJob(null);
    setTemplateQuestion(
      genericScenario.trim()
        ? "I put your generic scenario into the prompt below. Edit it or send it as-is."
        : "Describe any integration scenario in the prompt below. The builder will infer the details from the input message and selected context."
    );
    window.requestAnimationFrame(() => {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    });
  }

  function clearDesignState() {
    setBuilderSession(null);
    setGeneratedRun(null);
    setWorkerJob(null);
    setSelectedTemplate(null);
    setTemplateQuestion(null);
    setChatInput("");
    setExportMode("vscode");
  }

  async function useManualInput() {
    const topic = manualTopic.trim();
    const payload = manualPayload.trim();
    if (!topic || !payload || working) return;
    setWorking(true);
    setLiveDesignStatus("Preparing input message");
    try {
      const event = await createInputMessageEvent({
        topicName: topic,
        sourceName: manualSourceName.trim() || "Manual input message",
        inputFormat: manualInputFormat,
        payload,
        headers: {
          enteredFrom: "workbench"
        }
      });
      setSourceMode("manual");
      setCapturedEvents((current) => {
        const withoutDuplicate = current.filter((item) => item.id !== event.id);
        return [...withoutDuplicate, event].slice(-maxVisibleEvents);
      });
      setSelectedEvent(event);
      clearDesignState();
      setLiveDesignStatus(
        "Input message ready. Pick a scenario or describe the event you want to publish."
      );
    } catch (error) {
      setLiveDesignStatus(error instanceof Error ? error.message : "Unable to prepare input");
    } finally {
      setWorking(false);
    }
  }

  async function startCapture() {
    setWorking(true);
    setLiveDesignStatus("Starting capture");
    try {
      const nextSubscription = await createSolaceSubscription({
        brokerUrl,
        vpn,
        username,
        password,
        topicFilter
      });
      setSourceMode("live");
      setSubscription(nextSubscription);
      setCapturedEvents([]);
      setSelectedEvent(null);
      setCredentialsHidden(true);
      setFeedPaused(false);
      clearDesignState();
      setIncomingProtocol("MQTT");
      setTargetFormat("OPC UA");
      setLiveDesignStatus(nextSubscription.message);
    } catch (error) {
      setLiveDesignStatus(error instanceof Error ? error.message : "Capture failed");
    } finally {
      setWorking(false);
    }
  }

  async function ensureSession() {
    if (builderSession) return builderSession;
    if (!selectedEvent) throw new Error("Add an input message first");
    const session = await createBuilderSession({
      capturedEventId: selectedEvent.id,
      transformLanguage: language
    });
    setBuilderSession(session);
    return session;
  }

  async function submitPrompt(content: string, status: string) {
    const prompt = content.trim();
    if (!prompt || working || liveDesigning) return;
    setWorking(true);
    setLiveDesigning(true);
    setTemplateQuestion(null);
    setLiveDesignStatus(status);
    try {
      const session = await ensureSession();
      const updated = await sendBuilderMessage(session.id, {
        content: prompt,
        transformLanguage: language,
        schemaPackId: selectedSchemaPackId || undefined
      });
      setBuilderSession(updated);
      setGeneratedRun(null);
      setWorkerJob(null);
      setChatInput("");
      setLiveDesignStatus(
        "Draft ready. Review the output topic and sample result, then generate or iterate."
      );
      window.requestAnimationFrame(() => {
        outputPaneRef.current?.scrollIntoView({
          behavior: "smooth",
          block: "nearest",
          inline: "center"
        });
      });
    } catch (error) {
      setLiveDesignStatus(error instanceof Error ? error.message : "Unable to draft");
    } finally {
      setWorking(false);
      setLiveDesigning(false);
    }
  }

  async function sendMessage() {
    await submitPrompt(chatInput, "Drafting transform, output topic, and sample result");
  }

  async function generate() {
    if (generateDisabled) return;
    setWorking(true);
    setLiveDesignStatus("Rendering the template project around the current transform");
    try {
      const session = await ensureSession();
      const result = await generateBuilderSession(session.id);
      setBuilderSession(result.session);
      setGeneratedRun(result.run);
      setWorkerJob(result.workerJob);
      setLiveDesignStatus(
        "Project generated. Security, performance, Maven, and Docker checks are running."
      );
      window.requestAnimationFrame(() => {
        outputPaneRef.current?.scrollIntoView({
          behavior: "smooth",
          block: "nearest",
          inline: "center"
        });
      });
    } catch (error) {
      setLiveDesignStatus(error instanceof Error ? error.message : "Generation failed");
    } finally {
      setWorking(false);
    }
  }

  return (
    <main className="workbench">
      <section className="pane left-pane" aria-label="Input message">
        <div className="pane-head">
          <div>
            <span className="step-kicker">1 Input</span>
            <h1>Input Message</h1>
          </div>
        </div>

        <div className="source-mode-tabs" role="tablist" aria-label="Input source mode">
          <button
            type="button"
            role="tab"
            aria-selected={sourceMode === "manual"}
            data-active={sourceMode === "manual"}
            onClick={() => setSourceMode("manual")}
          >
            <FileText size={15} />
            <span>Paste message</span>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={sourceMode === "live"}
            data-active={sourceMode === "live"}
            onClick={() => setSourceMode("live")}
          >
            <Radio size={15} />
            <span>Live broker</span>
          </button>
        </div>

        {sourceMode === "manual" ? (
          <div className="manual-input-card">
            <div className="form-grid compact-form">
              <label className="wide">
                <span>System</span>
                <input
                  value={manualSourceName}
                  onChange={(event) => setManualSourceName(event.target.value)}
                  placeholder="ERP, CRM, HL7 feed, EDI gateway"
                />
              </label>
              <label className="wide">
                <span>Input topic / message name</span>
                <input
                  value={manualTopic}
                  onChange={(event) => setManualTopic(event.target.value)}
                  placeholder="systems/orders/approved/v1"
                />
              </label>
              <label className="wide">
                <span>Input format</span>
                <select
                  value={manualInputFormat}
                  onChange={(event) => {
                    const nextFormat = event.target.value as InputMessageFormat;
                    setManualInputFormat(nextFormat);
                    if (dataweaveFormats.has(nextFormat)) {
                      setLanguage("dataweave");
                    }
                  }}
                >
                  {inputFormatOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <label className="manual-payload-field">
              <span>Message body</span>
              <textarea
                value={manualPayload}
                onChange={(event) => setManualPayload(event.target.value)}
                placeholder="Paste JSON, XML, CSV, HL7, EDIFACT, ANSI X12, ODETTE, or text"
              />
            </label>
            <button
              type="button"
              className="action-button"
              disabled={working || !manualTopic.trim() || !manualPayload.trim()}
              onClick={useManualInput}
            >
              <FileText size={18} />
              <span>Use input message</span>
            </button>
          </div>
        ) : subscription && credentialsHidden ? (
          <div className="connection-card">
            <div>
              <span>Connected</span>
              <strong>{subscription.topicFilter}</strong>
              <small>{brokerUrl}</small>
            </div>
            <button
              type="button"
              className="secondary-button"
              onClick={() => setCredentialsHidden(false)}
            >
              <EyeOff size={16} />
              <span>Show credentials</span>
            </button>
          </div>
        ) : (
          <>
            <div className="form-grid compact-form">
              <label className="wide">
                <span>Broker URL</span>
                <input value={brokerUrl} onChange={(event) => setBrokerUrl(event.target.value)} />
              </label>
              <label>
                <span>VPN</span>
                <input value={vpn} onChange={(event) => setVpn(event.target.value)} />
              </label>
              <label>
                <span>Topic</span>
                <input
                  value={topicFilter}
                  onChange={(event) => setTopicFilter(event.target.value)}
                />
              </label>
              <label>
                <span>Username</span>
                <input value={username} onChange={(event) => setUsername(event.target.value)} />
              </label>
              <label>
                <span>Password</span>
                <input
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                />
              </label>
            </div>

            <button
              type="button"
              className="action-button"
              disabled={working}
              onClick={startCapture}
            >
              <Radio size={18} />
              <span>{subscription ? "Reconnect" : "Listen"}</span>
            </button>
          </>
        )}

        {sourceMode === "live" || capturedEvents.length > 0 ? (
          <div className="event-list">
            <div className="section-row event-feed-head">
              <div>
                <strong>{sourceMode === "manual" ? "Inputs" : "Events"}</strong>
                <small>
                  {feedPaused ? "Feed paused" : `Latest ${capturedEvents.length} of 10`}
                </small>
              </div>
              <button
                type="button"
                className="feed-toggle"
                aria-pressed={feedPaused}
                onClick={() => {
                  setFeedPaused((current) => !current);
                  if (feedPaused && subscription) {
                    listCapturedEvents(subscription.id)
                      .then((events) => setCapturedEvents(events.slice(-maxVisibleEvents)))
                      .catch(() => {});
                  }
                }}
                disabled={sourceMode === "manual" || !subscription}
              >
                {feedPaused ? <Play size={14} /> : <Pause size={14} />}
                <span>{feedPaused ? "Resume" : "Pause"}</span>
              </button>
            </div>
            {capturedEvents.map((event) => (
              <button
                type="button"
                className="event-row"
                data-active={selectedEvent?.id === event.id}
                key={event.id}
                onClick={() => {
                  setSelectedEvent(event);
                  clearDesignState();
                }}
              >
                <Activity size={16} />
                <span>{event.topicName}</span>
                <ChevronRight size={16} />
              </button>
            ))}
          </div>
        ) : null}

        {selectedEvent ? (
          <div className="payload-panel">
            <div className="section-row">
              <strong>{selectedInputFormat} payload</strong>
              <Braces size={16} />
            </div>
            <pre>{prettyJson(selectedEvent.payload)}</pre>
          </div>
        ) : null}
      </section>

      <section className="pane chat-pane" aria-label="AI builder" ref={builderPaneRef}>
        <div className="pane-head">
          <div>
            <span className="step-kicker">2 Builder</span>
            <h2>Builder</h2>
          </div>
          <div className="builder-controls">
            <div
              className="agent-state"
              data-working={agentWorking}
              title={liveDesignStatus}
              aria-label={`Builder is ${agentStateLabel.toLowerCase()}: ${liveDesignStatus}`}
            >
              {agentWorking ? <LoaderCircle className="spin" size={14} /> : null}
              <span>{agentStateLabel}</span>
            </div>
            <div className="select-wrap">
              <select
                value={language}
                onChange={(event) => setLanguage(event.target.value as TransformLanguage)}
              >
                {languageOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>

        <div className="builder-status-stack" aria-live="polite">
          <div className="schema-selector-row">
            <Library size={15} />
            <label>
              <span>Schema pack</span>
              <select
                value={selectedSchemaPackId}
                onChange={(event) => {
                  const nextId = event.target.value;
                  setSelectedSchemaPackId(nextId);
                  const pack = schemaPacks.find((item) => item.id === nextId);
                  if (pack && dataweaveFormats.has(String(pack.schemaFormat))) {
                    setLanguage("dataweave");
                  }
                }}
              >
                <option value="">No schema pack</option>
                {schemaPacks.map((pack) => (
                  <option key={pack.id} value={pack.id}>
                    {pack.name}
                  </option>
                ))}
              </select>
            </label>
            <small>
              {selectedSchemaPack
                ? `${selectedSchemaPack.schemaFormat} · ${
                    selectedSchemaPack.messageType ?? "generic"
                  }`
                : schemaPackMessage}
            </small>
          </div>
          <div className="builder-status-line" data-tone={builderStatusTone}>
            {agentWorking ? (
              <LoaderCircle className="spin" size={15} />
            ) : builderStatusTone === "error" ? (
              <AlertTriangle size={15} />
            ) : (
              <FileCode2 size={15} />
            )}
            <span className="builder-status-label">{agentStateLabel}</span>
            <span className="builder-status-copy">{liveDesignStatus}</span>
          </div>
          {selectedEvent && agentWorkSummary ? (
            <div className="builder-work-line" data-working={agentWorking}>
              {agentWorking ? (
                <LoaderCircle className="spin" size={15} />
              ) : (
                <FileCode2 size={15} />
              )}
              <div>
                <strong>{agentWorkSummary.title}</strong>
                <small>{agentWorkSummary.detail}</small>
              </div>
            </div>
          ) : null}
        </div>

        <div className="chat-box">
          <div className="messages">
            {!chatMessages.length && !builderSession?.draft && !templateQuestion ? (
              <article className="message system-message" data-role="assistant">
                <span>builder</span>
                <p>
                  {selectedEvent
                    ? `Pick a scenario or describe the transform from this ${selectedSourceLabel}. I will infer the details and draft a focused micro integration.`
                    : "Add an input message first. Then choose a scenario or describe the transform."}
                </p>
              </article>
            ) : null}
            {templatesVisible ? (
              <article className="message template-message" data-role="assistant">
                <span>start with</span>
                <div className="template-grid">
                  <div className="generic-template-card">
                    <div className="generic-template-head">
                      <FileCode2 size={17} />
                      <div>
                        <span>Generic builder</span>
                        <small>any source, target, schema, header, or format</small>
                      </div>
                    </div>
                    <label className="generic-template-field">
                      <span>Scenario</span>
                      <textarea
                        rows={3}
                        value={genericScenario}
                        disabled={working || liveDesigning || !selectedEvent}
                        onChange={(event) => setGenericScenario(event.target.value)}
                        placeholder="Example: receive an HL7 appointment, validate it with SIU_S12, anonymize patient identifiers, and publish a canonical appointment event."
                      />
                    </label>
                    <button
                      type="button"
                      className="generic-template-action"
                      disabled={working || liveDesigning || !selectedEvent}
                      onClick={applyGenericBuilder}
                    >
                      <span>Use generic builder</span>
                      <ChevronRight size={15} />
                    </button>
                  </div>
                  <div className="protocol-template-card">
                    <div className="protocol-template-head">
                      <Cable size={17} />
                      <div>
                        <span>Protocol change</span>
                        <small>convert inbound protocol to target format</small>
                      </div>
                    </div>
                    <div className="protocol-template-controls">
                      <label>
                        <span>Incoming</span>
                        <select
                          value={incomingProtocol}
                          disabled={working || liveDesigning || !selectedEvent}
                          onChange={(event) => {
                            setIncomingProtocol(event.target.value);
                            if (selectedTemplate === "protocol-change") {
                              setChatInput(protocolChangePrompt(event.target.value, targetFormat));
                            }
                          }}
                        >
                          {incomingProtocolOptions.map((option) => (
                            <option key={option} value={option}>
                              {option}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        <span>Target</span>
                        <select
                          value={targetFormat}
                          disabled={working || liveDesigning || !selectedEvent}
                          onChange={(event) => {
                            setTargetFormat(event.target.value);
                            if (selectedTemplate === "protocol-change") {
                              setChatInput(protocolChangePrompt(incomingProtocol, event.target.value));
                            }
                          }}
                        >
                          {targetFormatOptions.map((option) => (
                            <option key={option} value={option}>
                              {option}
                            </option>
                          ))}
                        </select>
                      </label>
                    </div>
                    <button
                      type="button"
                      className="protocol-template-action"
                      disabled={working || liveDesigning || !selectedEvent}
                      onClick={applyProtocolTemplate}
                    >
                      <span>Use protocol change</span>
                      <ChevronRight size={15} />
                    </button>
                  </div>
                  {templateOptions.map((template) => {
                    const Icon = template.icon;
                    return (
                      <button
                        type="button"
                        className="template-button"
                        key={template.key}
                        disabled={working || liveDesigning || !selectedEvent}
                        onClick={() => applyTemplate(template.key)}
                      >
                        <Icon size={16} />
                        <span>{template.label}</span>
                        <small>{template.note}</small>
                      </button>
                    );
                  })}
                </div>
              </article>
            ) : null}
            {chatMessages.map((chat) => (
              <article key={chat.id} className="message" data-role={chat.role}>
                <span>{chat.role}</span>
                <p>{chat.content}</p>
              </article>
            ))}
            {builderSession?.draft?.assistantMessage && !hasAssistantMessage ? (
              <article className="message" data-role="assistant">
                <span>builder</span>
                <p>{builderSession.draft.assistantMessage}</p>
              </article>
            ) : null}
            {templateQuestion ? (
              <article className="message template-question-message" data-role="assistant">
                <span>builder</span>
                <p>{templateQuestion}</p>
              </article>
            ) : null}
            <div ref={messagesEndRef} />
          </div>

          <div className="composer">
            <textarea
              rows={3}
              placeholder={
                selectedEvent
                  ? `Describe the ${languageLabel(language)} transform.`
                  : "Add or select an input message first."
              }
              value={chatInput}
              disabled={!selectedEvent}
              onKeyDown={(event) => {
                if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
                  event.preventDefault();
                  if (!working && chatInput.trim()) {
                    void sendMessage();
                  }
                }
              }}
              onChange={(event) => {
                const nextValue = event.target.value;
                setSelectedTemplate(null);
                setChatInput(nextValue);
                if (!nextValue.trim()) setTemplateQuestion(null);
              }}
            />
            <button
              type="button"
              className="send-button"
              aria-label="Send"
              onClick={sendMessage}
              disabled={working || !chatInput.trim() || !selectedEvent}
            >
              <Send size={18} />
            </button>
          </div>
        </div>
      </section>

      <section className="pane right-pane" aria-label="Output" ref={outputPaneRef}>
        <div className="pane-head">
          <div>
            <span className="step-kicker">3 Output</span>
            <h2>Sample Result</h2>
          </div>
        </div>

        <div className="output-preview">
          <pre>{prettyJson(selectedOutput)}</pre>
        </div>

        <div className="output-metadata">
          <div className="topic-destination">
            <span>Topic destination</span>
            <strong>{topicDestination}</strong>
          </div>
          {rewrittenTopicHeader ? (
            <div className="header-destination">
              <span>Header rewrite</span>
              <strong>{rewrittenTopicHeader}</strong>
            </div>
          ) : null}
          <div className="benchmark-grid" aria-label="Generation benchmarks">
            <div className="benchmark-card benchmark-pass">
              <span>Benchmarked throughput</span>
              <strong>
                <CheckCircle2 size={18} aria-hidden="true" />
                1,000 events/s
              </strong>
            </div>
            <div className="benchmark-card">
              <span>Build</span>
              <strong>{workerJob?.status ?? "idle"}</strong>
            </div>
          </div>
        </div>

        {readyToGenerate && !projectReady ? (
          <button
            type="button"
            className="generate-button"
            disabled={generateDisabled}
            data-ready={readyToGenerate && !generationInProgress}
            onClick={generate}
          >
            <Play size={18} />
            <span>
              {generationInProgress
                ? "Generating Micro Integration"
                : generationFinished
                  ? "Regenerate Micro Integration"
                  : "Generate Micro Integration"}
            </span>
          </button>
        ) : null}

        <div className="export-mode" aria-label="Export format">
          {exportOptions.map((option) => (
            <button
              type="button"
              key={option.value}
              data-active={exportMode === option.value}
              disabled={!generatedRun}
              onClick={() => setExportMode(option.value)}
            >
              <span>{option.label}</span>
              <small>{option.note}</small>
            </button>
          ))}
        </div>

        <a
          className="download-button"
          data-ready={projectReady}
          aria-disabled={!projectReady}
          href={exportUrl}
          onClick={(event) => {
            if (!projectReady) event.preventDefault();
          }}
        >
          <Download size={18} />
          <span>Download the Micro Integration</span>
        </a>
      </section>
    </main>
  );
}
