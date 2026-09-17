"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, PlugZap, Save, ShieldCheck } from "lucide-react";
import { getSettings, saveSettings, testLiteLlmSettings } from "@/lib/api";

export default function SettingsPage() {
  const [message, setMessage] = useState("Configure the hosted AI provider used by Builder.");
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [configured, setConfigured] = useState(false);
  const [form, setForm] = useState({
    litellmBaseUrl: "",
    litellmApiKey: "",
    litellmModel: "bedrock-claude-4-5-sonnet",
    publicBaseUrl: ""
  });

  async function loadView() {
    try {
      const view = await getSettings();
      setConfigured(view.hasLiteLlmConfig);
      setForm((current) => ({
        ...current,
        litellmBaseUrl: view.litellmBaseUrl ?? current.litellmBaseUrl,
        litellmModel: view.litellmModel ?? current.litellmModel,
        publicBaseUrl: view.publicBaseUrl ?? current.publicBaseUrl
      }));
      setMessage(
        view.hasLiteLlmConfig
          ? "AI Provider is configured. API key remains encrypted server-side."
          : "AI Provider is missing a base URL, API key, or model."
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to load settings");
    }
  }

  useEffect(() => {
    void loadView();
  }, []);

  async function testConnection() {
    setTesting(true);
    setMessage("Testing LiteLLM connection");
    try {
      const result = await testLiteLlmSettings({
        litellmBaseUrl: form.litellmBaseUrl.trim() || undefined,
        litellmApiKey: form.litellmApiKey.trim() || undefined,
        litellmModel: form.litellmModel.trim() || undefined
      });
      setMessage(result.message);
      setConfigured(result.ok || configured);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to test LiteLLM");
    } finally {
      setTesting(false);
    }
  }

  async function save() {
    setSaving(true);
    setMessage("Saving encrypted AI Provider settings");
    try {
      const payload: Record<string, unknown> = {
        litellmBaseUrl: form.litellmBaseUrl.trim(),
        litellmModel: form.litellmModel.trim(),
        publicBaseUrl: form.publicBaseUrl.trim()
      };
      if (form.litellmApiKey.trim()) {
        payload.litellmApiKey = form.litellmApiKey.trim();
      }
      const view = await saveSettings(payload);
      setConfigured(view.hasLiteLlmConfig);
      setForm((current) => ({ ...current, litellmApiKey: "" }));
      setMessage("AI Provider settings saved. Testing saved connection now.");
      const result = await testLiteLlmSettings({});
      setMessage(result.message);
      setConfigured(result.ok);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to save settings");
    } finally {
      setSaving(false);
    }
  }

  return (
    <main className="settings-page">
      <section className="settings-hero">
        <div>
          <span className="step-kicker">Settings</span>
          <h1>AI Provider</h1>
          <p>
            Builder always uses LiteLLM for chat, draft generation, sample output, and the
            transform file. Hosted deployments store these values encrypted in the app.
          </p>
        </div>
        <div className="settings-state" data-ready={configured}>
          {configured ? <CheckCircle2 size={20} /> : <ShieldCheck size={20} />}
          <strong>{configured ? "Configured" : "Needs setup"}</strong>
          <span>{configured ? "encrypted server-side" : "connection required"}</span>
        </div>
      </section>

      <section className="settings-grid">
        <div className="ai-provider-card">
          <div className="section-row">
            <div>
              <strong>LiteLLM connection</strong>
              <small>OpenAI-compatible chat completions endpoint</small>
            </div>
            <PlugZap size={18} />
          </div>
          <div className="form-grid">
            <label className="wide">
              <span>Base URL</span>
              <input
                value={form.litellmBaseUrl}
                onChange={(event) =>
                  setForm((current) => ({ ...current, litellmBaseUrl: event.target.value }))
                }
                placeholder="https://lite-llm.example"
              />
            </label>
            <label className="wide">
              <span>API key</span>
              <input
                type="password"
                value={form.litellmApiKey}
                onChange={(event) =>
                  setForm((current) => ({ ...current, litellmApiKey: event.target.value }))
                }
                placeholder={configured ? "Leave blank to keep saved key" : "Paste key"}
              />
            </label>
            <label className="wide">
              <span>Model</span>
              <input
                value={form.litellmModel}
                onChange={(event) =>
                  setForm((current) => ({ ...current, litellmModel: event.target.value }))
                }
                placeholder="bedrock-claude-4-5-sonnet"
              />
            </label>
            <label className="wide">
              <span>Public app URL</span>
              <input
                value={form.publicBaseUrl}
                onChange={(event) =>
                  setForm((current) => ({ ...current, publicBaseUrl: event.target.value }))
                }
                placeholder="http://mi.sol-se-emea.com"
              />
            </label>
          </div>
          <div className="settings-actions">
            <button
              type="button"
              className="secondary-button"
              disabled={testing || saving}
              onClick={testConnection}
            >
              <PlugZap size={16} />
              <span>{testing ? "Testing" : "Test connection"}</span>
            </button>
            <button
              type="button"
              className="action-button compact-action"
              disabled={saving || testing || !form.litellmBaseUrl.trim() || !form.litellmModel.trim()}
              onClick={save}
            >
              <Save size={16} />
              <span>{saving ? "Saving" : "Save encrypted settings"}</span>
            </button>
          </div>
          <p className="muted">{message}</p>
        </div>
      </section>
    </main>
  );
}
