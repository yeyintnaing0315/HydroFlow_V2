import type { TownshipRouteComparison } from "../../types";
import { floodExposureLabel, formatDistance, formatDuration, formatMeasure, routeMethodLabel } from "./routeFormat";

interface RouteComparisonProps {
  state: "idle" | "loading" | "ready" | "error";
  error?: string;
  comparison: TownshipRouteComparison | null;
  onSelect: (optionIndex: number) => void;
  selecting: boolean;
}

export default function RouteComparison({
  state,
  error,
  comparison,
  onSelect,
  selecting,
}: RouteComparisonProps) {
  const alternatives = comparison?.alternatives ?? [];
  return (
    <section className="panel allocation-compare-panel" aria-label="Route comparison">
      <div className="section-heading">
        <h2>Routes</h2>
        {comparison && !comparison.alternatives_available && alternatives.length === 1 ? (
          <span className="source">Only one route is available</span>
        ) : null}
      </div>
      {state === "loading" ? <p className="state">Comparing routes…</p> : null}
      {state === "error" ? <p className="state error">Routes unavailable: {error}</p> : null}
      {state === "idle" ? <p className="hint">Select a township to compare delivery roads.</p> : null}
      {comparison && alternatives.length ? (
        <>
          <p className="allocation-context-line">
            Destination rain {formatMeasure(comparison.rainfall_mm)} mm · discharge{" "}
            {formatMeasure(comparison.discharge_m3_s)} m³/s
            {comparison.risk_band ? ` · ${comparison.risk_band}` : ""}
          </p>
          <div className="allocation-route-cards">
            {alternatives.map((option) => (
              <button
                key={option.option_index}
                type="button"
                className={option.selected ? "is-selected" : option.recommended ? "is-recommended" : ""}
                aria-pressed={option.selected}
                disabled={selecting}
                onClick={() => onSelect(option.option_index)}
              >
                <strong>
                  {option.label}
                  {option.recommended ? " · recommended" : ""}
                  {option.selected ? " · selected" : ""}
                </strong>
                <span>
                  {formatDistance(option.distance_m)} · {formatDuration(option.duration_s)}
                </span>
                <span>{routeMethodLabel(option.routing_method)}</span>
                <span>{floodExposureLabel(option.flood_exposure)}</span>
              </button>
            ))}
          </div>
        </>
      ) : null}
    </section>
  );
}
