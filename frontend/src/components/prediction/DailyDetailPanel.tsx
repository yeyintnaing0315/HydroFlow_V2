import type { PredictionTimelineDay } from "../../types";
import { floodBandLabel, formatPercent } from "./mapUtils";

interface DailyDetailPanelProps {
  day: PredictionTimelineDay | undefined;
}

export default function DailyDetailPanel({ day }: DailyDetailPanelProps) {
  if (!day) {
    return <p className="state">Select a date to view the flood prediction.</p>;
  }
  const riskLevel = day.probability_risk_level ?? "unknown";
  const tiles: [string, string, string?][] = [
    ["Flood chance", formatPercent(day.flood_probability)],
    ["Risk", floodBandLabel(riskLevel), `metric-risk risk-${riskLevel}`],
    ["Rainfall", day.rainfall_mm == null ? "—" : `${day.rainfall_mm.toFixed(1)} mm`],
    ["Discharge", day.discharge_m3_s == null ? "—" : `${day.discharge_m3_s.toFixed(1)} m³/s`],
  ];
  return (
    <div className="flood-now-grid" role="table" aria-label="Flood prediction">
      {tiles.map(([label, value, tone]) => (
        <div key={label} role="row" className={tone}>
          <span>{label}</span>
          <strong>{value}</strong>
        </div>
      ))}
    </div>
  );
}
