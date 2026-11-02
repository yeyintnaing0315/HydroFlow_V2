import type { HealthResponse, JobRun } from "../../types";

interface ModelStatusBarProps {
  health: HealthResponse | undefined;
  lastRun: JobRun | undefined;
  stale: boolean;
}

export default function ModelStatusBar({ health, lastRun, stale }: ModelStatusBarProps) {
  return (
    <div className="model-status-bar" role="status">
      <span>
        Flood model: {health?.models?.flood ? "artifact loaded" : "unavailable"} · Help model:{" "}
        {health?.models?.help ? "loaded" : "unavailable"}
      </span>
      <span>
        Last prediction job:{" "}
        {lastRun ? `${lastRun.status} · ${lastRun.finished_at ?? lastRun.started_at}` : "none"}
        {stale ? " · Data may be stale (>12h)" : ""}
      </span>
    </div>
  );
}
