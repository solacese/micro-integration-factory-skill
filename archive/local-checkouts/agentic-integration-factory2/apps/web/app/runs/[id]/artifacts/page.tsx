"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import type { ArtifactDetail, ArtifactSummary } from "@spec2event/shared";
import { getArtifact, getArtifacts, updateArtifact } from "@/lib/api";

export default function ArtifactEditorPage() {
  const params = useParams<{ id: string }>();
  const runId = params.id;
  const [artifacts, setArtifacts] = useState<ArtifactSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [selected, setSelected] = useState<ArtifactDetail | null>(null);
  const [content, setContent] = useState("");
  const [password, setPassword] = useState(() => {
    if (typeof window === "undefined") {
      return "";
    }
    return window.sessionStorage.getItem("demo-admin-password") ?? "";
  });
  const [message, setMessage] = useState("Loading artifacts...");

  useEffect(() => {
    if (!runId) return;
    getArtifacts(runId)
      .then((items) => {
        setArtifacts(items);
        if (items[0]) setSelectedId(items[0].id);
        setMessage(
          items.length ? "Select an artifact to inspect or edit." : "No artifacts available yet.",
        );
      })
      .catch((error) =>
        setMessage(error instanceof Error ? error.message : "Unable to load artifacts"),
      );
  }, [runId]);

  useEffect(() => {
    if (!runId || !selectedId) return;
    getArtifact(runId, selectedId)
      .then((artifact) => {
        setSelected(artifact);
        setContent(artifact.content);
      })
      .catch((error) =>
        setMessage(error instanceof Error ? error.message : "Unable to load artifact"),
      );
  }, [runId, selectedId]);

  return (
    <main className="two-column">
      <section className="panel stack">
        <div className="flex-between">
          <div>
            <span className="eyebrow">Artifacts</span>
            <h1 className="page-title">Generated project files</h1>
          </div>
          <div className="input" style={{ minWidth: 280 }}>
            <span>Admin password for save</span>
            <input
              type="password"
              value={password}
              onChange={(event) => {
                const value = event.target.value;
                setPassword(value);
                window.sessionStorage.setItem("demo-admin-password", value);
              }}
            />
          </div>
        </div>
        <p className="muted">{message}</p>
        <div className="grid-table">
          {artifacts.map((artifact) => (
            <button
              className="table-row columns-2"
              key={artifact.id}
              onClick={() => setSelectedId(artifact.id)}
              type="button"
            >
              <div>
                <strong>{artifact.path}</strong>
                <div className="muted">{artifact.kind}</div>
              </div>
              <div>
                <span className="badge">rev {artifact.revision}</span>
              </div>
            </button>
          ))}
        </div>
      </section>
      <section className="editor-pane stack">
        <div className="flex-between">
          <div>
            <span className="eyebrow">Editor</span>
            <div className="muted">{selected?.path ?? "Choose a file"}</div>
          </div>
          <button
            className="button-primary"
            disabled={!selected}
            onClick={async () => {
              if (!selected) return;
              setMessage("Saving artifact revision...");
              try {
                const updated = await updateArtifact(runId, selected.id, content);
                setSelected(updated);
                setContent(updated.content);
                setMessage(`Saved ${updated.path} as revision ${updated.revision}`);
              } catch (error) {
                setMessage(error instanceof Error ? error.message : "Unable to save artifact");
              }
            }}
            type="button"
          >
            Save revision
          </button>
        </div>
        <div className="textarea">
          <textarea value={content} onChange={(event) => setContent(event.target.value)} />
        </div>
      </section>
    </main>
  );
}
