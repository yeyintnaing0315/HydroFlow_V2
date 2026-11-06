import { FormEvent, useEffect, useMemo, useState } from "react";
import { api } from "./api";
import AllocationFloodHistory from "./components/allocation/AllocationFloodHistory";
import AllocationOverviewMap from "./components/allocation/AllocationOverviewMap";
import AllocationPrintPreview from "./components/allocation/AllocationPrintPreview";
import AllocationConfirmedDeductions from "./components/allocation/AllocationConfirmedDeductions";
import AllocationTownshipSupplyTable from "./components/allocation/AllocationTownshipSupplyTable";
import { aggregatePlanDeductions } from "./lib/allocationPlanDeductions";
import { formatDistance, routeMethodLabel } from "./components/allocation/routeFormat";
import { PageControls, ViewDialog } from "./components/ViewDialog";
import { errorText } from "./lib/formatError";
import type { AllocationFocus } from "./lib/allocationFocus";
import { resolveHighSevereAffectedPeople } from "./lib/syntheticAffectedEstimate";
import { depotRegionForCoordinates, type DepotRegion } from "./lib/depotRegion";
import { depotsFromPlan, routesFromPlan, townshipsFromPlan } from "./lib/allocationPlanMap";
import { ensureAffectedSexSplit } from "./lib/splitAffectedBySex";
import { depotReferenceCoords, resolveTownshipPosition } from "./lib/resolveTownshipPosition";
import { floodFillLevel, riskLabel } from "./components/prediction/mapUtils";
import type {
  AllocationBlockedSegment,
  AllocationPlanHistoryItem,
  AllocationPlanResponse,
  AllocationStoreStatus,
  AllocationTownshipRow,
  AssistancePriority,
  BagoAreasResponse,
  CensusResponse,
  InventorySnapshot,
  LoadState,
  PredictionMapScoresResponse,
  TownshipMapScore,
  TownshipRouteComparison,
  Coordinates,
} from "./types";

type SavedPlan = AllocationPlanResponse & {
  status?: "draft" | "confirmed";
  prediction_run_id?: number | null;
  unverified_stores?: AllocationStoreStatus[];
};

type SavedRoute = AllocationPlanResponse["routes"][number] & {
  routing_method?: string;
  blocked_segments?: AllocationBlockedSegment[];
};

interface ResourceAllocationDashboardProps {
  startDate: string;
  onStartDate: (value: string) => void;
  focus?: AllocationFocus | null;
  onClearFocus?: () => void;
  onOpenInventory?: () => void;
  areas?: {
    state: LoadState;
    data?: BagoAreasResponse;
    error?: string;
  };
}

interface Resource<T> {
  state: LoadState;
  data?: T;
  error?: string;
}

const loading = <T,>(): Resource<T> => ({ state: "loading" });

/** Plans include high and severe townships only (backend min_priority threshold). */
const ALLOCATION_MIN_PRIORITY: AssistancePriority = "high";

type RegionCode = DepotRegion;

const DEPOT_TOWNSHIP_NAMES = new Set(["bago", "pyay"]);

function isDepotTownship(name: string): boolean {
  return DEPOT_TOWNSHIP_NAMES.has(name.trim().toLowerCase());
}

const DEFAULT_DEPOTS: OverviewDepot[] = [
  {
    id: "depot-bago",
    name: "Bago depot (east)",
    ...depotReferenceCoords("east"),
    region: "east",
  },
  {
    id: "depot-pyay",
    name: "Pyay depot (west)",
    ...depotReferenceCoords("west"),
    region: "west",
  },
];

interface OverviewDepot {
  id: string;
  name: string;
  latitude: number;
  longitude: number;
  region: "east" | "west";
}

function buildExpectedAffectedOverrides(
  startDate: string,
  focus: AllocationFocus | null | undefined,
  affectedByTownship: Record<string, number | null>,
  focusEstimate: { affected: number | null } | null,
): Record<string, number> | undefined {
  const overrides: Record<string, number> = {};
  if (focus) {
    const estimate = resolveHighSevereAffectedPeople(
      focus.townshipId,
      startDate,
      focusEstimate?.affected ??
        focus.expectedAffected ??
        affectedByTownship[focus.townshipId] ??
        null,
      focus.riskLevel,
    );
    if (estimate != null && estimate > 0) {
      overrides[focus.townshipId] = estimate;
    }
  } else {
    for (const [townshipId, count] of Object.entries(affectedByTownship)) {
      if (count != null && count > 0) {
        overrides[townshipId] = count;
      }
    }
  }
  return Object.keys(overrides).length ? overrides : undefined;
}

function planRequestBody(
  startDate: string,
  focus: AllocationFocus | null | undefined,
  affectedByTownship: Record<string, number | null>,
  focusEstimate: { affected: number | null } | null,
) {
  return {
    date: startDate,
    warehouse_region: "auto" as const,
    min_priority: ALLOCATION_MIN_PRIORITY,
    // Focused view: one date + one township. Region view: all high/severe townships that day.
    include_all_high_severe: !focus,
    township_ids: focus ? [focus.townshipId] : undefined,
    commit_inventory: false,
    vehicle_profile: "truck" as const,
    expected_affected_overrides: buildExpectedAffectedOverrides(
      startDate,
      focus,
      affectedByTownship,
      focusEstimate,
    ),
  };
}

function depotDisplayLabel(region: "east" | "west"): string {
  return region === "east" ? "Bago East" : "Pyay West";
}

export default function ResourceAllocationDashboard({
  startDate,
  onStartDate,
  focus,
  onClearFocus,
  areas,
}: ResourceAllocationDashboardProps) {
  const [inventoryEast, setInventoryEast] = useState<Resource<InventorySnapshot>>({ state: "empty" });
  const [inventoryWest, setInventoryWest] = useState<Resource<InventorySnapshot>>({ state: "empty" });
  const [plan, setPlan] = useState<Resource<SavedPlan>>({ state: "empty" });
  const [stores, setStores] = useState<AllocationStoreStatus[]>([]);
  const [history, setHistory] = useState<AllocationPlanHistoryItem[]>([]);
  const [confirming, setConfirming] = useState(false);
  const [confirmError, setConfirmError] = useState<string | undefined>();
  const [selectedTownshipId, setSelectedTownshipId] = useState<string | null>(null);
  const [comparison, setComparison] = useState<TownshipRouteComparison | null>(null);
  const [compareState, setCompareState] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [compareError, setCompareError] = useState<string | undefined>();
  const [selectingRoute, setSelectingRoute] = useState(false);
  const [routesOpen, setRoutesOpen] = useState(false);
  const [printOpen, setPrintOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyPage, setHistoryPage] = useState(0);
  const [areaResource, setAreaResource] = useState<Resource<BagoAreasResponse>>(areas ?? { state: "empty" });
  const [mapScores, setMapScores] = useState<Resource<PredictionMapScoresResponse>>({ state: "empty" });
  const [affectedByTownship, setAffectedByTownship] = useState<Record<string, number | null>>({});
  const [affectedLoading, setAffectedLoading] = useState(false);
  const [networkRoutesByTownship, setNetworkRoutesByTownship] = useState<
    Record<string, { path: Coordinates[]; distanceM: number | null }>
  >({});
  const [networkRoutesLoading, setNetworkRoutesLoading] = useState(false);
  const [censusResource, setCensusResource] = useState<Resource<CensusResponse>>({ state: "loading" });
  const [focusEstimateRequested, setFocusEstimateRequested] = useState(false);
  const [focusEstimateLoading, setFocusEstimateLoading] = useState(false);
  const [focusEstimateResult, setFocusEstimateResult] = useState<{
    affected: number | null;
    male: number | null;
    female: number | null;
  } | null>(null);

  const refreshInventory = async () => {
    setInventoryEast(loading);
    setInventoryWest(loading);
    try {
      const [east, west] = await Promise.all([api.inventory("east"), api.inventory("west")]);
      setInventoryEast({ state: "ready", data: east });
      setInventoryWest({ state: "ready", data: west });
    } catch (reason) {
      const message = errorText(reason);
      setInventoryEast({ state: "error", error: message });
      setInventoryWest({ state: "error", error: message });
    }
  };

  const refreshStores = async () => {
    try {
      setStores(await api.allocationStores());
    } catch {
      setStores([]);
    }
  };

  const refreshHistory = async () => {
    try {
      setHistory(await api.allocationPlans());
    } catch {
      setHistory([]);
    }
  };

  useEffect(() => {
    if (areas) {
      setAreaResource(areas);
      return;
    }
    let active = true;
    setAreaResource(loading);
    api
      .bagoAreas()
      .then((data) => {
        if (active) setAreaResource({ state: "ready", data });
      })
      .catch((reason) => {
        if (active) setAreaResource({ state: "error", error: errorText(reason) });
      });
    return () => {
      active = false;
    };
  }, [areas]);

  useEffect(() => {
    let active = true;
    setCensusResource(loading);
    api
      .census()
      .then((data) => {
        if (active) setCensusResource({ state: "ready", data });
      })
      .catch(() => {
        if (active) setCensusResource({ state: "empty" });
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    setMapScores(loading);
    api
      .predictionMapScores(startDate)
      .then((data) => {
        if (active) setMapScores({ state: "ready", data });
      })
      .catch((reason) => {
        if (active) setMapScores({ state: "error", error: errorText(reason) });
      });
    return () => {
      active = false;
    };
  }, [startDate]);

  useEffect(() => {
    void refreshInventory();
    void refreshStores();
  }, []);

  const predictionHighSevere = useMemo(() => {
    return (mapScores.data?.scores ?? []).filter((score: TownshipMapScore) => {
      const level = floodFillLevel(score);
      return level === "high" || level === "severe";
    });
  }, [mapScores.data]);

  useEffect(() => {
    setFocusEstimateRequested(false);
    setFocusEstimateLoading(false);
    setFocusEstimateResult(null);
  }, [focus?.townshipId, focus?.date]);

  useEffect(() => {
    if (plan.state === "ready") return;
    if (focus) {
      setAffectedByTownship({});
      setAffectedLoading(false);
      return;
    }
    const targets = predictionHighSevere.filter((score) => score.latitude != null && score.longitude != null);
    if (!targets.length) {
      setAffectedByTownship({});
      setAffectedLoading(false);
      return;
    }
    let active = true;
    setAffectedLoading(true);
    Promise.all(
      targets.map(async (score) => {
        try {
          const day = await api.helpSummary({
            date: startDate,
            township_id: score.township_id,
            township_name_en: score.township_name,
            latitude: score.latitude as number,
            longitude: score.longitude as number,
          });
          const resolved = resolveHighSevereAffectedPeople(
            score.township_id,
            startDate,
            day?.expected_affected_people ?? null,
            floodFillLevel(score),
          );
          return [score.township_id, resolved] as const;
        } catch {
          return [score.township_id, null] as const;
        }
      }),
    ).then((rows) => {
      if (!active) return;
      setAffectedByTownship(Object.fromEntries(rows));
      setAffectedLoading(false);
    });
    return () => {
      active = false;
    };
  }, [predictionHighSevere, startDate, plan.state, focus]);

  const runFocusEstimate = async () => {
    if (!focus) return;
    setFocusEstimateRequested(true);
    setFocusEstimateLoading(true);
    setFocusEstimateResult(null);
    try {
      let helpDay: Awaited<ReturnType<typeof api.helpSummary>> | undefined;
      let affected: number | null =
        focus.expectedAffected != null && focus.expectedAffected > 0 ? focus.expectedAffected : null;
      if (affected == null) {
        helpDay = await api.helpSummary({
          date: startDate,
          township_id: focus.townshipId,
          township_name_en: focus.townshipName,
          latitude: focus.latitude,
          longitude: focus.longitude,
        });
        affected = helpDay?.expected_affected_people ?? null;
      }
      affected = resolveHighSevereAffectedPeople(
        focus.townshipId,
        startDate,
        affected,
        focus.riskLevel,
      );
      const sex = ensureAffectedSexSplit(
        focus.townshipName,
        affected,
        helpDay?.affected_male ?? null,
        helpDay?.affected_female ?? null,
        censusResource.data,
      );
      const result = {
        affected,
        male: sex.male,
        female: sex.female,
      };
      setFocusEstimateResult(result);
      setAffectedByTownship({ [focus.townshipId]: affected });
    } catch {
      const fallback = resolveHighSevereAffectedPeople(
        focus.townshipId,
        startDate,
        null,
        focus.riskLevel,
      );
      const sex = ensureAffectedSexSplit(
        focus.townshipName,
        fallback,
        null,
        null,
        censusResource.data,
      );
      setFocusEstimateResult({
        affected: fallback,
        male: sex.male,
        female: sex.female,
      });
      if (fallback != null) {
        setAffectedByTownship({ [focus.townshipId]: fallback });
      }
    } finally {
      setFocusEstimateLoading(false);
    }
  };

  const runPlan = async () => {
    setPlan(loading);
    setConfirmError(undefined);
    setRoutesOpen(false);
    setComparison(null);
    setCompareState("idle");
    try {
      const result = (await api.allocationPlan(
        planRequestBody(startDate, focus, affectedByTownship, focusEstimateResult),
      )) as SavedPlan;
      setPlan({ state: "ready", data: result });
    } catch (reason) {
      setPlan({ state: "error", error: errorText(reason) });
    }
  };

  const submitPlan = async (event?: FormEvent) => {
    event?.preventDefault();
    await runPlan();
  };

  const confirmPlan = async () => {
    if (!plan.data || plan.data.status === "confirmed") return;
    setPrintOpen(false);
    setConfirming(true);
    setConfirmError(undefined);
    try {
      const result = await api.confirmAllocationPlan(plan.data.plan_id);
      setPlan({
        state: "ready",
        data: { ...plan.data, status: result.status, prediction_run_id: result.prediction_run_id },
      });
      await refreshInventory();
      await refreshHistory();
    } catch (reason) {
      setConfirmError(errorText(reason));
    } finally {
      setConfirming(false);
    }
  };

  const openHistoryPlan = async (planId: string) => {
    setPlan(loading);
    setConfirmError(undefined);
    setPrintOpen(false);
    setRoutesOpen(false);
    setComparison(null);
    setCompareState("idle");
    try {
      const result = (await api.allocationPlanDetail(planId)) as SavedPlan;
      setPlan({ state: "ready", data: result });
    } catch (reason) {
      setPlan({ state: "error", error: errorText(reason) });
    }
  };

  const listedRows = plan.data?.rows ?? [];
  const selectedRowId =
    selectedTownshipId && listedRows.some((row) => row.township_id === selectedTownshipId)
      ? selectedTownshipId
      : focus && listedRows.some((row) => row.township_id === focus.townshipId)
        ? focus.townshipId
        : (listedRows[0]?.township_id ?? null);

  const selectTownship = (townshipId: string) => {
    setSelectedTownshipId(townshipId);
    setRoutesOpen(false);
    setComparison(null);
    setCompareState("idle");
    setCompareError(undefined);
  };

  const chooseRoute = async (optionIndex: number) => {
    if (!plan.data || !selectedRowId) return;
    setSelectingRoute(true);
    setCompareError(undefined);
    try {
      const result = await api.selectTownshipRoute(plan.data.plan_id, selectedRowId, optionIndex);
      setComparison(result);
      setCompareState("ready");
      setPlan((current) => {
        if (!current.data) return current;
        return {
          ...current,
          data: {
            ...current.data,
            rows: current.data.rows.map((item) =>
              item.township_id === result.township_id ? { ...item, route_options: result.alternatives } : item,
            ),
          },
        };
      });
    } catch (reason) {
      setCompareError(errorText(reason));
    } finally {
      setSelectingRoute(false);
    }
  };

  useEffect(() => {
    if (!routesOpen || !plan.data || !selectedRowId) return;
    const row = plan.data.rows.find((item) => item.township_id === selectedRowId);
    if (row && Array.isArray(row.route_options)) {
      setComparison({
        plan_id: plan.data.plan_id,
        township_id: selectedRowId,
        depot_region: row.depot_region,
        alternatives: row.route_options,
        alternatives_available: row.route_options.length >= 2,
        rainfall_mm: row.rainfall_mm ?? null,
        discharge_m3_s: row.discharge_m3_s ?? null,
        flood_probability: row.flood_probability ?? null,
        risk_band: row.risk_band ?? null,
      });
      setCompareState("ready");
      setCompareError(undefined);
      return;
    }
    let active = true;
    setCompareState("loading");
    setCompareError(undefined);
    api
      .compareTownshipRoutes(plan.data.plan_id, selectedRowId)
      .then((result) => {
        if (!active) return;
        setComparison(result);
        setCompareState("ready");
        setPlan((current) => {
          if (!current.data) return current;
          const rows = current.data.rows.map((item) =>
            item.township_id === result.township_id ? { ...item, route_options: result.alternatives } : item,
          );
          if (rows.every((row, index) => row === current.data?.rows[index])) return current;
          return { ...current, data: { ...current.data, rows } };
        });
      })
      .catch((reason) => {
        if (!active) return;
        setComparison(null);
        setCompareState("error");
        setCompareError(errorText(reason));
      });
    return () => {
      active = false;
    };
  }, [routesOpen, plan.data, selectedRowId]);

  const selectedRow = listedRows.find((row) => row.township_id === selectedRowId);
  const planReady = plan.state === "ready" && plan.data != null;

  const overviewTownships = useMemo(() => {
    return (areaResource.data?.districts ?? []).flatMap((district) =>
      district.townships
        .filter((township) => Number.isFinite(township.latitude) && Number.isFinite(township.longitude))
        .map((township) => {
          const position = resolveTownshipPosition(
            township.name_en,
            township.latitude,
            township.longitude,
            township.geometry,
          );
          return {
            id: township.id,
            name: township.name_en,
            latitude: position.latitude,
            longitude: position.longitude,
            districtId: district.id,
          };
        }),
    );
  }, [areaResource.data]);

  const showFocusEstimateFlow = Boolean(focus && !planReady);

  const overviewMapTownships = useMemo(() => {
    if (planReady && plan.data) return townshipsFromPlan(plan.data);
    const base = overviewTownships.filter((township) => !isDepotTownship(township.name));
    if (focus && !planReady) {
      return base.filter((township) => township.id === focus.townshipId);
    }
    const routedIds = Object.keys(networkRoutesByTownship);
    if (routedIds.length === 0) {
      return networkRoutesLoading ? [] : base;
    }
    const focusId = selectedTownshipId ?? focus?.townshipId ?? null;
    const visible = new Set(routedIds);
    if (focusId) visible.add(focusId);
    return base.filter((township) => visible.has(township.id));
  }, [
    planReady,
    plan.data,
    overviewTownships,
    networkRoutesByTownship,
    networkRoutesLoading,
    selectedTownshipId,
    focus,
    focus?.townshipId,
  ]);

  const mapLoadingMessage =
    compareState === "loading" ? "Loading route…" : networkRoutesLoading ? "Loading routes…" : null;

  const scoreMap = useMemo(() => {
    const map = new Map<string, TownshipMapScore>();
    for (const score of mapScores.data?.scores ?? []) map.set(score.township_id, score);
    return map;
  }, [mapScores.data]);

  const overviewDepots = useMemo((): OverviewDepot[] => {
    if (planReady && plan.data) {
      return depotsFromPlan(plan.data);
    }
    const eastStore = stores.find((store) => store.region === "east");
    const westStore = stores.find((store) => store.region === "west");
    const eastRef = depotReferenceCoords("east");
    const westRef = depotReferenceCoords("west");
    return [
      {
        id: "depot-bago",
        name: eastStore?.name ?? "Bago depot (east)",
        latitude: eastStore?.latitude ?? eastRef.latitude,
        longitude: eastStore?.longitude ?? eastRef.longitude,
        region: "east",
      },
      {
        id: "depot-pyay",
        name: westStore?.name ?? "Pyay depot (west)",
        latitude: westStore?.latitude ?? westRef.latitude,
        longitude: westStore?.longitude ?? westRef.longitude,
        region: "west",
      },
    ];
  }, [planReady, plan.data, stores]);

  const highlightedTownshipId = planReady ? selectedRowId : (selectedTownshipId ?? focus?.townshipId ?? null);

  useEffect(() => {
    if (planReady) {
      setNetworkRoutesByTownship({});
      setNetworkRoutesLoading(false);
      return;
    }
    const east = overviewDepots.find((depot) => depot.region === "east");
    const west = overviewDepots.find((depot) => depot.region === "west");
    if (!east || !west) return;
    const allTargets = overviewTownships.filter((township) => !isDepotTownship(township.name));
    const targets =
      focus && !planReady
        ? allTargets.filter((township) => township.id === focus.townshipId)
        : allTargets;
    if (!targets.length) {
      setNetworkRoutesByTownship({});
      return;
    }
    let active = true;
    setNetworkRoutesLoading(true);
    const legs = targets.slice(0, 32).map((township) => {
      const region = depotRegionForCoordinates(township.latitude, township.longitude);
      const depot = region === "east" ? east : west;
      return {
        township_id: township.id,
        depot_region: region,
        depot_latitude: depot.latitude,
        depot_longitude: depot.longitude,
        township_latitude: township.latitude,
        township_longitude: township.longitude,
      };
    });
    api
      .allocationNetworkRoutes(legs)
      .then((response) => {
        if (!active) return;
        const next: Record<string, { path: Coordinates[]; distanceM: number | null }> = {};
        for (const route of response.routes) {
          if (route.routing_method !== "osrm_road" || route.path.length < 2) continue;
          next[route.township_id] = { path: route.path, distanceM: route.distance_m };
        }
        setNetworkRoutesByTownship(next);
      })
      .catch(() => {
        if (!active) return;
        setNetworkRoutesByTownship({});
      })
      .finally(() => {
        if (active) setNetworkRoutesLoading(false);
      });
    return () => {
      active = false;
    };
  }, [planReady, overviewDepots, overviewTownships, stores, focus]);

  const overviewRoutes = useMemo(() => {
    const east = overviewDepots.find((depot) => depot.region === "east");
    const west = overviewDepots.find((depot) => depot.region === "west");
    if (!east || !west) return [];
    const depotFor = (region: "east" | "west") => (region === "east" ? east : west);
    const activeAlternative = routesOpen
      ? (comparison?.alternatives.find((option) => option.selected) ??
        comparison?.alternatives.find((option) => option.recommended))
      : undefined;

    if (!planReady) {
      return overviewTownships
        .filter((township) => !isDepotTownship(township.name))
        .flatMap((township) => {
          const region = depotRegionForCoordinates(township.latitude, township.longitude);
          const network = networkRoutesByTownship[township.id];
          if (!network || network.path.length < 2) return [];
          return [
            {
              id: township.id,
              label: township.name,
              depotRegion: region,
              distanceM: network.distanceM,
              emphasized: township.id === highlightedTownshipId,
              path: network.path,
            },
          ];
        });
    }

    if (!plan.data) return [];
    const planDepots = depotsFromPlan(plan.data);
    const baseRoutes = routesFromPlan(plan.data, planDepots, highlightedTownshipId);
    return baseRoutes.map((route) => {
      if (route.id !== selectedRowId || !activeAlternative || activeAlternative.path.length < 2) {
        return route;
      }
      return {
        ...route,
        path: activeAlternative.path,
        distanceM: activeAlternative.distance_m ?? route.distanceM,
        emphasized: true,
      };
    });
  }, [
    overviewDepots,
    overviewTownships,
    planReady,
    plan.data,
    listedRows,
    highlightedTownshipId,
    routesOpen,
    comparison,
    selectedRowId,
    networkRoutesByTownship,
  ]);

  const mapDisplayRoutes = useMemo(() => {
    if (!highlightedTownshipId) return overviewRoutes;
    const active = overviewRoutes.filter((route) => route.id === highlightedTownshipId);
    return active.length ? active : overviewRoutes;
  }, [overviewRoutes, highlightedTownshipId]);

  const inventoryError =
    inventoryEast.state === "error"
      ? inventoryEast.error
      : inventoryWest.state === "error"
        ? inventoryWest.error
        : undefined;

  const priorityScopeLabel = focus ? `${riskLabel(focus.riskLevel)} risk` : "High and severe only";

  const routeCaption = useMemo(() => {
    if (!selectedRow) return "";
    const active =
      comparison?.alternatives.find((option) => option.selected) ??
      comparison?.alternatives.find((option) => option.recommended);
    if (routesOpen && active) {
      return `${selectedRow.township_name} · ${active.label} · ${routeMethodLabel(active.routing_method)} · ${formatDistance(active.distance_m)}`;
    }
    const route = (plan.data?.routes ?? []).find((item) => item.route_id === selectedRow.route_id);
    const method = (route as SavedRoute | undefined)?.routing_method;
    const km = formatDistance(route?.distance_m);
    return `${selectedRow.township_name} · ${selectedRow.route_id}${method ? ` · ${routeMethodLabel(method)}` : ""}${km === "—" ? "" : ` · ${km}`}`;
  }, [selectedRow, comparison, routesOpen, plan.data]);

  const routeDistanceByTownship = useMemo(() => {
    const out: Record<string, number | null | undefined> = {};
    for (const route of overviewRoutes) {
      out[route.id] = route.distanceM;
    }
    return out;
  }, [overviewRoutes]);

  const censusData = censusResource.data;

  const affectedRows = planReady
    ? listedRows.map((row) => ({
        id: row.township_id,
        name: row.township_name,
        affected: row.population as number | null,
        male: row.affected_male ?? 0,
        female: row.affected_female ?? 0,
        pending: false,
      }))
    : showFocusEstimateFlow
      ? focusEstimateRequested
        ? (() => {
            const affected = resolveHighSevereAffectedPeople(
              focus!.townshipId,
              startDate,
              focusEstimateResult?.affected ?? null,
              focus!.riskLevel,
            );
            const sex = ensureAffectedSexSplit(
              focus!.townshipName,
              affected,
              focusEstimateResult?.male,
              focusEstimateResult?.female,
              censusData,
            );
            return [
              {
                id: focus!.townshipId,
                name: focus!.townshipName,
                affected,
                male: sex.male,
                female: sex.female,
                pending: focusEstimateLoading,
              },
            ];
          })()
        : (() => {
            const affected = resolveHighSevereAffectedPeople(
              focus!.townshipId,
              startDate,
              focus!.expectedAffected ?? null,
              focus!.riskLevel,
            );
            const sex = ensureAffectedSexSplit(
              focus!.townshipName,
              affected,
              null,
              null,
              censusData,
            );
            return [
              {
                id: focus!.townshipId,
                name: focus!.townshipName,
                affected,
                male: sex.male,
                female: sex.female,
                pending: false,
              },
            ];
          })()
      : predictionHighSevere.map((score) => {
          const raw =
            score.township_id in affectedByTownship ? affectedByTownship[score.township_id] : null;
          const affected = resolveHighSevereAffectedPeople(
            score.township_id,
            startDate,
            raw,
            floodFillLevel(score),
          );
          const sex = ensureAffectedSexSplit(
            score.township_name,
            affected,
            null,
            null,
            censusData,
          );
          return {
            id: score.township_id,
            name: score.township_name,
            affected,
            male: sex.male,
            female: sex.female,
            pending: affectedLoading && !(score.township_id in affectedByTownship),
          };
        });

  const totalAffectedEst = useMemo(() => {
    let total = 0;
    let counted = false;
    for (const row of affectedRows) {
      if (row.pending || row.affected == null) continue;
      total += row.affected;
      counted = true;
    }
    return counted ? total : null;
  }, [affectedRows]);

  const totalAffectedBySex = useMemo(() => {
    let male = 0;
    let female = 0;
    let hasMale = false;
    let hasFemale = false;
    for (const row of affectedRows) {
      if (row.pending) continue;
      if (row.male != null) {
        male += row.male;
        hasMale = true;
      }
      if (row.female != null) {
        female += row.female;
        hasFemale = true;
      }
    }
    return {
      male: hasMale ? male : null,
      female: hasFemale ? female : null,
    };
  }, [affectedRows]);

  const formatToolbarCount = (value: number | null, pending: boolean) => {
    if (pending) return "…";
    if (value == null) return "—";
    return value.toLocaleString();
  };

  const sexCountsPending =
    !planReady && showFocusEstimateFlow
      ? focusEstimateRequested && focusEstimateLoading
      : affectedLoading && !planReady;

  const planConfirmed = plan.data?.status === "confirmed";

  const confirmedDeductions = useMemo(() => {
    if (!planConfirmed || !plan.data) return [];
    return aggregatePlanDeductions(plan.data.rows);
  }, [planConfirmed, plan.data]);

  const roadRouteCount = Object.keys(networkRoutesByTownship).length;

  const previewTableRows = useMemo((): AllocationTownshipRow[] => {
    return affectedRows.map((row) => {
      const countsUnknown =
        !row.pending && row.affected == null && row.male == null && row.female == null;
      const people =
        row.affected ??
        (row.male != null && row.female != null && !row.pending ? row.male + row.female : 0);
      return {
        township_id: row.id,
        township_name: row.name,
        latitude: 0,
        longitude: 0,
        population: row.pending || countsUnknown ? -1 : people,
        affected_male: row.pending || row.male == null ? -1 : row.male,
        affected_female: row.pending || row.female == null ? -1 : row.female,
        priority: "high",
        resources_label: "",
        quantities_label: "",
        route_id: "",
        depot_region: "east",
        has_shortage: false,
        line_items: [],
      };
    });
  }, [affectedRows]);

  const selectTownshipFromTable = (townshipId: string) => {
    if (planReady && !listedRows.some((item) => item.township_id === townshipId)) return;
    selectTownship(townshipId);
  };

  const alerts: { tone: "error" | "status"; message: string }[] = [];
  if (plan.state === "error" && plan.error) alerts.push({ tone: "error", message: `Plan failed: ${plan.error}` });
  if (confirmError) alerts.push({ tone: "error", message: `Confirm failed: ${confirmError}` });
  if (plan.data?.shortages.length) {
    alerts.push({
      tone: "status",
      message:
        "This saved plan has resource gaps. Create a new plan after restocking verified depots.",
    });
  }
  if (plan.data?.unverified_stores?.length) {
    alerts.push({
      tone: "status",
      message: `Unverified depots were not used: ${plan.data.unverified_stores.map((store) => store.name).join(", ")}. Verify stock, then create the plan again before confirm.`,
    });
  }
  const historyPages = Math.max(1, Math.ceil(history.length / 6));
  const historySlice = history.slice(historyPage * 6, historyPage * 6 + 6);

  const detailTownshipId = highlightedTownshipId;
  const detailTownshipMeta = useMemo(() => {
    if (!detailTownshipId) return null;
    if (planReady && selectedRow && selectedRow.township_id === detailTownshipId) {
      return {
        id: selectedRow.township_id,
        name: selectedRow.township_name,
        latitude: selectedRow.latitude,
        longitude: selectedRow.longitude,
        priority: selectedRow.priority,
        depotRegion: selectedRow.depot_region,
      };
    }
    if (focus && focus.townshipId === detailTownshipId) {
      return {
        id: focus.townshipId,
        name: focus.townshipName,
        latitude: focus.latitude,
        longitude: focus.longitude,
        priority: focus.riskLevel,
        depotRegion: depotRegionForCoordinates(focus.latitude, focus.longitude),
      };
    }
    const fromScore = predictionHighSevere.find((score) => score.township_id === detailTownshipId);
    const fromArea = overviewTownships.find((township) => township.id === detailTownshipId);
    if (!fromArea) return null;
    const level = fromScore ? floodFillLevel(fromScore) : "high";
    return {
      id: fromArea.id,
      name: fromArea.name,
      latitude: fromArea.latitude,
      longitude: fromArea.longitude,
      priority: level === "severe" ? "severe" : "high",
      depotRegion: depotRegionForCoordinates(fromArea.latitude, fromArea.longitude),
    };
  }, [
    detailTownshipId,
    planReady,
    selectedRow,
    focus,
    predictionHighSevere,
    overviewTownships,
  ]);

  const summaryAffectedDisplay = planReady
    ? plan.data?.totals.affected_population.toLocaleString() ?? "—"
    : formatToolbarCount(totalAffectedEst, sexCountsPending);

  const summaryResourcesDisplay = planReady
    ? `${(plan.data?.totals.resources_needed_units ?? 0).toLocaleString()} units`
    : totalAffectedEst != null
      ? `${(totalAffectedEst * 19).toLocaleString()} units est.`
      : "—";

  const summaryDepotDisplay = detailTownshipMeta
    ? depotDisplayLabel(detailTownshipMeta.depotRegion)
    : "—";

  const detailRiskLabel = detailTownshipMeta
    ? riskLabel(
        (detailTownshipMeta.priority === "severe"
          ? "severe"
          : detailTownshipMeta.priority === "high"
            ? "high"
            : focus?.riskLevel ?? "high") as Parameters<typeof riskLabel>[0],
      )
    : null;

  const detailRouteLabel = useMemo(() => {
    if (!detailTownshipMeta) return null;
    const depot = depotDisplayLabel(detailTownshipMeta.depotRegion);
    const distance = formatDistance(routeDistanceByTownship[detailTownshipMeta.id] ?? undefined);
    const suffix = distance === "—" ? "" : ` · ${distance}`;
    return `${depot} → ${detailTownshipMeta.name}${suffix}`;
  }, [detailTownshipMeta, routeDistanceByTownship]);

  const allocationTownshipLabel = useMemo(() => {
    if (planReady && selectedRow) return selectedRow.township_name;
    if (focus && !planReady) return focus.townshipName;
    if (selectedTownshipId) {
      const score = predictionHighSevere.find((item) => item.township_id === selectedTownshipId);
      const area = overviewTownships.find((item) => item.id === selectedTownshipId);
      return score?.township_name ?? area?.name ?? "Selected township";
    }
    return "All high and severe";
  }, [
    planReady,
    selectedRow,
    focus,
    selectedTownshipId,
    predictionHighSevere,
    overviewTownships,
  ]);

  const allocationPlanningDate = plan.data?.planning_date ?? startDate;

  return (
    <main className="allocation-board allocation-board-single">
      {alerts.length ? (
        <div className="allocation-alerts">
          {alerts.map((alert) => (
            <p key={alert.message} className={alert.tone === "error" ? "state error" : "allocation-alert"} role="status">
              {alert.message}
            </p>
          ))}
        </div>
      ) : null}

      <section className="panel allocation-map-column">
        <div className="allocation-map-stack">
          <div className="allocation-route-map-head">
            <h2>Route map</h2>
            <div className="allocation-route-map-meta" aria-label="Route map context">
              <span className="allocation-route-map-meta-item">
                <span className="allocation-top-label">Planning date</span>
                <strong>{allocationPlanningDate}</strong>
              </span>
              <span className="allocation-route-map-meta-item">
                <span className="allocation-top-label">Township</span>
                <strong>{allocationTownshipLabel}</strong>
              </span>
            </div>
            <span className="source allocation-route-map-source">
              {mapLoadingMessage ?? (planReady ? `${listedRows.length} high or severe` : null)}
            </span>
          </div>
          {!printOpen ? (
            <AllocationOverviewMap
              instanceKey="allocation-dashboard-map"
              townships={overviewMapTownships}
              depots={overviewDepots}
              routes={mapDisplayRoutes}
              focusTownshipId={highlightedTownshipId}
              loadingMessage={mapLoadingMessage}
              onSelectTownship={(townshipId) => {
                if (planReady && !listedRows.some((row) => row.township_id === townshipId)) return;
                selectTownship(townshipId);
              }}
            />
          ) : (
            <div className="allocation-map-frame allocation-map-sleep" aria-hidden />
          )}
          <ul className="legend allocation-map-legend" aria-label="Map legend">
            <li><i style={{ background: "#0b5873" }} />East depot routes</li>
            <li><i style={{ background: "#c45a1a" }} />West depot routes</li>
            <li><i style={{ background: "#f4b942" }} />Bago depot</li>
            <li><i style={{ background: "#e07a2f" }} />Pyay depot</li>
          </ul>
          {planReady && routeCaption ? (
            <p className="hint allocation-map-hint">{routeCaption}</p>
          ) : null}
        </div>
        <details className="allocation-flood-history-details">
          <summary>Flood history</summary>
          <AllocationFloodHistory />
        </details>
      </section>

      <section className="allocation-split-side">
        <article
          className="panel allocation-side-stack allocation-plan-table-card"
          role="region"
          aria-label="Allocation plan table"
        >
          {focus && onClearFocus ? (
            <div className="allocation-scope-strip">
              <span className="allocation-scope-label">Scope: {priorityScopeLabel}</span>
              <button type="button" className="text-link" onClick={onClearFocus}>
                Clear focus
              </button>
            </div>
          ) : !focus ? (
            <div className="allocation-scope-strip">
              <span className="allocation-scope-label">Scope: {priorityScopeLabel}</span>
            </div>
          ) : null}

          <div className="allocation-summary-cards" aria-label="Allocation summary">
            <div className="allocation-summary-card">
              <span className="allocation-summary-card-label">Affected people</span>
              <strong className="allocation-summary-card-value">{summaryAffectedDisplay}</strong>
              {!planReady ? (
                <span className="allocation-summary-card-meta">
                  M {formatToolbarCount(totalAffectedBySex.male, sexCountsPending)} · F{" "}
                  {formatToolbarCount(totalAffectedBySex.female, sexCountsPending)}
                </span>
              ) : null}
            </div>
            <div className="allocation-summary-card">
              <span className="allocation-summary-card-label">Required resources</span>
              <strong className="allocation-summary-card-value">{summaryResourcesDisplay}</strong>
            </div>
            <div className="allocation-summary-card">
              <span className="allocation-summary-card-label">Assigned depot</span>
              <strong className="allocation-summary-card-value">{summaryDepotDisplay}</strong>
            </div>
          </div>

          <div className="allocation-detail-list" aria-label="Allocation details">
            <h3 className="allocation-detail-title">Allocation details</h3>
            {detailTownshipMeta ? (
              <dl className="allocation-detail-rows">
                <div>
                  <dt>Township</dt>
                  <dd>{detailTownshipMeta.name}</dd>
                </div>
                <div>
                  <dt>Risk level</dt>
                  <dd>
                    <span className={`risk-pill risk-${detailTownshipMeta.priority}`}>{detailRiskLabel}</span>
                  </dd>
                </div>
                <div>
                  <dt>Delivery priority</dt>
                  <dd>
                    <span className="allocation-priority-pill">{detailRiskLabel ?? "—"}</span>
                  </dd>
                </div>
                <div>
                  <dt>Estimated route</dt>
                  <dd>{detailRouteLabel ?? "—"}</dd>
                </div>
              </dl>
            ) : (
              <p className="hint allocation-detail-empty">Select a township to see allocation details.</p>
            )}
          </div>

          <div
            className={`allocation-table-section${planConfirmed ? " allocation-table-section--confirmed" : ""}`}
          >
            <div className="section-heading allocation-table-head">
              <h2>
                {planReady
                  ? "Plan"
                  : showFocusEstimateFlow
                    ? "Affected people"
                    : "High and severe townships"}
              </h2>
              <span className="source">
                {planReady && plan.data
                  ? `${plan.data.totals.affected_population.toLocaleString()} people`
                  : showFocusEstimateFlow
                    ? focusEstimateRequested
                      ? focus!.townshipName
                      : "Estimate to load counts"
                    : affectedRows.length
                      ? `${affectedRows.length} townships`
                      : "No high or severe"}
              </span>
            </div>
            <AllocationTownshipSupplyTable
              rows={planReady ? listedRows : previewTableRows}
              previewOnly={!planReady}
              dashboardPlanView={planReady}
              planningDate={allocationPlanningDate}
              routeDistanceByTownship={routeDistanceByTownship}
              selectedTownshipId={highlightedTownshipId}
              onSelectTownship={selectTownshipFromTable}
            />
            {planConfirmed ? <AllocationConfirmedDeductions lines={confirmedDeductions} /> : null}
          </div>

          <form
            className={`allocation-plan-form allocation-plan-form-stack${
              showFocusEstimateFlow && !focusEstimateRequested ? " allocation-plan-form-stack--estimate" : ""
            }`}
            onSubmit={submitPlan}
          >
            {showFocusEstimateFlow && !focusEstimateRequested ? (
              <button
                type="button"
                className="allocation-action primary allocation-primary-cta allocation-estimate-cta"
                disabled={focusEstimateLoading}
                onClick={() => void runFocusEstimate()}
              >
                {focusEstimateLoading ? "Estimating…" : "Estimate"}
              </button>
            ) : null}
            <button
              type="submit"
              className="allocation-action primary allocation-primary-cta"
              disabled={plan.state === "loading"}
            >
              {plan.state === "loading" ? "Planning…" : "Create Allocation Plan"}
            </button>
            {planReady ? (
              <button
                type="button"
                className="allocation-action outline allocation-secondary-cta"
                disabled={plan.data?.status === "confirmed" || confirming}
                onClick={() => void confirmPlan()}
              >
                {confirming ? "Confirming…" : plan.data?.status === "confirmed" ? "Confirmed" : "Confirm plan"}
              </button>
            ) : null}
            {planReady ? (
              <button
                type="button"
                className="allocation-action outline allocation-secondary-cta"
                disabled={!planConfirmed}
                title={planConfirmed ? undefined : "Confirm the plan before printing"}
                onClick={() => setPrintOpen(true)}
              >
                Print preview
              </button>
            ) : null}
          </form>
          {inventoryError ? <p className="state error">Inventory unavailable: {inventoryError}</p> : null}
        </article>
      </section>

      {printOpen && plan.data ? (
        <AllocationPrintPreview
          plan={plan.data}
          emphasizedTownshipId={highlightedTownshipId}
          onClose={() => setPrintOpen(false)}
        />
      ) : null}
      <ViewDialog title="Saved plans" open={historyOpen} onClose={() => setHistoryOpen(false)}>
        <div className="history-table" role="table">
          {historySlice.map((item) => (
            <button
              type="button"
              className="history-row allocation"
              key={item.plan_id}
              onClick={() => {
                setHistoryOpen(false);
                void openHistoryPlan(item.plan_id);
              }}
            >
              <strong>#{item.plan_id}</strong>
              <span>{item.status}</span>
              <span>{(item.planning_date ?? item.created_at).slice(0, 10)}</span>
            </button>
          ))}
        </div>
        <PageControls page={historyPage} pages={historyPages} onPage={setHistoryPage} />
      </ViewDialog>
    </main>
  );
}
