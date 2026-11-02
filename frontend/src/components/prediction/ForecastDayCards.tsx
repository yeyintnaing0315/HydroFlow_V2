import type { PredictionTimelineDay } from "../../types";
import { formatPercent, riskLabel } from "./mapUtils";

interface ForecastDayCardsProps {
  days: PredictionTimelineDay[];
  selectedDate: string;
  onSelect: (date: string) => void;
}

export default function ForecastDayCards({ days, selectedDate, onSelect }: ForecastDayCardsProps) {
  if (days.length === 0) {
    return <p className="state">No days in this range.</p>;
  }
  return (
    <div className="forecast-day-cards" role="list" aria-label="Daily forecast cards">
      {days.map((day) => (
        <button
          key={day.date}
          type="button"
          role="listitem"
          className={`forecast-day-card ${selectedDate === day.date ? "selected" : ""}`}
          aria-pressed={selectedDate === day.date}
          onClick={() => onSelect(day.date)}
        >
          <time dateTime={day.date}>{day.date}</time>
          <strong>{formatPercent(day.flood_probability)}</strong>
          <span className={`risk-pill risk-${day.probability_risk_level ?? "none"}`}>
            {riskLabel(day.probability_risk_level)}
          </span>
          <p>
            {day.rainfall_mm == null ? "Rainfall —" : `${day.rainfall_mm.toFixed(1)} mm rain`}
            {day.period_type === "historical" && day.observed_flood ? " · Recorded flood" : ""}
          </p>
          <small>{day.data_status.replaceAll("_", " ")}</small>
        </button>
      ))}
    </div>
  );
}
