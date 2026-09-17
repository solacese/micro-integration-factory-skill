"use client";

import clsx from "clsx";
import { GOLDEN_STEPPER, type GenerationRunSummary } from "@spec2event/shared";

export function RunStepper({ run }: { run: GenerationRunSummary }) {
  const stepsByName = new Map(run.steps.map((step) => [step.stepName, step]));
  const progressed = GOLDEN_STEPPER.filter((step) => stepsByName.has(step.key)).length;
  const progressPercent = Math.round((progressed / GOLDEN_STEPPER.length) * 100);

  return (
    <div className="stack">
      <div className="progress-shell">
        <div className="progress-meta">
          <strong>Progress</strong>
          <span className="muted">
            {progressed} / {GOLDEN_STEPPER.length}
          </span>
        </div>
        <div className="progress-track" aria-hidden="true">
          <div className="progress-fill" style={{ width: `${progressPercent}%` }} />
        </div>
      </div>

      <div className="step-table-wrap">
        <table className="step-table">
          <thead>
            <tr>
              <th scope="col">Step</th>
              <th scope="col">State</th>
              <th scope="col">Detail</th>
            </tr>
          </thead>
          <tbody>
            {GOLDEN_STEPPER.map((step, index) => {
              const record = stepsByName.get(step.key);
              const status = record?.status ?? "pending";
              return (
                <tr key={step.key}>
                  <td>
                    <div className="step-name">
                      <span className="step-index">{String(index + 1).padStart(2, "0")}</span>
                      <strong>{step.label}</strong>
                    </div>
                  </td>
                  <td>
                    <span className={clsx("step-state")} data-status={status}>
                      {status}
                    </span>
                  </td>
                  <td className="step-detail">{record?.message ?? "Waiting"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
