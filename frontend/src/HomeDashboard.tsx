import { useEffect, useMemo, useState } from "react";
import type { GeoJsonObject } from "geojson";
import { GeoJSON, MapContainer, useMap } from "react-leaflet";
import { api } from "./api";
import BasemapTileLayer from "./components/map/BasemapTileLayer";
import MapViewportFix from "./components/map/MapViewportFix";
import { districtColor, floodFillLevel, formatPercent, riskColor, riskLabel } from "./components/prediction/mapUtils";
import HomeFloodHistory from "./components/home/HomeFloodHistory";
import { PageControls, ViewDialog } from "./components/ViewDialog";
import { needsResourceAllocation, type AllocationFocus } from "./lib/allocationFocus";
import { fillRatio, itemCapacity, statusFor, statusSlug, type StockStatus } from "./lib/stockStatus";
import type {
  AllocationPlanHistoryItem,
  AllocationPlanResponse,
  AllocationTownshipRow,
  AssistancePriority,
  BagoAreasResponse,
  InventorySnapshot,
  LoadState,
  PageId,
  RegionForecastResponse,
  RegionForecastScore,
  RiskLevel,
} from "./types";

interface Resource<T> {
  state: LoadState;
  data?: T;
  error?: string;
}

interface HomeDashboardProps {
  areas: Resource<BagoAreasResponse>;
  onOpenPage: (page: PageId) => void;
  onPlanResources: (focus: AllocationFocus) => void;
}

interface StockLine {
  key: string;
  name: string;
  quantity: number;
  unit: string;
  status: StockStatus;
  fill: number;
  depot: string;
}

const LEVEL_RANK: Record<string, number> = {
  unknown: 0,
  none: 0,
  low: 1,
  moderate: 2,
  high: 3,
  severe: 4,
  very_high: 4,
};

const loading = <T,>(): Resource<T> => ({ state: "loading" });

function localDate(): string {
  const day = new Date();
  return `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, "0")}-${String(day.getDate()).padStart(2, "0")}`;
}

function errorText(reason: unknown): string {
  return reason instanceof Error ? reason.message : "Unexpected request failure";
}

function formatNumber(value: number, digits = 0): string {
  return value.toLocaleString("en-US", { maximumFractionDigits: digits });
}

function formatRainRange(values: number[]): string {
  if (values.length === 0) return "—";
  const min = Math.min(...values);
  const max = Math.max(...values);
  if (min === max) return `${formatNumber(min, 1)} mm`;
  return `${formatNumber(min, 1)}–${formatNumber(max, 1)} mm`;
}

function newestPlan(plans: AllocationPlanHistoryItem[]): AllocationPlanHistoryItem | undefined {
  return [...plans].sort((left, right) => right.created_at.localeCompare(left.created_at))[0];
}

function levelRank(level: string | null | undefined): number {
  return LEVEL_RANK[level ?? "unknown"] ?? 0;
}

function rankOutlook(score: RegionForecastScore): { level: RiskLevel | "unknown"; probability: number } {
  const level = score.probability_risk_level ?? score.risk_level ?? "unknown";
  return { level, probability: score.flood_probability ?? -1 };
}

function stockLines(locations: InventorySnapshot[]): StockLine[] {
  return locations.flatMap((snapshot) =>
    snapshot.classes.flatMap((row) =>
      row.items.map((item) => {
        const capacity = itemCapacity(row.code, item);
        return {
          key: `${snapshot.region}:${row.code}:${item.code ?? item.name}`,
          name: item.name,
          quantity: item.quantity,
          unit: item.unit,
          status: statusFor(item.quantity, capacity),
          fill: fillRatio(item.quantity, capacity),
          depot: snapshot.location,
        };
      }),
    ),
  );
}

function byNeed(left: StockLine, right: StockLine): number {
  return left.fill - right.fill || left.name.localeCompare(right.name);
}

function restockSentence(lines: StockLine[]): string {
  const urgent = lines.filter((line) => line.fill < 30).sort(byNeed);
  if (urgent.length === 0) {
    const low = lines.filter((line) => line.status === "Low Stock").length;
    if (low === 0) return "No items are below the restock threshold.";
    return low === 1 ? "1 item is low on stock." : `${low} items are low on stock.`;
  }
  const names = urgent.slice(0, 3).map((line) => `${line.name} (${line.depot})`);
  if (urgent.length === 1) return `Consider restocking ${names[0]}.`;
  if (urgent.length === 2) return `Consider restocking ${names[0]} and ${names[1]}.`;
  const listed = `${names.slice(0, -1).join(", ")}, and ${names[names.length - 1]}`;
  const extra = urgent.length > 3 ? `, plus ${urgent.length - 3} more` : "";
  return `Consider restocking ${listed}${extra}.`;
}

function lineTotals(row: AllocationTownshipRow): { requested: number; allocated: number } {
  const requested =
    row.requested_total ?? row.line_items.reduce((sum, item) => sum + item.requested, 0);
  const allocated =
    row.allocated_total ?? row.line_items.reduce((sum, item) => sum + item.allocated, 0);
  return { requested, allocated };
}

function priorityLabel(priority: AssistancePriority): string {
  if (priority === "none") return "None";
  return riskLabel(priority);
}

function FitPoints({ points }: { points: [number, number][] }) {
  const map = useMap();
  useEffect(() => {
    if (points.length === 0 || typeof map.getContainer !== "function") return;
    const container = map.getContainer();
    const fit = () => {
      try {
        map.invalidateSize();
        map.fitBounds(points, { padding: [18, 18], maxZoom: 9 });
      } catch {
        // Leaflet can throw if the map is torn down during a reload.
      }
    };
    const frame = requestAnimationFrame(fit);
    if (typeof ResizeObserver === "undefined") {
      return () => cancelAnimationFrame(frame);
    }
    const observer = new ResizeObserver(() => {
      const size = map.getSize();
      const box = container.getBoundingClientRect();
      if (Math.abs(size.x - box.width) > 2 || Math.abs(size.y - box.height) > 2) fit();
    });
    observer.observe(container);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, [map, points]);
  return null;
}

function RainSparkline({ points }: { points: { lead: number; mm: number }[] }) {
  if (points.length === 0) return null;
  const width = 280;
  const height = 72;
  const pad = { top: 8, right: 8, bottom: 8, left: 8 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const max = Math.max(...points.map((point) => point.mm), 1);
  const coords = points.map((point, index) => {
    const x = pad.left + (index / Math.max(points.length - 1, 1)) * innerW;
    const y = pad.top + innerH - (point.mm / max) * innerH;
    return `${x},${y}`;
  });

  return (
    <svg className="home-spark" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Forecast rainfall sparkline">
      <polyline points={coords.join(" ")} />
      {points.map((point, index) => {
        const [x, y] = coords[index].split(",");
        return <circle key={point.lead} cx={x} cy={y} r="3" />;
      })}
    </svg>
  );
}

export default function HomeDashboard({ areas, onOpenPage, onPlanResources }: HomeDashboardProps) {
  const [forecast, setForecast] = useState<Resource<RegionForecastResponse>>(loading);
  const [plan, setPlan] = useState<Resource<AllocationPlanResponse>>(loading);
  const [inventory, setInventory] = useState<Resource<InventorySnapshot[]>>(loading);
  const [homeList, setHomeList] = useState<null | "risk" | "plan" | "stock">(null);
  const [homePage, setHomePage] = useState(0);
  const asOf = useMemo(() => localDate(), []);

  useEffect(() => {
    let active = true;
    api
      .predictionRegionForecast(asOf)
      .then((data) => {
        if (active) setForecast({ state: "ready", data });
      })
      .catch((reason: unknown) => {
        if (active) setForecast({ state: "error", error: errorText(reason) });
      });
    return () => {
      active = false;
    };
  }, [asOf]);

  useEffect(() => {
    let active = true;
    api
      .allocationPlans()
      .then(async (plans) => {
        if (!active) return;
        const latest = newestPlan(plans);
        if (!latest) {
          setPlan({ state: "empty" });
          return;
        }
        try {
          const detail = await api.allocationPlanDetail(latest.plan_id);
          if (active) setPlan({ state: "ready", data: detail });
        } catch (reason: unknown) {
          if (active) setPlan({ state: "error", error: errorText(reason) });
        }
      })
      .catch((reason: unknown) => {
        if (active) setPlan({ state: "error", error: errorText(reason) });
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    api
      .inventoryLocations()
      .then((data) => {
        if (active) setInventory({ state: data.locations.length ? "ready" : "empty", data: data.locations });
      })
      .catch((reason: unknown) => {
        if (active) setInventory({ state: "error", error: errorText(reason) });
      });
    return () => {
      active = false;
    };
  }, []);

  const scores = forecast.data?.scores ?? [];
  const today = scores.filter((score) => score.lead_days === 0);
  const windowScores = scores.filter((score) => score.lead_days >= 0 && score.lead_days <= 3);
  const rankedToday = [...today].sort((left, right) => {
    const rankedLeft = rankOutlook(left);
    const rankedRight = rankOutlook(right);
    return (
      levelRank(rankedRight.level) - levelRank(rankedLeft.level) ||
      rankedRight.probability - rankedLeft.probability
    );
  });
  const worst = rankedToday[0];
  const highDistricts = new Set(
    today
      .filter((score) => {
        const level = rankOutlook(score).level;
        return level === "high" || level === "severe";
      })
      .map((score) => score.district_id),
  );
  const rainfallValues = windowScores
    .map((score) => score.rainfall_mm)
    .filter((value): value is number => value != null);
  const discharge = [...windowScores]
    .filter((score) => score.discharge_m3_s != null)
    .sort(
      (left, right) =>
        (right.discharge_m3_s ?? 0) - (left.discharge_m3_s ?? 0) ||
        (right.flood_probability ?? -1) - (left.flood_probability ?? -1),
    )[0];
  const peak = rankedToday[0];
  const rainfallSeries = peak
    ? windowScores
        .filter((score) => score.township_id === peak.township_id && score.rainfall_mm != null)
        .sort((left, right) => left.lead_days - right.lead_days)
        .map((score) => ({ lead: score.lead_days, mm: score.rainfall_mm as number }))
    : [];

  const lines = useMemo(() => stockLines(inventory.data ?? []), [inventory.data]);
  const attentionAll = [...lines]
    .filter((line) => line.status === "Out of Stock" || line.status === "Critical" || line.status === "Low Stock")
    .sort(byNeed);
  const attention = attentionAll.slice(0, 4);
  const inStock = lines.filter((line) => line.status === "In Stock" || line.status === "Full").length;
  const lowStock = lines.filter((line) => line.status === "Critical" || line.status === "Low Stock").length;
  const outOfStock = lines.filter((line) => line.status === "Out of Stock").length;

  const allocationRowsAll = [...(plan.data?.rows ?? [])]
    .sort((left, right) => levelRank(right.priority) - levelRank(left.priority) || left.township_name.localeCompare(right.township_name));
  const allocationRows = allocationRowsAll.slice(0, 4);

  const townships = areas.data?.districts.flatMap((district) =>
    district.townships.map((township) => ({
      ...township,
      color: districtColor(district.id),
    })),
  ) ?? [];
  const todayByTownship = new Map(today.map((score) => [score.township_id, score]));
  const mapPoints = townships.map((township) => [township.latitude, township.longitude] as [number, number]);

  const planTownship = (score: RegionForecastScore) => {
    const outlook = rankOutlook(score);
    const fromAreas = townships.find((township) => township.id === score.township_id);
    const latitude = score.latitude ?? fromAreas?.latitude;
    const longitude = score.longitude ?? fromAreas?.longitude;
    if (latitude == null || longitude == null) return;
    if (outlook.level !== "high" && outlook.level !== "severe") return;
    const riskLevel: RiskLevel = outlook.level === "severe" ? "severe" : "high";
    onPlanResources({
      townshipId: score.township_id,
      townshipName: score.township_name,
      date: score.target_date,
      riskLevel,
      latitude,
      longitude,
      floodProbability: score.flood_probability,
    });
  };

  return (
    <main className="home-board">
      <section className="home-kpis" aria-label="Overview">
        <article className="home-kpi">
          <span>Overall flood risk</span>
          <strong>{forecast.state === "loading" ? "…" : forecast.state === "error" ? "—" : riskLabel(worst ? rankOutlook(worst).level : worst?.risk_level)}</strong>
          <small>
            {forecast.state === "loading"
              ? "Loading today's scores"
              : forecast.state === "error"
                ? "Forecast unavailable"
                : highDistricts.size === 0
                  ? "No district is high or severe"
                  : `High or severe in ${highDistricts.size} ${highDistricts.size === 1 ? "district" : "districts"}`}
          </small>
        </article>
        <article className="home-kpi">
          <span>Forecast rainfall</span>
          <strong>{forecast.state === "loading" ? "…" : forecast.state === "error" ? "—" : formatRainRange(rainfallValues)}</strong>
          <small>Lead days 0–3</small>
        </article>
        <article className="home-kpi">
          <span>Modeled discharge</span>
          <strong>
            {forecast.state === "loading"
              ? "…"
              : forecast.state === "error" || discharge?.discharge_m3_s == null
                ? "—"
                : `${formatNumber(discharge.discharge_m3_s)} m³/s`}
          </strong>
          <small>{forecast.state === "error" ? "Forecast unavailable" : discharge?.township_name ?? "No discharge in this window"}</small>
        </article>
        <article className="home-kpi">
          <span>People in latest plan</span>
          <strong>
            {plan.state === "loading"
              ? "…"
              : plan.state === "ready"
                ? formatNumber(plan.data?.totals.affected_population ?? 0)
                : "—"}
          </strong>
          {plan.state === "empty" ? (
            <button type="button" className="text-link" onClick={() => onOpenPage("allocation")}>
              Open resource allocation
            </button>
          ) : (
            <small>
              {plan.state === "error"
                ? "Plan unavailable"
                : plan.data?.planning_date
                  ? `Latest plan · ${plan.data.planning_date}`
                  : "Affected people on the saved plan"}
            </small>
          )}
        </article>
      </section>

      <div className="home-columns">
        <article className="panel home-column">
          <div className="section-heading">
            <h2>Flood Prediction</h2>
            <button type="button" className="text-link" onClick={() => onOpenPage("prediction")}>
              Open flood prediction
            </button>
          </div>
          {areas.state === "error" && <p className="state error">Map areas could not be loaded. {areas.error}</p>}
          <div className="map-frame home-map">
            <MapContainer center={[18.26, 96.07]} zoom={8} scrollWheelZoom={false} aria-label="Bago flood risk summary">
              <BasemapTileLayer />
              <MapViewportFix />
              <FitPoints points={mapPoints} />
              {townships.map((township) => {
                if (!township.geometry) return null;
                const score = todayByTownship.get(township.id);
                const fillLevel = score ? floodFillLevel(score) : "unknown";
                const fill = score ? riskColor(fillLevel) : township.color;
                return (
                  <GeoJSON
                    key={township.id}
                    data={township.geometry as GeoJsonObject}
                    interactive={false}
                    style={{
                      color: township.color,
                      weight: 1.5,
                      fillColor: fill,
                      fillOpacity: score ? 0.62 : 0.2,
                    }}
                  />
                );
              })}
            </MapContainer>
          </div>
          <ul className="legend" aria-label="Flood risk bands">
            <li><i style={{ background: "#2d9c6c" }} />Low</li>
            <li><i style={{ background: "#c49212" }} />Medium</li>
            <li><i style={{ background: "#d86a1a" }} />High</li>
            <li><i style={{ background: "#a83232" }} />Severe</li>
          </ul>
          {forecast.state === "loading" && <p className="state">Loading flood outlook…</p>}
          {forecast.state === "error" && (
            <p className="state error">Flood forecast could not be loaded. {forecast.error}</p>
          )}
          {forecast.state === "ready" && rankedToday.length === 0 && (
            <p className="state">No township scores for today.</p>
          )}
          {rankedToday.length > 0 && (
            <>
            <ul className="home-list">
              {rankedToday.slice(0, 4).map((score) => {
                const outlook = rankOutlook(score);
                const canPlan =
                  needsResourceAllocation(outlook.level) &&
                  (score.latitude != null || townships.some((township) => township.id === score.township_id));
                return (
                  <li key={score.township_id}>
                    <strong>{score.township_name}</strong>
                    <span className={`risk-pill risk-${outlook.level === "unknown" ? "none" : outlook.level}`}>
                      {riskLabel(outlook.level)}
                    </span>
                    <span>{formatPercent(score.flood_probability)}</span>
                    {canPlan && (
                      <button type="button" className="text-link" onClick={() => planTownship(score)}>
                        Plan resources
                      </button>
                    )}
                  </li>
                );
              })}
            </ul>
            {rankedToday.length > 4 ? (
              <button type="button" className="text-link" onClick={() => { setHomePage(0); setHomeList("risk"); }}>
                View townships
              </button>
            ) : null}
            </>
          )}
          {peak && rainfallSeries.length > 0 && (
            <div>
              <p className="hint">
                Rainfall · {peak.township_name}:{" "}
                {rainfallSeries.map((point) => `day ${point.lead} ${formatNumber(point.mm, 1)} mm`).join(", ")}
              </p>
              <RainSparkline points={rainfallSeries} />
            </div>
          )}
        </article>

        <article className="panel home-column">
          <div className="section-heading">
            <h2>Resource Allocation</h2>
            <button type="button" className="text-link" onClick={() => onOpenPage("allocation")}>
              Open resource allocation
            </button>
          </div>
          {plan.state === "loading" && <p className="state">Loading the latest plan…</p>}
          {plan.state === "error" && <p className="state error">The latest plan could not be loaded. {plan.error}</p>}
          {plan.state === "empty" && (
            <p className="state">No allocation plan yet. Create one from Resource Allocation.</p>
          )}
          {plan.state === "ready" && plan.data && (
            <>
              <p className="hint">
                {plan.data.status === "confirmed" ? "Confirmed" : "Draft"} · {plan.data.planning_date} ·{" "}
                {formatNumber(plan.data.shortages.length)} unmet {plan.data.shortages.length === 1 ? "line" : "lines"}
              </p>
              {allocationRows.length === 0 ? (
                <p className="state">This plan has no township allocations.</p>
              ) : (
                <ul className="home-list">
                  {allocationRows.map((row) => {
                    const totals = lineTotals(row);
                    return (
                      <li key={row.township_id}>
                        <strong>{row.township_name}</strong>
                        <span className={`risk-pill risk-${row.priority === "none" ? "none" : row.priority}`}>
                          {priorityLabel(row.priority)}
                        </span>
                        <span>
                          {formatNumber(totals.allocated)} allocated of {formatNumber(totals.requested)} requested
                        </span>
                      </li>
                    );
                  })}
                </ul>
              )}
              {allocationRowsAll.length > 4 ? (
                <button type="button" className="text-link" onClick={() => { setHomePage(0); setHomeList("plan"); }}>
                  View plan
                </button>
              ) : null}
            </>
          )}
        </article>

        <article className="panel home-column">
          <div className="section-heading">
            <h2>Inventory Management</h2>
            <button type="button" className="text-link" onClick={() => onOpenPage("inventory")}>
              Open inventory
            </button>
          </div>
          {inventory.state === "loading" && <p className="state">Loading stock…</p>}
          {inventory.state === "error" && (
            <p className="state error">Inventory could not be loaded. {inventory.error}</p>
          )}
          {(inventory.state === "ready" || inventory.state === "empty") && (
            <>
              <div className="home-counts" role="group" aria-label="Stock counts">
                <div>
                  <span>Items</span>
                  <strong>{formatNumber(lines.length)}</strong>
                </div>
                <div>
                  <span>In stock</span>
                  <strong>{formatNumber(inStock)}</strong>
                </div>
                <div>
                  <span>Low stock</span>
                  <strong>{formatNumber(lowStock)}</strong>
                </div>
                <div>
                  <span>Out of stock</span>
                  <strong>{formatNumber(outOfStock)}</strong>
                </div>
              </div>
              {attention.length === 0 ? (
                <p className="state">No items need restocking.</p>
              ) : (
                <ul className="home-list">
                  {attention.map((line) => (
                    <li key={line.key}>
                      <strong>{line.name}</strong>
                      <span className={`stock-pill stock-${statusSlug(line.status)}`}>{line.status}</span>
                      <span>
                        {formatNumber(line.quantity)} {line.unit} · {line.depot}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
              {attentionAll.length > 4 ? (
                <button type="button" className="text-link" onClick={() => { setHomePage(0); setHomeList("stock"); }}>
                  View stock
                </button>
              ) : null}
              <p className="home-suggest">{restockSentence(lines)}</p>
            </>
          )}
        </article>
      </div>

      <HomeFloodHistory areas={areas.data} onPlanResources={onPlanResources} />

      <ViewDialog
        title={homeList === "risk" ? "Townships" : homeList === "plan" ? "Allocation plan" : "Stock to restock"}
        open={homeList != null}
        onClose={() => setHomeList(null)}
      >
        <ul className="home-list">
          {homeList === "risk"
            ? rankedToday.slice(homePage * 6, homePage * 6 + 6).map((score) => (
                <li key={score.township_id}>
                  <strong>{score.township_name}</strong>
                  <span>{riskLabel(rankOutlook(score).level)}</span>
                  <span>{formatPercent(score.flood_probability)}</span>
                </li>
              ))
            : null}
          {homeList === "plan"
            ? allocationRowsAll.slice(homePage * 6, homePage * 6 + 6).map((row) => (
                <li key={row.township_id}>
                  <strong>{row.township_name}</strong>
                  <span>{priorityLabel(row.priority)}</span>
                </li>
              ))
            : null}
          {homeList === "stock"
            ? attentionAll.slice(homePage * 6, homePage * 6 + 6).map((line) => (
                <li key={line.key}>
                  <strong>{line.name}</strong>
                  <span>{line.status}</span>
                  <span>
                    {formatNumber(line.quantity)} {line.unit}
                  </span>
                </li>
              ))
            : null}
        </ul>
        <PageControls
          page={homePage}
          pages={Math.max(
            1,
            Math.ceil(
              (homeList === "risk" ? rankedToday.length : homeList === "plan" ? allocationRowsAll.length : attentionAll.length) / 6,
            ),
          )}
          onPage={setHomePage}
        />
      </ViewDialog>
    </main>
  );
}
