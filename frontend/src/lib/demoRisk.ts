import type { PredictionTimelineDay, RiskLevel } from "../types";

export type DemoRiskMode = "off" | "high" | "severe";

const DEMO_PROBABILITY: Record<Exclude<DemoRiskMode, "off">, number> = {
  high: 0.62,
  severe: 0.82,
};

export function demoRiskMode(): DemoRiskMode {
  const raw = (import.meta.env.VITE_DEMO_RISK_LEVEL as string | undefined)?.trim().toLowerCase();
  if (raw === "high" || raw === "severe") return raw;
  return "off";
}

/** Local UI demo only — does not change API or stored predictions. */
export function applyDemoRisk(day: PredictionTimelineDay | undefined): PredictionTimelineDay | undefined {
  const mode = demoRiskMode();
  if (!day || mode === "off") return day;
  const level: RiskLevel = mode;
  const probability = DEMO_PROBABILITY[mode];
  return {
    ...day,
    flood_probability: probability,
    predicted_flood: true,
    probability_risk_level: level,
    risk_level: level,
  };
}

export function demoRiskBanner(): string | null {
  const mode = demoRiskMode();
  if (mode === "off") return null;
  return `Demo mode: showing ${mode} risk in the UI (VITE_DEMO_RISK_LEVEL). Live API scores are unchanged.`;
}
