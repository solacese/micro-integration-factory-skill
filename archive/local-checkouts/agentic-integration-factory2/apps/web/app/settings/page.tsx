"use client";

import { useState } from "react";
import { getSettings, saveSettings } from "@/lib/api";

export default function SettingsPage() {
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("Enter the demo admin password to read or update stored credentials.");
  const [form, setForm] = useState<Record<string, string>>({
    awsAccessKeyId: "",
    awsSecretAccessKey: "",
    awsSessionToken: "",
    litellmBaseUrl: "",
    litellmApiKey: "",
    litellmModel: "",
    solaceBrokerUrl: "",
    solaceVpn: "",
    solaceUsername: "",
    solacePassword: "",
    solaceWebMessagingUrl: "",
    eventPortalBaseUrl: "",
    eventPortalToken: "",
    k8sApiServer: "",
    k8sToken: "",
    k8sNamespace: "",
    k8sCaCert: "",
    rancherUrl: "",
    rancherToken: "",
    containerRegistry: "",
    containerRegistryUsername: "",
    containerRegistryPassword: "",
    containerImagePrefix: "",
    stripeSecretKey: "",
    stripeWebhookSecret: "",
    deployEc2Host: "",
    deployEc2SshUser: "",
    deployEc2SshPrivateKey: "",
    deployEc2Port: "",
    publicBaseUrl: ""
  });

  async function loadView() {
    try {
      window.sessionStorage.setItem("demo-admin-password", password);
      const view = await getSettings();
      setMessage(
        `Loaded settings metadata. AWS: ${view.hasAwsConfig ? "configured" : "missing"}, Solace: ${view.hasSolaceConfig ? "configured" : "missing"}, Event Portal: ${view.hasEventPortalConfig ? "configured" : "missing"}`
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to load settings");
    }
  }

  async function save() {
    try {
      window.sessionStorage.setItem("demo-admin-password", password);
      await saveSettings(form);
      setMessage("Settings saved server-side.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to save settings");
    }
  }

  return (
    <main className="stack">
      <section className="panel stack">
        <span className="eyebrow">Admin settings</span>
        <h1 className="page-title">Server-side credentials and deploy settings.</h1>
        <p className="muted">{message}</p>
      </section>
      <section className="panel stack">
        <label className="input">
          <span>Demo admin password</span>
          <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
        </label>
        <div className="flex">
          <button className="button-secondary" onClick={loadView} type="button">
            Load metadata
          </button>
          <button className="button-primary" onClick={save} type="button">
            Save settings
          </button>
        </div>
      </section>
      <section className="three-column">
        {Object.entries(form).map(([key, value]) => (
          <label className="input panel" key={key}>
            <span>{key}</span>
            <input
              value={value}
              onChange={(event) => setForm((current) => ({ ...current, [key]: event.target.value }))}
            />
          </label>
        ))}
      </section>
    </main>
  );
}
