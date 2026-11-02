import { useEffect, useMemo, useState } from "react";
import { CircleMarker, GeoJSON, MapContainer, Pane, Popup, useMap } from "react-leaflet";
import BasemapTileLayer from "./components/map/BasemapTileLayer";
import MapViewportFix from "./components/map/MapViewportFix";
import type { GeoJsonObject } from "geojson";
import AllocationPrompt from "./components/prediction/AllocationPrompt";
import DailyDetailPanel from "./components/prediction/DailyDetailPanel";
import HazardDepthPanel from "./components/prediction/HazardDepthPanel";
import { PageControls, ViewDialog } from "./components/ViewDialog";
import type { AllocationFocus } from "./lib/allocationFocus";
import { districtColor, displayRiskLevel, floodBandLabel, floodFillLevel, formatPercent, riskColor } from "./components/prediction/mapUtils";
import { usePredictionTimeline } from "./hooks/usePredictionTimeline";
import type {
  BagoAreasResponse,
  HealthResponse,
  InundationProduct,
  JobRun,
  LoadState,
  PredictionTimelineDay,
  RegionForecastScore,
  SettlementPoint,
} from "./types";

interface Resource<T> {
  state: LoadState;
  data?: T;
  error?: string;
}

function preferredTownshipId(districts: BagoAreasResponse["districts"]): string {
  const bagoDistrict = districts.find((district) => district.name_en === "Bago");
  const bagoTownship = bagoDistrict?.townships.find((township) => township.name_en === "Bago");
  return bagoTownship?.id ?? districts[0]?.townships[0]?.id ?? "";
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

function outlookFromForecast(score: RegionForecastScore): PredictionTimelineDay {
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

function TownshipPopup({
  name,
  probability,
  level,
  earlyWarning,
}: {
  name: string;
  probability: number | null | undefined;
  level: string | null | undefined;
  earlyWarning?: boolean;
}) {
  return (
    <Popup>
      <strong>{name}</strong>
      <br />
      {formatPercent(probability)} · {floodBandLabel(level)}
      {earlyWarning ? (
        <>
          <br />
          Early warning
        </>
      ) : null}
    </Popup>
  );
}

function HistoryStack({ primary, secondary }: { primary: string; secondary?: string }) {
  return (
    <span className="history-stack">
      <b>{primary}</b>
      {secondary ? <small>{secondary}</small> : null}
    </span>
  );
}

function historyMonthDay(iso: string): string {
  const [, month, day] = iso.split("-");
  return `${month}-${day}`;
}

function DayGroup({
  title,
  days,
  selectedDate,
  showEmpty,
  empty,
  onSelect,
}: {
  title: string;
  days: PredictionTimelineDay[];
  selectedDate: string;
  showEmpty: boolean;
  empty: string;
  onSelect: (date: string) => void;
}) {
  return (
    <section className="history-group">
      <div className="history-table" role="table" aria-label={title}>
        <div className="history-row region header" role="row">
          <span>Date</span>
          <span>Rainfall</span>
          <span>River discharge</span>
          <span>Risk</span>
        </div>
        {days.map((day) => {
          const rainfall = day.rainfall_mm == null ? "—" : `${day.rainfall_mm.toFixed(1)} mm`;
          const discharge = day.discharge_m3_s == null ? "—" : `${day.discharge_m3_s.toFixed(1)} m³/s`;
          return (
          <button
            type="button"
            key={day.date}
            className={`history-row region selectable ${selectedDate === day.date ? "selected" : ""}`}
            aria-label={`${day.date} ${rainfall} ${discharge} ${floodBandLabel(day.probability_risk_level)}`}
            onClick={() => onSelect(day.date)}
          >
            <strong className="history-day">{historyMonthDay(day.date)}</strong>
            {day.rainfall_mm == null ? (
              <span>—</span>
            ) : (
              <HistoryStack primary={day.rainfall_mm.toFixed(1)} secondary="mm" />
            )}
            {day.discharge_m3_s == null ? (
              <span>—</span>
            ) : (
              <HistoryStack primary={day.discharge_m3_s.toFixed(1)} secondary="m³/s" />
            )}
            <span className={`risk-pill risk-${day.probability_risk_level ?? "none"}`}>
              {floodBandLabel(day.probability_risk_level)}
            </span>
          </button>
          );
        })}
        {showEmpty && days.length === 0 && <p className="hint">{empty}</p>}
      </div>
    </section>
  );
}

export interface PredictionMapContext {
  regionLabel: string;
  districtName: string;
  townshipName: string;
}

interface FloodPredictionDashboardProps {
  areas: Resource<BagoAreasResponse>;
  health: Resource<HealthResponse>;
  runs: Resource<JobRun[]>;
  inundation: Resource<InundationProduct[]>;
  settlements: Resource<SettlementPoint[]>;
  onPlanResources?: (focus: AllocationFocus) => void;
  onMapContextChange?: (context: PredictionMapContext | null) => void;
}

export default function FloodPredictionDashboard({
  areas,
  inundation,
  settlements,
  onPlanResources,
  onMapContextChange,
}: FloodPredictionDashboardProps) {
  const [selectedTownship, setSelectedTownship] = useState("");
  const [districtFilter, setDistrictFilter] = useState("all");
  const [historyView, setHistoryView] = useState<"next" | "past">("next");
  const [outlookOpen, setOutlookOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyPage, setHistoryPage] = useState(0);

  useEffect(() => {
    if (areas.data && !selectedTownship) {
      setSelectedTownship(preferredTownshipId(areas.data.districts));
    }
  }, [areas.data, selectedTownship]);

  const {
    anchorDate,
    setAnchorDate,
    dateMin,
    dateMax,
    selectedDate,
    setSelectedDate,
    timeline,
    selectedDay,
    scoresByTownship,
  } = usePredictionTimeline(areas.data, selectedTownship, districtFilter);

  const visibleDistricts = useMemo(() => {
    const districts = areas.data?.districts ?? [];
    if (districtFilter === "all") return districts;
    return districts.filter((district) => district.id === districtFilter);
  }, [areas.data, districtFilter]);

  const visibleTownships = useMemo(
    () =>
      visibleDistricts.flatMap((district) =>
        district.townships.map((township) => ({
          ...township,
          districtId: district.id,
          districtName: district.name_en,
          color: districtColor(district.id),
        })),
      ),
    [visibleDistricts],
  );

  useEffect(() => {
    if (districtFilter === "all" || !areas.data) return;
    const district = areas.data.districts.find((item) => item.id === districtFilter);
    if (!district) return;
    const stillValid = district.townships.some((township) => township.id === selectedTownship);
    if (!stillValid && district.townships[0]) {
      setSelectedTownship(district.townships[0].id);
    }
  }, [districtFilter, areas.data, selectedTownship]);

  const mapPoints = useMemo<[number, number][]>(
    () => visibleTownships.map((township) => [township.latitude, township.longitude]),
    [visibleTownships],
  );

  const chooseTownship = (id: string) => {
    setSelectedTownship(id);
  };

  const selectedTownshipMeta = useMemo(() => {
    for (const district of areas.data?.districts ?? []) {
      const match = district.townships.find((township) => township.id === selectedTownship);
      if (match) {
        return {
          name: match.name_en,
          latitude: match.latitude,
          longitude: match.longitude,
          districtName: district.name_en,
        };
      }
    }
    return null;
  }, [areas.data, selectedTownship]);

  useEffect(() => {
    if (!onMapContextChange) return;
    if (!selectedTownshipMeta) {
      onMapContextChange(null);
      return;
    }
    onMapContextChange({
      regionLabel: "Bago Region, Myanmar",
      districtName: selectedTownshipMeta.districtName,
      townshipName: selectedTownshipMeta.name,
    });
  }, [onMapContextChange, selectedTownshipMeta]);

  const timelineDays = timeline.data?.days ?? [];
  const pastDays = timelineDays.filter((day) => day.period_type === "historical");
  const forecastDays = timelineDays.filter((day) => day.period_type === "forecast");
  const timelineReady = timeline.state === "ready";
  const selectedForecast = scoresByTownship.get(selectedTownship);
  const forecastForDay =
    selectedForecast && "target_date" in selectedForecast && selectedForecast.target_date === selectedDate
      ? (selectedForecast as RegionForecastScore)
      : undefined;
  const forecastOutlook =
    forecastForDay && forecastForDay.data_status !== "unavailable" && forecastForDay.flood_probability != null
      ? outlookFromForecast(forecastForDay)
      : undefined;
  const panelDay = selectedDay ?? forecastOutlook;

  const modelScoreForTownship = (
    townshipId: string,
    score: ReturnType<typeof scoresByTownship.get>,
  ) => {
    if (
      townshipId === selectedTownship &&
      panelDay?.date === selectedDate &&
      panelDay.probability_risk_level
    ) {
      return {
        probability_risk_level: panelDay.probability_risk_level,
        risk_level: panelDay.risk_level,
        flood_probability: panelDay.flood_probability,
      };
    }
    return score;
  };

  const districtChips = (
    <div className="chip-row" role="group" aria-label="Bago districts" data-testid="district-chips">
      <button
        type="button"
        className={districtFilter === "all" ? "active" : ""}
        onClick={() => setDistrictFilter("all")}
      >
        All districts
      </button>
      {areas.data?.districts.map((district) => (
        <button
          key={district.id}
          type="button"
          className={districtFilter === district.id ? "active" : ""}
          onClick={() => setDistrictFilter(district.id)}
        >
          {district.name_en}
        </button>
      ))}
    </div>
  );

  return (
    <main className="predict-board">
      <div className="predict-split">
        <article className="panel map-panel">
          {districtChips}
          {areas.state === "error" && <p className="state error">Unavailable: {areas.error}</p>}
          <div className="map-frame">
            <MapContainer center={[18.26, 96.07]} zoom={8} scrollWheelZoom={false} aria-label="Bago flood risk map">
              <BasemapTileLayer />
              <MapViewportFix />
              <FitPoints points={mapPoints} />
              {inundation.data?.map((product) => (
                <GeoJSON
                  key={`inundation-${product.id}`}
                  data={product.geometry as GeoJsonObject}
                  style={{ color: "#2457a6", fillColor: "#3b82d0", fillOpacity: 0.28, weight: 1 }}
                />
              ))}
              {visibleTownships.map((township) => {
                if (!township.geometry) return null;
                const score = modelScoreForTownship(township.id, scoresByTownship.get(township.id));
                const selected = township.id === selectedTownship;
                const fillLevel = score ? floodFillLevel(score) : "unknown";
                const fill = score ? riskColor(fillLevel) : township.color;
                return (
                  <GeoJSON
                    key={`${township.id}:${selected ? "on" : "off"}:${fillLevel}`}
                    data={township.geometry as GeoJsonObject}
                    style={{
                      color: selected ? "#f4fbff" : township.color,
                      weight: selected ? 3.5 : 1.5,
                      fillColor: fill,
                      fillOpacity: score ? 0.62 : 0.2,
                    }}
                    interactive={false}
                  />
                );
              })}
              <Pane name="district-outlines" style={{ zIndex: 450, pointerEvents: "none" }}>
                {areas.data?.districts.map(
                  (district) =>
                    district.geometry && (
                      <GeoJSON
                        key={`district-${district.id}-${districtFilter}`}
                        data={district.geometry as GeoJsonObject}
                        interactive={false}
                        style={{
                          color: districtColor(district.id),
                          weight: districtFilter === district.id ? 3 : 2,
                          fill: false,
                          fillOpacity: 0,
                        }}
                      />
                    ),
                )}
              </Pane>
              <Pane name="township-pins" style={{ zIndex: 520 }}>
                {visibleTownships.map((township) => {
                  const score = modelScoreForTownship(township.id, scoresByTownship.get(township.id));
                  const selected = township.id === selectedTownship;
                  const fillLevel = score ? floodFillLevel(score) : "unknown";
                  const fill = score ? riskColor(fillLevel) : township.color;
                  const earlyWarning = Boolean(
                    score && "early_warning" in score && score.early_warning,
                  );
                  return (
                    <CircleMarker
                      key={`pin-${township.id}-${fillLevel}`}
                      center={[township.latitude, township.longitude]}
                      radius={selected ? 9 : 7}
                      pathOptions={{
                        color: selected ? "#ffffff" : "#0b1624",
                        fillColor: fill,
                        fillOpacity: 0.95,
                        weight: selected ? 3 : 2,
                      }}
                      eventHandlers={{
                        click: () => chooseTownship(township.id),
                        mouseover: (event) => {
                          event.target.openPopup();
                        },
                      }}
                    >
                      <TownshipPopup
                        name={township.name_en}
                        probability={
                          score && "flood_probability" in score ? score.flood_probability : undefined
                        }
                        level={displayRiskLevel(score)}
                        earlyWarning={earlyWarning}
                      />
                    </CircleMarker>
                  );
                })}
              </Pane>
              {settlements.data?.map((settlement) => (
                <CircleMarker
                  key={`settlement-${settlement.id}`}
                  center={[settlement.latitude, settlement.longitude]}
                  radius={3}
                  pathOptions={{ color: "#3f5965", fillColor: "#ffffff", fillOpacity: 0.9, weight: 1 }}
                />
              ))}
            </MapContainer>
          </div>
          <p className="hint" role="status">
            Map colors use the gradient-boosting flood model for{" "}
            <strong>{selectedDate}</strong>
            {selectedDate !== anchorDate ? ` (timeline centered on ${anchorDate})` : ""}.
            Pick another day in the table to update the map.
          </p>
          <ul className="legend" aria-label="Flood risk bands">
            <li><i style={{ background: "#2d9c6c" }} />low</li>
            <li><i style={{ background: "#c49212" }} />moderate</li>
            <li><i style={{ background: "#d86a1a" }} />high</li>
            <li><i style={{ background: "#a83232" }} />severe</li>
          </ul>
          <ul className="district-legend">
            {(areas.data?.districts ?? []).map((district) => (
              <li key={district.id}>
                <i style={{ background: districtColor(district.id) }} />
                {district.name_en} · {district.townships.length} townships
              </li>
            ))}
          </ul>
        </article>

        <aside className="predict-rail prediction-center">
          <article className="panel flood-now">
            <div className="prediction-title-row">
              <h2 className="prediction-panel-title">Flood prediction</h2>
              <p className="prediction-year">
                <span className="field-label">Year</span>
                <strong>{(selectedDate || anchorDate).slice(0, 4)}</strong>
              </p>
            </div>
            <div className="prediction-choices">
              <label className="township-side prediction-plan-date">
                <span className="field-label">Selected date</span>
                <input
                  type="date"
                  value={anchorDate}
                  min={dateMin}
                  max={dateMax}
                  onChange={(event) => setAnchorDate(event.target.value)}
                  aria-label="Selected date"
                />
              </label>
              <label className="township-side township-choice">
                <span className="field-label">Selected township</span>
                <select
                  id="selected-township-name"
                  aria-label="Selected township"
                  value={selectedTownship}
                  disabled={!areas.data}
                  onChange={(event) => chooseTownship(event.target.value)}
                >
                  {!areas.data ? (
                    <option value="">Loading…</option>
                  ) : districtFilter === "all" ? (
                    visibleDistricts.map((district) => (
                      <optgroup key={district.id} label={`${district.name_en} District`}>
                        {district.townships.map((township) => (
                          <option key={township.id} value={township.id}>
                            {township.name_en}
                          </option>
                        ))}
                      </optgroup>
                    ))
                  ) : (
                    visibleDistricts[0]?.townships.map((township) => (
                      <option key={township.id} value={township.id}>
                        {township.name_en}
                      </option>
                    ))
                  )}
                </select>
              </label>
            </div>
            <button type="button" className="text-link" onClick={() => setOutlookOpen(true)}>
              Prediction details
            </button>
            <DailyDetailPanel day={panelDay} />
            <AllocationPrompt
              day={panelDay}
              townshipName={selectedTownshipMeta?.name ?? "Selected township"}
              onPlanResources={() => {
                if (!onPlanResources || !panelDay || !selectedTownshipMeta) return;
                onPlanResources({
                  townshipId: selectedTownship,
                  townshipName: selectedTownshipMeta.name,
                  date: panelDay.date,
                  riskLevel: panelDay.probability_risk_level ?? "low",
                  latitude: selectedTownshipMeta.latitude,
                  longitude: selectedTownshipMeta.longitude,
                  expectedAffected:
                    panelDay.potentially_affected_population ??
                    panelDay.recorded_affected_people ??
                    undefined,
                  floodProbability: panelDay.flood_probability,
                });
              }}
            />
            {timeline.state === "error" && <p className="state error">Unavailable: {timeline.error}</p>}
          </article>
        </aside>

        <article className="panel history-panel">
          <div className="history-switch" role="group" aria-label="Forecast history">
            <button
              type="button"
              className={historyView === "next" ? "active" : ""}
              aria-pressed={historyView === "next"}
              onClick={() => setHistoryView("next")}
            >
              Next 7 days
            </button>
            <button
              type="button"
              className={historyView === "past" ? "active" : ""}
              aria-pressed={historyView === "past"}
              onClick={() => setHistoryView("past")}
            >
              Previous 7 days
            </button>
          </div>
          <div className="history-scroll">
            {historyView === "next" ? (
              <DayGroup
                title="Next 7 days"
                days={forecastDays}
                selectedDate={selectedDate}
                showEmpty={timelineReady}
                empty="No forecast scores for this township."
                onSelect={setSelectedDate}
              />
            ) : (
              <DayGroup
                title="Previous 7 days"
                days={pastDays}
                selectedDate={selectedDate}
                showEmpty={timelineReady}
                empty="No previous-day scores for this township."
                onSelect={setSelectedDate}
              />
            )}
            <button
              type="button"
              className="text-link"
              onClick={() => {
                setHistoryPage(0);
                setHistoryOpen(true);
              }}
            >
              View days
            </button>
          </div>
        </article>
      </div>
      <ViewDialog title="Prediction details" open={outlookOpen} onClose={() => setOutlookOpen(false)}>
        {selectedTownship ? <HazardDepthPanel townshipId={selectedTownship} /> : null}
        <AllocationPrompt
          day={panelDay}
          townshipName={selectedTownshipMeta?.name ?? "Selected township"}
          onPlanResources={() => {
            if (!onPlanResources || !panelDay || !selectedTownshipMeta) return;
            setOutlookOpen(false);
            onPlanResources({
              townshipId: selectedTownship,
              townshipName: selectedTownshipMeta.name,
              date: panelDay.date,
              riskLevel: panelDay.probability_risk_level ?? "low",
              latitude: selectedTownshipMeta.latitude,
              longitude: selectedTownshipMeta.longitude,
              expectedAffected:
                panelDay.potentially_affected_population ??
                panelDay.recorded_affected_people ??
                undefined,
              floodProbability: panelDay.flood_probability,
            });
          }}
        />
      </ViewDialog>
      <ViewDialog title={historyView === "next" ? "Next 7 days" : "Previous 7 days"} open={historyOpen} onClose={() => setHistoryOpen(false)}>
        <DayGroup
          title={historyView === "next" ? "Next 7 days" : "Previous 7 days"}
          days={(historyView === "next" ? forecastDays : pastDays).slice(historyPage * 4, historyPage * 4 + 4)}
          selectedDate={selectedDate}
          showEmpty={timelineReady}
          empty="No scores for this township."
          onSelect={(date) => {
            setSelectedDate(date);
            setHistoryOpen(false);
          }}
        />
        <PageControls
          page={historyPage}
          pages={Math.max(1, Math.ceil((historyView === "next" ? forecastDays : pastDays).length / 4))}
          onPage={setHistoryPage}
        />
      </ViewDialog>
    </main>
  );
}
