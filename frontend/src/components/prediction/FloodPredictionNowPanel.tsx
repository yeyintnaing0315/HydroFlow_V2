import { useMemo } from "react";
import { usePredictionTimeline } from "../../hooks/usePredictionTimeline";
import type { AllocationFocus } from "../../lib/allocationFocus";
import { outlookFromForecast } from "../../lib/outlookFromForecast";
import type {
  BagoAreasResponse,
  LoadState,
  PredictionTimelineDay,
  PredictionTimelineResponse,
  RegionForecastScore,
  TownshipMapScore,
} from "../../types";
import AllocationPrompt from "./AllocationPrompt";
import DailyDetailPanel from "./DailyDetailPanel";
import LoadingSpinner from "./LoadingSpinner";

interface Resource<T> {
  state: LoadState;
  data?: T;
  error?: string;
}

export interface PredictionNowTimelineControl {
  anchorDate: string;
  setAnchorDate: (value: string) => void;
  dateMin: string;
  dateMax: string;
  selectedDate: string;
  timeline: Resource<PredictionTimelineResponse>;
  selectedDay: PredictionTimelineDay | undefined;
  scoresByTownship: Map<string, TownshipMapScore | RegionForecastScore>;
}

interface FloodPredictionNowPanelProps {
  areas: Resource<BagoAreasResponse>;
  selectedTownship: string;
  onSelectTownship: (townshipId: string) => void;
  districtFilter?: string;
  embedded?: boolean;
  timelineControl?: PredictionNowTimelineControl;
  onPlanResources?: (focus: AllocationFocus) => void;
  onPredictionDetails?: () => void;
  className?: string;
}

function regionForecastForDay(
  score: TownshipMapScore | RegionForecastScore | undefined,
  selectedDate: string,
): RegionForecastScore | undefined {
  if (!score || !("lead_days" in score)) return undefined;
  return score.target_date === selectedDate ? score : undefined;
}

function panelDayForSelection(
  selectedDay: PredictionTimelineDay | undefined,
  selectedForecast: TownshipMapScore | RegionForecastScore | undefined,
  selectedDate: string,
) {
  const forecastForDay = regionForecastForDay(selectedForecast, selectedDate);
  const forecastOutlook =
    forecastForDay && forecastForDay.data_status !== "unavailable" && forecastForDay.flood_probability != null
      ? outlookFromForecast(forecastForDay)
      : undefined;
  return selectedDay ?? forecastOutlook;
}

function FloodPredictionNowPanelBody({
  areas,
  selectedTownship,
  onSelectTownship,
  districtFilter = "all",
  embedded = false,
  timelineControl,
  onPlanResources,
  onPredictionDetails,
  className,
}: FloodPredictionNowPanelProps & { timelineControl: PredictionNowTimelineControl }) {
  const {
    anchorDate,
    setAnchorDate,
    dateMin,
    dateMax,
    selectedDate,
    timeline,
    selectedDay,
    scoresByTownship,
  } = timelineControl;

  const visibleDistricts = useMemo(() => {
    const districts = areas.data?.districts ?? [];
    if (districtFilter === "all") return districts;
    return districts.filter((district) => district.id === districtFilter);
  }, [areas.data, districtFilter]);

  const selectedTownshipMeta = useMemo(() => {
    for (const district of visibleDistricts) {
      const match = district.townships.find((township) => township.id === selectedTownship);
      if (match) {
        return {
          id: match.id,
          name: match.name_en,
          latitude: match.latitude,
          longitude: match.longitude,
          districtName: district.name_en,
        };
      }
    }
    return undefined;
  }, [visibleDistricts, selectedTownship]);

  const selectedForecast = scoresByTownship.get(selectedTownship);
  const panelDay = panelDayForSelection(selectedDay, selectedForecast, selectedDate);
  const timelineLoading = timeline.state === "loading";

  const body = (
    <>
      <div className="prediction-title-row">
        {embedded ? null : <h2 className="prediction-panel-title">Flood prediction</h2>}
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
            onChange={(event) => onSelectTownship(event.target.value)}
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
      {onPredictionDetails ? (
        <button type="button" className="text-link" onClick={onPredictionDetails}>
          Prediction details
        </button>
      ) : null}
      {timelineLoading ? (
        <div className="prediction-panel-loading">
          <LoadingSpinner label="Loading flood prediction…" />
        </div>
      ) : (
        <>
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
                  panelDay.potentially_affected_population ?? panelDay.recorded_affected_people ?? undefined,
                floodProbability: panelDay.flood_probability,
              });
            }}
          />
        </>
      )}
      {timeline.state === "error" && <p className="state error">Unavailable: {timeline.error}</p>}
    </>
  );

  const floodClass = ["flood-now", className].filter(Boolean).join(" ");
  if (embedded) {
    return <div className={floodClass}>{body}</div>;
  }
  return <article className={`panel ${floodClass}`}>{body}</article>;
}

function FloodPredictionNowPanelWithHook(props: Omit<FloodPredictionNowPanelProps, "timelineControl">) {
  const districtFilter = props.districtFilter ?? "all";
  const timelineControl = usePredictionTimeline(props.areas.data, props.selectedTownship, districtFilter);
  return <FloodPredictionNowPanelBody {...props} timelineControl={timelineControl} />;
}

export default function FloodPredictionNowPanel(props: FloodPredictionNowPanelProps) {
  if (props.timelineControl) {
    return <FloodPredictionNowPanelBody {...props} timelineControl={props.timelineControl} />;
  }
  return <FloodPredictionNowPanelWithHook {...props} />;
}
