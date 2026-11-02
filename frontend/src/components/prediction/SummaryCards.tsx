import type { PredictionTimelineDay } from "../../types";
import { formatPercent, riskLabel } from "./mapUtils";

interface SummaryCardsProps {
  day: PredictionTimelineDay | undefined;
  asOf: string;
}

function valueOrDash(value: number | null | undefined, suffix: string) {
  return value == null ? "—" : `${value.toLocaleString()} ${suffix}`;
}

export default function SummaryCards({ day, asOf }: SummaryCardsProps) {
  const impact =
    day?.impact_level && day.impact_level !== "unknown" && day.impact_level !== "none"
      ? riskLabel(day.impact_level)
      : day?.probability_risk_level
        ? `${riskLabel(day.probability_risk_level)} (model-based)`
        : "Unknown";

  return (
    <div className="summary-cards" aria-label="Flood prediction summary">
      <article className="summary-card summary-primary">
        <span>Flood probability</span>
        <strong>{formatPercent(day?.flood_probability)}</strong>
        <small>
          {day?.evidence_type === "model_prediction"
            ? "Uncalibrated model score"
            : day?.data_status === "insufficient_features"
              ? "Missing rainfall or discharge for this day — run hydro download or pick another date"
              : "No model score"}
        </small>
      </article>
      <article className="summary-card summary-primary">
        <span>Flood risk level</span>
        <strong className={`risk-pill risk-${day?.probability_risk_level ?? "none"}`}>
          {riskLabel(day?.probability_risk_level)}
        </strong>
        <small>Derived from probability bands</small>
      </article>
      <article className="summary-card">
        <span>Rainfall</span>
        <strong>{valueOrDash(day?.rainfall_mm, "mm")}</strong>
        <small>Selected day · as of {asOf}</small>
      </article>
      <article className="summary-card">
        <span>Expected impact</span>
        <strong>{impact}</strong>
        <small>Recorded impacts override when available</small>
      </article>
    </div>
  );
}
