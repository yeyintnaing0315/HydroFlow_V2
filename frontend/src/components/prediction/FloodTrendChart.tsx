import { useMemo, useState } from "react";
import type { PredictionTimelineDay } from "../../types";
import { formatPercent, riskLabel } from "./mapUtils";

interface FloodTrendChartProps {
  days: PredictionTimelineDay[];
  asOf: string;
  selectedDate: string;
  onSelect: (date: string) => void;
}

export default function FloodTrendChart({ days, asOf, selectedDate, onSelect }: FloodTrendChartProps) {
  const [hovered, setHovered] = useState<string | null>(null);
  const scored = useMemo(
    () => days.filter((day) => day.flood_probability != null),
    [days],
  );

  if (scored.length === 0) {
    return <p className="state">No probability series available for this township.</p>;
  }

  const width = 640;
  const height = 200;
  const pad = { top: 16, right: 12, bottom: 28, left: 36 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const xs = scored.map((_, index) => pad.left + (index / Math.max(scored.length - 1, 1)) * innerW);
  const ys = scored.map(
    (day) => pad.top + innerH - (day.flood_probability as number) * innerH,
  );
  const points = xs.map((x, index) => `${x},${ys[index]}`).join(" ");
  const asOfIndex = scored.findIndex((day) => day.date === asOf);
  const asOfX = asOfIndex >= 0 ? xs[asOfIndex] : null;

  const activeDate = hovered ?? selectedDate;
  const active = scored.find((day) => day.date === activeDate) ?? scored[scored.length - 1];

  return (
    <div className="trend-chart-wrap">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="trend-chart"
        role="img"
        aria-label="Flood probability trend"
      >
        <line x1={pad.left} y1={pad.top + innerH} x2={width - pad.right} y2={pad.top + innerH} stroke="#c8d4e0" />
        {[0, 0.25, 0.5, 0.75, 1].map((tick) => {
          const y = pad.top + innerH - tick * innerH;
          return (
            <g key={tick}>
              <line x1={pad.left} y1={y} x2={width - pad.right} y2={y} stroke="#e8eef5" />
              <text x={4} y={y + 4} fontSize="10" fill="#6b7c90">
                {Math.round(tick * 100)}
              </text>
            </g>
          );
        })}
        <polyline fill="none" stroke="#0b5873" strokeWidth="2.5" points={points} />
        {scored.map((day, index) => (
          <circle
            key={day.date}
            cx={xs[index]}
            cy={ys[index]}
            r={selectedDate === day.date ? 6 : 4}
            fill={day.period_type === "forecast" ? "#d86a1a" : day.period_type === "historical" ? "#2d9c6c" : "#1f6feb"}
            stroke="#fff"
            strokeWidth="1.5"
            style={{ cursor: "pointer" }}
            onMouseEnter={() => setHovered(day.date)}
            onMouseLeave={() => setHovered(null)}
            onClick={() => onSelect(day.date)}
          >
            <title>
              {day.date}: {formatPercent(day.flood_probability)} ({riskLabel(day.probability_risk_level)})
            </title>
          </circle>
        ))}
        {asOfX != null && (
          <line
            x1={asOfX}
            y1={pad.top}
            x2={asOfX}
            y2={pad.top + innerH}
            stroke="#1f6feb"
            strokeDasharray="4 3"
          />
        )}
      </svg>
      <div className="trend-tooltip" aria-live="polite">
        <strong>{active.date}</strong>
        <span>{formatPercent(active.flood_probability)} · {riskLabel(active.probability_risk_level)}</span>
        <small>{active.period_type} · {active.data_status.replaceAll("_", " ")}</small>
      </div>
      <div className="trend-legend">
        <span><i className="dot historical" /> Historical estimate</span>
        <span><i className="dot current" /> Today</span>
        <span><i className="dot forecast" /> Forecast</span>
      </div>
    </div>
  );
}
