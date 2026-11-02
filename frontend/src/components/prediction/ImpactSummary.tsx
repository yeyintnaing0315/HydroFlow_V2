import type { PredictionTimelineDay } from "../../types";
import { riskLabel } from "./mapUtils";

interface ImpactSummaryProps {
  day: PredictionTimelineDay | undefined;
  disclaimer: string;
}

export default function ImpactSummary({ day, disclaimer }: ImpactSummaryProps) {
  const impactLevel = day?.impact_level;
  return (
    <article className="panel impact-panel" aria-label="Population and impact">
      <div className="section-heading">
        <h2>Population &amp; impact</h2>
      </div>
      <p className="hint">{disclaimer}</p>
      <div className="detail-grid">
        <div className="detail-row">
          <span>Potentially exposed population</span>
          <strong>
            {day?.potentially_exposed_population == null
              ? "Unavailable"
              : day.potentially_exposed_population.toLocaleString()}
          </strong>
          <small>2024 census total for township — not an affected count.</small>
        </div>
        <div className="detail-row">
          <span>Recorded affected (selected day)</span>
          <strong>
            {day?.recorded_affected_people == null ? "No validated record" : day.recorded_affected_people.toLocaleString()}
          </strong>
        </div>
        <div className="detail-row">
          <span>Impact level</span>
          <strong>
            {impactLevel === "none"
              ? "None"
              : riskLabel(impactLevel === "unknown" ? null : impactLevel ?? null)}
          </strong>
        </div>
      </div>
    </article>
  );
}
