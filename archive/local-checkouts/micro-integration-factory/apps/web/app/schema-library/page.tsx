"use client";

import { useEffect, useMemo, useState } from "react";
import { FileCode2, Library, Trash2, Upload } from "lucide-react";
import type { SchemaPackFormat, SchemaPackSummary } from "@spec2event/shared";
import { createSchemaPack, deleteSchemaPack, listSchemaPacks } from "@/lib/api";

const schemaFormats: Array<{ value: SchemaPackFormat; label: string }> = [
  { value: "hl7", label: "HL7 YAML" },
  { value: "generic_edi", label: "Generic EDI YAML" },
  { value: "edifact", label: "EDIFACT YAML" },
  { value: "odette", label: "ODETTE YAML" },
  { value: "ansi_x12", label: "ANSI X12 YAML" },
  { value: "json_schema", label: "JSON Schema" },
  { value: "xml_schema", label: "XML / XSD" },
  { value: "csv_layout", label: "CSV layout" },
  { value: "fixed_width", label: "Fixed-width layout" }
];

const sampleHl7 = `form: HL7
version: '2.5.1'
structures:
- id: 'SIU_S12'
  name: 'SIU_S12'
  data:
  - { idRef: 'MSH', position: '01', usage: R }
  - { idRef: 'SCH', position: '02', usage: R }
  - groupId: 'PATIENT'
    count: '>1'
    usage: O
    items:
    - { idRef: 'PID', position: '06', usage: O }
segments:
- id: 'MSH'
  name: 'Message Header'
  values:
  - { idRef: 'ST', name: 'Sending Application', usage: R }
- id: 'PID'
  name: 'Patient Identification'
  values:
  - { idRef: 'CX', name: 'Patient Identifier List', usage: R, count: '>1' }
composites:
- id: 'CX'
  name: 'Extended Composite ID'
  values:
  - { idRef: 'ST', name: 'ID Number', usage: R }
`;

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function asRecords(summary: Record<string, unknown>, key: string) {
  const value = summary[key];
  return Array.isArray(value) ? value.filter(isRecord) : [];
}

function countValue(pack: SchemaPackSummary, key: string) {
  const counts = pack.summary.counts;
  if (isRecord(counts)) {
    const value = counts[key];
    if (typeof value === "number") return value;
  }
  return 0;
}

function textValue(value: unknown) {
  if (typeof value === "string" && value.trim()) return value;
  if (typeof value === "number") return String(value);
  return "none";
}

export default function SchemaLibraryPage() {
  const [packs, setPacks] = useState<SchemaPackSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [message, setMessage] = useState("Upload reusable schemas once, then use them in Builder.");
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    name: "HL7 SIU_S12 appointment",
    schemaFormat: "hl7" as SchemaPackFormat,
    version: "2.5.1",
    messageType: "SIU_S12",
    industry: "Healthcare",
    rawContent: sampleHl7,
    filename: ""
  });

  async function refresh() {
    try {
      const nextPacks = await listSchemaPacks();
      setPacks(nextPacks);
      setSelectedId((current) => current ?? nextPacks[0]?.id ?? null);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to load schema packs");
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  const selectedPack = useMemo(
    () => packs.find((pack) => pack.id === selectedId) ?? packs[0] ?? null,
    [packs, selectedId]
  );

  async function uploadSchema() {
    if (!form.name.trim() || !form.rawContent.trim() || saving) return;
    setSaving(true);
    setMessage("Parsing schema pack");
    try {
      const created = await createSchemaPack({
        name: form.name.trim(),
        schemaFormat: form.schemaFormat,
        version: form.version.trim() || undefined,
        messageType: form.messageType.trim() || undefined,
        industry: form.industry.trim() || undefined,
        rawContent: form.rawContent,
        filename: form.filename || undefined,
        contentType: "text/plain"
      });
      setSelectedId(created.id);
      setMessage(`Saved ${created.name}. Builder can now use it as schema context.`);
      await refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to save schema pack");
    } finally {
      setSaving(false);
    }
  }

  async function removeSchema(schemaPackId: string) {
    setSaving(true);
    try {
      await deleteSchemaPack(schemaPackId);
      setMessage("Schema pack deleted.");
      setSelectedId(null);
      await refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to delete schema pack");
    } finally {
      setSaving(false);
    }
  }

  return (
    <main className="library-page">
      <section className="library-hero">
        <div>
          <span className="step-kicker">Schema Library</span>
          <h1>Reusable schema packs for generic micro integrations</h1>
          <p>
            Store HL7, EDI, JSON Schema, XML/XSD, CSV, and fixed-width layouts as compact
            mapping context for Builder.
          </p>
        </div>
        <div className="library-stat">
          <Library size={20} />
          <strong>{packs.length}</strong>
          <span>schema packs</span>
        </div>
      </section>

      <section className="library-grid">
        <div className="library-form">
          <div className="section-row">
            <strong>Add schema pack</strong>
            <Upload size={16} />
          </div>
          <div className="form-grid compact-form">
            <label className="wide">
              <span>Name</span>
              <input
                value={form.name}
                onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
              />
            </label>
            <label>
              <span>Format</span>
              <select
                value={form.schemaFormat}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    schemaFormat: event.target.value as SchemaPackFormat
                  }))
                }
              >
                {schemaFormats.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Version</span>
              <input
                value={form.version}
                onChange={(event) => setForm((current) => ({ ...current, version: event.target.value }))}
              />
            </label>
            <label>
              <span>Message type</span>
              <input
                value={form.messageType}
                onChange={(event) =>
                  setForm((current) => ({ ...current, messageType: event.target.value }))
                }
                placeholder="SIU_S12, DESADV, 850"
              />
            </label>
            <label>
              <span>Industry</span>
              <input
                value={form.industry}
                onChange={(event) =>
                  setForm((current) => ({ ...current, industry: event.target.value }))
                }
                placeholder="Healthcare, Automotive"
              />
            </label>
            <label className="wide file-input">
              <span>Upload file</span>
              <input
                type="file"
                onChange={async (event) => {
                  const file = event.target.files?.[0];
                  if (!file) return;
                  const text = await file.text();
                  setForm((current) => ({
                    ...current,
                    filename: file.name,
                    name: current.name || file.name,
                    rawContent: text
                  }));
                }}
              />
            </label>
          </div>
          <label className="manual-payload-field schema-content-field">
            <span>Raw schema content</span>
            <textarea
              value={form.rawContent}
              onChange={(event) =>
                setForm((current) => ({ ...current, rawContent: event.target.value }))
              }
            />
          </label>
          <div className="section-row">
            <small className="muted">{message}</small>
            <button
              type="button"
              className="action-button compact-action"
              disabled={saving || !form.name.trim() || !form.rawContent.trim()}
              onClick={uploadSchema}
            >
              <FileCode2 size={16} />
              <span>Save schema pack</span>
            </button>
          </div>
        </div>

        <div className="schema-list">
          <div className="section-row">
            <strong>Reusable packs</strong>
            <small>{packs.length} total</small>
          </div>
          {packs.map((pack) => (
            <button
              type="button"
              className="schema-pack-row"
              data-active={selectedPack?.id === pack.id}
              key={pack.id}
              onClick={() => setSelectedId(pack.id)}
            >
              <span>{pack.name}</span>
              <small>
                {pack.schemaFormat} · {pack.messageType ?? "any type"}
              </small>
            </button>
          ))}
          {!packs.length ? <p className="muted">No schema packs yet.</p> : null}
        </div>

        <div className="schema-detail">
          {selectedPack ? (
            <>
              <div className="section-row">
                <div>
                  <strong>{selectedPack.name}</strong>
                  <small>
                    {selectedPack.schemaFormat} · {selectedPack.version ?? "unversioned"} ·{" "}
                    {selectedPack.industry ?? "general"}
                  </small>
                </div>
                <button
                  type="button"
                  className="icon-danger"
                  aria-label="Delete schema pack"
                  disabled={saving}
                  onClick={() => void removeSchema(selectedPack.id)}
                >
                  <Trash2 size={16} />
                </button>
              </div>
              <div className="schema-count-grid">
                {["structures", "segments", "composites", "fields"].map((key) => (
                  <div key={key}>
                    <span>{key}</span>
                    <strong>{countValue(selectedPack, key)}</strong>
                  </div>
                ))}
              </div>
              <div className="schema-summary-grid">
                <SummaryBlock
                  title="Structures"
                  items={asRecords(selectedPack.summary, "structures")}
                  empty="No structures parsed"
                />
                <SummaryBlock
                  title="Segments"
                  items={asRecords(selectedPack.summary, "segments")}
                  empty="No segments parsed"
                />
                <SummaryBlock
                  title="Composites"
                  items={asRecords(selectedPack.summary, "composites")}
                  empty="No composites parsed"
                />
                <SummaryBlock
                  title="Fields"
                  items={asRecords(selectedPack.summary, "fields")}
                  empty="No fields parsed"
                />
              </div>
              <div className="schema-hints">
                <strong>Required / repeating hints</strong>
                <small>
                  Required: {countValue(selectedPack, "requiredHints")} · Repeating:{" "}
                  {countValue(selectedPack, "repeatingHints")}
                </small>
                <p>
                  Example message type:{" "}
                  {textValue(selectedPack.summary.exampleMessageType ?? selectedPack.messageType)}
                </p>
              </div>
            </>
          ) : (
            <p className="muted">Select a schema pack to inspect its parsed summary.</p>
          )}
        </div>
      </section>
    </main>
  );
}

function SummaryBlock({
  title,
  items,
  empty
}: {
  title: string;
  items: Array<Record<string, unknown>>;
  empty: string;
}) {
  return (
    <div className="summary-block">
      <strong>{title}</strong>
      {items.length ? (
        items.slice(0, 8).map((item, index) => (
          <div className="summary-row" key={`${title}-${index}`}>
            <span>{textValue(item.id ?? item.name ?? item.path)}</span>
            <small>
              {textValue(item.fieldCount ?? item.itemCount ?? item.type ?? item.position)}
            </small>
          </div>
        ))
      ) : (
        <small className="muted">{empty}</small>
      )}
    </div>
  );
}
