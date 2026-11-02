import { useEffect, useMemo, useState } from "react";
import { api } from "../../api";
import { riskLabel } from "../prediction/mapUtils";
import type { BagoAreasResponse, FloodCaseCatalogResponse, FloodCaseItem, LoadState } from "../../types";
import type { AllocationFocus } from "../../lib/allocationFocus";

interface HomeFloodHistoryProps {
  areas?: BagoAreasResponse;
  onPlanResources: (focus: AllocationFocus) => void;
}

function formatNumber(value: number): string {
  return value.toLocaleString("en-US", { maximumFractionDigits: 0 });
}

function formatDateRange(row: FloodCaseItem): string {
  if (row.start_date === row.end_date) return row.start_date;
  return `${row.start_date} → ${row.end_date}`;
}

function formatPeakScore(row: FloodCaseItem): string {
  if (row.peak_score == null) return "—";
  if (row.source === "model") return `${row.peak_score.toFixed(1)}%`;
  return formatNumber(row.peak_score);
}

function sourceLabel(source: FloodCaseItem["source"]): string {
  return source === "recorded" ? "Relief records" : "Flood model";
}

function townshipCoords(areas: BagoAreasResponse | undefined, townshipId: string) {
  for (const district of areas?.districts ?? []) {
    const match = district.townships.find((township) => township.id === townshipId);
    if (match) return { latitude: match.latitude, longitude: match.longitude };
  }
  return undefined;
}

export default function HomeFloodHistory({ areas, onPlanResources }: HomeFloodHistoryProps) {
  const [state, setState] = useState<LoadState>("loading");
  const [data, setData] = useState<FloodCaseCatalogResponse | undefined>();
  const [error, setError] = useState<string | undefined>();
  const [level, setLevel] = useState<"all" | "high" | "severe">("all");
  const [source, setSource] = useState<"all" | "recorded" | "model">("all");
  const [year, setYear] = useState<number | "all">("all");

  useEffect(() => {
    let active = true;
    setState("loading");
    api
      .floodCasesHighSevere({
        level,
        source,
        view: "events",
        year: year === "all" ? undefined : year,
        limit: 500,
      })
      .then((payload) => {
        if (!active) return;
        setData(payload);
        setState(payload.events.length ? "ready" : "empty");
      })
      .catch((reason: unknown) => {
        if (!active) return;
        setError(reason instanceof Error ? reason.message : "Could not load flood history");
        setState("error");
      });
    return () => {
      active = false;
    };
  }, [level, source, year]);

  const years = useMemo(() => data?.by_year.map((entry) => entry.year) ?? [], [data]);

  const planFromRow = (row: FloodCaseItem) => {
    const coords = townshipCoords(areas, row.township_id);
    if (!coords) return;
    onPlanResources({
      townshipId: row.township_id,
      townshipName: row.place,
      date: row.peak_date,
      riskLevel: row.level,
      latitude: coords.latitude,
      longitude: coords.longitude,
      expectedAffected: row.affected_people ?? undefined,
      floodProbability: row.source === "model" && row.peak_score != null ? row.peak_score / 100 : undefined,
    });
  };

  return (
    <article className="panel home-flood-history">
      <div className="section-heading">
        <h2>High &amp; severe flood history</h2>
        <p className="hint home-flood-history-sub">
          When and where high or severe levels occurred across all catalogued data (relief impacts and model bands).
        </p>
      </div>

      <div className="home-flood-history-filters" role="group" aria-label="Filter flood history">
        <label>
          Level
          <select value={level} onChange={(event) => setLevel(event.target.value as typeof level)}>
            <option value="all">All</option>
            <option value="severe">Severe only</option>
            <option value="high">High only</option>
          </select>
        </label>
        <label>
          Source
          <select value={source} onChange={(event) => setSource(event.target.value as typeof source)}>
            <option value="all">All sources</option>
            <option value="recorded">Relief records</option>
            <option value="model">Flood model</option>
          </select>
        </label>
        <label>
          Year
          <select
            value={year === "all" ? "all" : String(year)}
            onChange={(event) => {
              const value = event.target.value;
              setYear(value === "all" ? "all" : Number(value));
            }}
          >
            <option value="all">All years</option>
            {years.map((entry) => (
              <option key={entry} value={entry}>
                {entry}
              </option>
            ))}
          </select>
        </label>
      </div>

      {state === "loading" && <p className="state">Loading high and severe cases…</p>}
      {state === "error" && <p className="state error">{error}</p>}
      {state === "ready" && data && (
        <>
          <ul className="home-flood-history-kpis" aria-label="Case totals">
            <li>
              <strong>{formatNumber(data.counts.total)}</strong>
              <span>events</span>
            </li>
            <li>
              <strong>{formatNumber(data.counts.severe)}</strong>
              <span>severe</span>
            </li>
            <li>
              <strong>{formatNumber(data.counts.high)}</strong>
              <span>high</span>
            </li>
            <li>
              <strong>{formatNumber(data.counts.recorded)}</strong>
              <span>from relief</span>
            </li>
            <li>
              <strong>{formatNumber(data.counts.model)}</strong>
              <span>from model</span>
            </li>
          </ul>
          <p className="hint">{data.disclaimer}</p>
          <div className="allocation-table-wrap home-flood-history-table">
            <table>
              <thead>
                <tr>
                  <th scope="col">Place</th>
                  <th scope="col">Level</th>
                  <th scope="col">Dates</th>
                  <th scope="col">Peak</th>
                  <th scope="col">Source</th>
                  <th scope="col">People</th>
                  <th scope="col">Depot</th>
                  <th scope="col" />
                </tr>
              </thead>
              <tbody>
                {data.events.map((row) => (
                  <tr key={`${row.source}-${row.township_id}-${row.start_date}-${row.level}`}>
                    <td>{row.place}</td>
                    <td>
                      <span className={`risk-pill risk-${row.level}`}>{riskLabel(row.level)}</span>
                    </td>
                    <td>
                      {formatDateRange(row)}
                      {row.days > 1 ? ` (${row.days} d)` : ""}
                    </td>
                    <td>{formatPeakScore(row)}</td>
                    <td>
                      {sourceLabel(row.source)}
                      {row.overlap ? " · overlap" : ""}
                    </td>
                    <td>{row.affected_people != null ? formatNumber(row.affected_people) : "—"}</td>
                    <td>{row.depot}</td>
                    <td>
                      <button type="button" className="text-link" onClick={() => planFromRow(row)}>
                        Plan
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      {state === "empty" && (
        <p className="state">
          No high or severe cases match these filters. Regenerate{" "}
          <code>data/processed/flood_cases_high_severe.csv</code> with{" "}
          <code>scripts/flood_case_catalog.py</code> if the catalog is outdated.
        </p>
      )}
    </article>
  );
}
