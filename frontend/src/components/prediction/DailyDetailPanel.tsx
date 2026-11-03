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
  const floodTiles: [string, string, string?][] = [
    ["Flood chance", formatPercent(day.flood_probability)],
    ["Risk", floodBandLabel(riskLevel), `metric-risk risk-${riskLevel}`],
    ["Rainfall", day.rainfall_mm == null ? "—" : `${day.rainfall_mm.toFixed(1)} mm`],
    ["Discharge", day.discharge_m3_s == null ? "—" : `${day.discharge_m3_s.toFixed(1)} m³/s`],
  ];
  const weatherTiles: [string, string][] = [
    ["Temperature", day.temperature_c == null ? "—" : `${day.temperature_c.toFixed(1)} °C`],
    ["Humidity", day.relative_humidity_pct == null ? "—" : `${Math.round(day.relative_humidity_pct)}%`],
    ["Wind speed", day.wind_speed_m_s == null ? "—" : `${day.wind_speed_m_s.toFixed(1)} m/s`],
    ["7-day rainfall", day.rainfall_7d_mm == null ? "—" : `${day.rainfall_7d_mm.toFixed(1)} mm`],
  ];
  return (
    <section className="prediction-metrics-panel" aria-label="Selected day metrics">
      <p className="prediction-metrics-group-label">Flood</p>
      <div className="flood-now-grid prediction-metrics-grid" role="table" aria-label="Flood prediction">
        {floodTiles.map(([label, value, tone]) => (
          <div key={label} role="row" className={tone}>
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </div>
      <p className="prediction-metrics-group-label">Weather</p>
      <div className="flood-now-grid prediction-metrics-grid prediction-weather-grid" role="table" aria-label="Weather conditions">
        {weatherTiles.map(([label, value]) => (
          <div key={label} role="row">
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </div>
    </section>
  );
}
