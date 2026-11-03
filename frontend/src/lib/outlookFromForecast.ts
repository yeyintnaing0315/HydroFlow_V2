import type { PredictionTimelineDay, RegionForecastScore } from "../types";

export function outlookFromForecast(score: RegionForecastScore): PredictionTimelineDay {
  const level = score.probability_risk_level;
  return {
    date: score.target_date,
    period_type: score.lead_days > 0 ? "forecast" : "current",
    flood_probability: score.flood_probability,
    predicted_flood: score.flood_probability == null ? null : score.flood_probability >= 0.5,
    probability_risk_level: level,
    risk_level: level ?? "unknown",
    hydrology_risk_score: null,
    hydrology_risk_level: null,
    rainfall_mm: score.rainfall_mm,
    discharge_m3_s: score.discharge_m3_s,
    relative_humidity_pct: null,
    impact_level: "unknown",
    potentially_exposed_population: null,
    potentially_affected_population: null,
    observed_flood: null,
    recorded_affected_people: null,
    data_status: score.data_status,
    evidence_type: score.data_status === "model_estimate" ? "model_prediction" : "none",
    probability_status: score.data_status === "model_estimate" ? "uncalibrated_academic_score" : null,
    forecast_horizon_hours: score.lead_days * 24,
    input_freshness: {},
    uncertainty:
      score.data_status === "unavailable"
        ? "Hydrology for this township is unavailable."
        : "Academic model score from saved or local hydrology.",
    key_factors: [],
  };
}
