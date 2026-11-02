import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { DEFAULT_HISTORY_START, filterDaysByMode, forecastEnd, localToday, type TimeMode } from "../lib/dates";
import type {
  BagoAreasResponse,
  LoadState,
  PredictionMapScoresResponse,
  PredictionTimelineDay,
  PredictionTimelineResponse,
  RegionForecastResponse,
  RegionForecastScore,
  TownshipMapScore,
} from "../types";

interface Resource<T> {
  state: LoadState;
  data?: T;
  error?: string;
}

const loading = <T,>(): Resource<T> => ({ state: "loading" });

function errorText(reason: unknown) {
  return reason instanceof Error ? reason.message : "Unexpected request failure";
}

export function usePredictionTimeline(
  areas: BagoAreasResponse | undefined,
  selectedTownship: string,
  districtFilter: string,
) {
  const today = localToday();
  const [anchorDate, setAnchorDateState] = useState(today);
  const [dateMin, setDateMin] = useState(DEFAULT_HISTORY_START);
  const [dateMax, setDateMax] = useState(forecastEnd(today));
  const [timeMode, setTimeMode] = useState<TimeMode>("today");
  const [selectedDate, setSelectedDate] = useState(today);
  const dateTouched = useRef(false);
  const [timeline, setTimeline] = useState<Resource<PredictionTimelineResponse>>(loading);
  const [mapScores, setMapScores] = useState<Resource<PredictionMapScoresResponse>>(loading);
  const [regionForecast, setRegionForecast] = useState<Resource<RegionForecastResponse>>({ state: "empty" });
  useEffect(() => {
    let active = true;
    api
      .predictionCalendarBounds()
      .then((bounds) => {
        if (!active) return;
        setDateMin(bounds.history_start);
        setDateMax(bounds.select_max);
      })
      .catch(() => {
        if (!active) return;
        setDateMin(DEFAULT_HISTORY_START);
        setDateMax(forecastEnd(today));
      });
    return () => {
      active = false;
    };
  }, [today]);

  const selectedPlace = useMemo(() => {
    for (const district of areas?.districts ?? []) {
      const township = district.townships.find((item) => item.id === selectedTownship);
      if (township) return { district, township };
    }
    return undefined;
  }, [areas, selectedTownship]);

  useEffect(() => {
    if (!selectedPlace) return;
    let active = true;
    const { township } = selectedPlace;
    setTimeline(loading);
    api
      .predictionTimeline({
        date: anchorDate,
        as_of: anchorDate,
        township_id: township.id,
        township_name_en: township.name_en,
        latitude: township.latitude,
        longitude: township.longitude,
      })
      .then((data) => {
        if (active) setTimeline({ state: "ready", data });
      })
      .catch((reason) => {
        if (active) setTimeline({ state: "error", error: errorText(reason) });
      });
    return () => {
      active = false;
    };
  }, [selectedPlace, anchorDate]);

  useEffect(() => {
    if (!dateTouched.current) {
      setSelectedDate(anchorDate);
    }
  }, [anchorDate]);

  useEffect(() => {
    const current = timeline.data?.as_of;
    if (current && current === anchorDate && !dateTouched.current) {
      setSelectedDate(current);
    }
  }, [timeline.data, anchorDate]);

  useEffect(() => {
    let active = true;
    setMapScores(loading);
    const districtId = districtFilter === "all" ? undefined : districtFilter;
    api
      .predictionMapScores(selectedDate, districtId)
      .then((data) => {
        if (active) {
          setMapScores({
            state: data.scores.length ? "ready" : "empty",
            data,
          });
        }
      })
      .catch((reason) => {
        if (active) setMapScores({ state: "error", error: errorText(reason) });
      });
    return () => {
      active = false;
    };
  }, [selectedDate, districtFilter]);

  useEffect(() => {
    const loadRegion = api.predictionRegionForecast;
    if (!loadRegion) {
      setRegionForecast({ state: "empty" });
      return;
    }
    let active = true;
    setRegionForecast(loading());
    loadRegion(anchorDate)
      .then((data) => {
        if (!active) return;
        setRegionForecast({
          state: data.scores.length ? "ready" : "empty",
          data,
        });
      })
      .catch((reason) => {
        if (active) setRegionForecast({ state: "error", error: errorText(reason) });
      });
    return () => {
      active = false;
    };
  }, [anchorDate]);

  const modeRange = useMemo(() => filterDaysByMode(anchorDate, timeMode), [anchorDate, timeMode]);

  const modeDays = useMemo(() => {
    const days = timeline.data?.days ?? [];
    return days.filter((day) => day.date >= modeRange.start && day.date <= modeRange.end);
  }, [timeline.data, modeRange]);

  const chartDays = useMemo(() => timeline.data?.days ?? [], [timeline.data]);

  const selectedDay = useMemo(
    () => timeline.data?.days.find((day) => day.date === selectedDate),
    [timeline.data, selectedDate],
  );

  const scoresByTownship = useMemo(() => {
    const map = new Map<string, TownshipMapScore | RegionForecastScore>();
    for (const score of mapScores.data?.scores ?? []) {
      map.set(score.township_id, score);
    }
    if (map.size === 0 && regionForecast.data) {
      for (const score of regionForecast.data.scores) {
        if (score.target_date !== selectedDate) continue;
        if (districtFilter !== "all" && score.district_id !== districtFilter) continue;
        map.set(score.township_id, score);
      }
    }
    return map;
  }, [regionForecast.data, selectedDate, districtFilter, mapScores.data]);

  const chooseDate = useCallback((date: string) => {
    dateTouched.current = true;
    setSelectedDate(date);
  }, []);

  const setAnchorDate = useCallback(
    (value: string) => {
      if (value < dateMin || value > dateMax) return;
      dateTouched.current = false;
      setAnchorDateState(value);
      setSelectedDate(value);
      setTimeMode("today");
    },
    [dateMin, dateMax],
  );

  const setTimeModeAndDate = useCallback(
    (mode: TimeMode) => {
      setTimeMode(mode);
      const range = filterDaysByMode(anchorDate, mode);
      if (mode === "today") {
        setSelectedDate(anchorDate);
      } else if (mode === "past") {
        setSelectedDate(range.end);
      } else {
        setSelectedDate(range.start);
      }
      dateTouched.current = true;
    },
    [anchorDate],
  );

  const stepSelectedDate = useCallback(
    (direction: -1 | 1) => {
      const ordered = modeDays.map((day) => day.date);
      if (ordered.length === 0) return;
      const index = ordered.indexOf(selectedDate);
      const nextIndex = index === -1 ? 0 : Math.min(Math.max(index + direction, 0), ordered.length - 1);
      setSelectedDate(ordered[nextIndex]);
      dateTouched.current = true;
    },
    [modeDays, selectedDate],
  );

  return {
    today,
    anchorDate,
    setAnchorDate,
    dateMin,
    dateMax,
    timeMode,
    setTimeMode: setTimeModeAndDate,
    selectedDate,
    setSelectedDate: chooseDate,
    timeline,
    mapScores,
    regionForecast,
    modeDays,
    chartDays,
    selectedDay,
    scoresByTownship,
    stepSelectedDate,
    selectedPlace,
    modeRange,
  };
}

export type { PredictionTimelineDay, TimeMode };
