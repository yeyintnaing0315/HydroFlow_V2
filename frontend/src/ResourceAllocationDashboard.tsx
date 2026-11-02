import { FormEvent, useEffect, useMemo, useState } from "react";
import { api } from "./api";
import AllocationFloodHistory from "./components/allocation/AllocationFloodHistory";
import AllocationOverviewMap from "./components/allocation/AllocationOverviewMap";
import AllocationPrintPreview from "./components/allocation/AllocationPrintPreview";
import RouteComparison from "./components/allocation/RouteComparison";
import { formatMeters, routeMethodLabel } from "./components/allocation/routeFormat";
import TownshipAllocationDetail from "./components/allocation/TownshipAllocationDetail";
import { PageControls, ViewDialog } from "./components/ViewDialog";
import { errorText } from "./lib/formatError";
import type { AllocationFocus } from "./lib/allocationFocus";
import { depotRegionForCoordinates, type DepotRegion } from "./lib/depotRegion";
import { depotsFromPlan, routesFromPlan, townshipsFromPlan } from "./lib/allocationPlanMap";
import { depotReferenceCoords, resolveTownshipPosition } from "./lib/resolveTownshipPosition";
import { floodBandLabel, floodFillLevel, riskLabel } from "./components/prediction/mapUtils";
import type {
  AllocationBlockedSegment,
  AllocationPlanHistoryItem,
  AllocationPlanResponse,
  AllocationStoreStatus,
  AssistancePriority,
  BagoAreasResponse,
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

function inStockLines(snapshot: InventorySnapshot | undefined) {
  return (snapshot?.classes ?? []).flatMap((klass) =>
    klass.items
      .filter((item) => item.quantity > 0)
      .map((item) => ({
        key: `${klass.code}:${item.code ?? "fund"}`,
        name: item.name,
        quantity: item.quantity,
        unit: item.unit,
      })),
  );
}

function affectedLabel(value: number | null | undefined, pending: boolean): string {
  if (pending) return "…";
  if (value == null) return "—";
  return value.toLocaleString();
}

function depotLabel(region: RegionCode): string {
  return region === "east" ? "Bago (east)" : "Pyay (west)";
}

function planRequestBody(startDate: string, focus: AllocationFocus | null | undefined) {
  return {
    date: startDate,
    warehouse_region: "auto" as const,
    min_priority: ALLOCATION_MIN_PRIORITY,
    // Focused view: one date + one township. Region view: all high/severe townships that day.
    include_all_high_severe: !focus,
    township_ids: focus ? [focus.townshipId] : undefined,
    commit_inventory: false,
    vehicle_profile: "truck" as const,
  };
}

export default function ResourceAllocationDashboard({
  startDate,
  focus,
  onClearFocus,
  onOpenInventory,
  areas,
}: ResourceAllocationDashboardProps) {
  const [inventoryEast, setInventoryEast] = useState<Resource<InventorySnapshot>>({ state: "empty" });
  const [inventoryWest, setInventoryWest] = useState<Resource<InventorySnapshot>>({ state: "empty" });
  const [plan, setPlan] = useState<Resource<SavedPlan>>({ state: "empty" });
  const [stores, setStores] = useState<AllocationStoreStatus[]>([]);
  const [history, setHistory] = useState<AllocationPlanHistoryItem[]>([]);
  const [confirming, setConfirming] = useState(false);
  const [confirmError, setConfirmError] = useState<string | undefined>();
  const [verifyError, setVerifyError] = useState<string | undefined>();
  const [selectedTownshipId, setSelectedTownshipId] = useState<string | null>(null);
  const [comparison, setComparison] = useState<TownshipRouteComparison | null>(null);
  const [compareState, setCompareState] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [compareError, setCompareError] = useState<string | undefined>();
  const [selectingRoute, setSelectingRoute] = useState(false);
  const [routesOpen, setRoutesOpen] = useState(false);
  const [printOpen, setPrintOpen] = useState(false);
  const [stockView, setStockView] = useState<"east" | "west" | null>(null);
  const [stockPage, setStockPage] = useState(0);
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
    if (plan.state === "ready") return;
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
          return [score.township_id, day?.expected_affected_people ?? null] as const;
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
  }, [predictionHighSevere, startDate, plan.state]);

  const runPlan = async () => {
    setPlan(loading);
    setConfirmError(undefined);
    setRoutesOpen(false);
    setComparison(null);
    setCompareState("idle");
    try {
      const result = (await api.allocationPlan(planRequestBody(startDate, focus))) as SavedPlan;
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

  const verifyDepot = async (region: RegionCode) => {
    setVerifyError(undefined);
    try {
      await api.verifyAllocationStore(region, "Stock confirmed");
      await refreshStores();
    } catch (reason) {
      setVerifyError(errorText(reason));
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

  const overviewMapTownships = useMemo(() => {
    if (planReady && plan.data) return townshipsFromPlan(plan.data);
    return overviewTownships.filter((township) => !isDepotTownship(township.name));
  }, [planReady, plan.data, overviewTownships]);

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
    const targets = overviewTownships.filter((township) => !isDepotTownship(township.name));
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
  }, [planReady, overviewDepots, overviewTownships, stores]);

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
      return `${selectedRow.township_name} · ${active.label} · ${routeMethodLabel(active.routing_method)} · ${formatMeters(active.distance_m)}`;
    }
    const route = (plan.data?.routes ?? []).find((item) => item.route_id === selectedRow.route_id);
    const method = (route as SavedRoute | undefined)?.routing_method;
    const meters = formatMeters(route?.distance_m);
    return `${selectedRow.township_name} · ${selectedRow.route_id}${method ? ` · ${routeMethodLabel(method)}` : ""}${meters === "—" ? "" : ` · ${meters}`}`;
  }, [selectedRow, comparison, routesOpen, plan.data]);

  const mapHint = planReady
    ? routeCaption ||
      (listedRows.length
        ? "Delivery routes for high and severe townships. Distance is shown in meters."
        : "No high or severe townships for this date.")
    : networkRoutesLoading
      ? "Loading driving routes on OpenStreetMap roads…"
      : "Road routes from the nearer depot (OSRM). Distance is in meters. Select a township or create a plan for high and severe deliveries.";

  const affectedRows = planReady
    ? listedRows.map((row) => ({
        id: row.township_id,
        name: row.township_name,
        affected: row.population as number | null,
        pending: false,
      }))
    : predictionHighSevere.map((score) => ({
        id: score.township_id,
        name: score.township_name,
        affected: score.township_id in affectedByTownship ? affectedByTownship[score.township_id] : null,
        pending: affectedLoading && !(score.township_id in affectedByTownship),
      }));

  const eastStock = inStockLines(inventoryEast.data);
  const westStock = inStockLines(inventoryWest.data);

  const scoreForTownship = (townshipId: string, name: string) => {
    const direct = scoreMap.get(townshipId);
    if (direct) return direct;
    const normalized = name.trim().toLowerCase();
    for (const score of scoreMap.values()) {
      if (score.township_name.trim().toLowerCase() === normalized) return score;
    }
    return undefined;
  };

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

  const roadRouteCount = Object.keys(networkRoutesByTownship).length;

  const alerts: { tone: "error" | "status"; message: string }[] = [];
  if (plan.state === "error" && plan.error) alerts.push({ tone: "error", message: `Plan failed: ${plan.error}` });
  if (confirmError) alerts.push({ tone: "error", message: `Confirm failed: ${confirmError}` });
  if (plan.data?.shortages.length) {
    const count = plan.data.shortages.length;
    alerts.push({
      tone: "status",
      message: `Stock shortage on ${count} line${count === 1 ? "" : "s"}.`,
    });
  }
  if (plan.data?.unverified_stores?.length) {
    alerts.push({
      tone: "status",
      message: `Unverified depots were not used: ${plan.data.unverified_stores.map((store) => store.name).join(", ")}. Verify stock, then create the plan again before confirm.`,
    });
  }
  const stockSource = stockView === "east" ? inventoryEast.data : stockView === "west" ? inventoryWest.data : undefined;
  const stockLines = (stockSource?.classes ?? []).flatMap((klass) =>
    klass.items.filter((item) => item.quantity > 0).map((item) => ({ klass, item })),
  );
  const stockPages = Math.max(1, Math.ceil(stockLines.length / 6));
  const stockSlice = stockLines.slice(stockPage * 6, stockPage * 6 + 6);
  const historyPages = Math.max(1, Math.ceil(history.length / 6));
  const historySlice = history.slice(historyPage * 6, historyPage * 6 + 6);

  return (
    <main className="allocation-board allocation-board-single">
      <div className="allocation-toolbar panel allocation-toolbar-meta">
        <div className="allocation-priority-side">
          <span className="field-label">Planning date</span>
          <strong className="allocation-priority-value">{plan.data?.planning_date ?? startDate}</strong>
        </div>
        <div className="allocation-priority-side">
          <span className="field-label">Priority scope</span>
          <strong className="allocation-priority-value">{priorityScopeLabel}</strong>
        </div>
        {focus && onClearFocus ? (
          <button type="button" className="text-link" onClick={onClearFocus}>
            All townships
          </button>
        ) : null}
        <div className="allocation-toolbar-links">
          {onOpenInventory ? (
            <button type="button" className="text-link" onClick={onOpenInventory}>
              Open inventory
            </button>
          ) : null}
          <button
            type="button"
            className="text-link"
            onClick={() => {
              setHistoryPage(0);
              setHistoryOpen(true);
              void refreshHistory();
            }}
          >
            Saved plans
          </button>
        </div>
      </div>

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
        <div className="section-heading">
          <div>
            <h2>Route map</h2>
          </div>
          <span className="source">
            {planReady
              ? `${listedRows.length} high or severe`
              : `Bago east · Pyay west · ${roadRouteCount || overviewRoutes.length} road routes`}
          </span>
        </div>
        {!printOpen ? (
          <AllocationOverviewMap
            instanceKey="allocation-dashboard-map"
            townships={overviewMapTownships}
            depots={overviewDepots}
            routes={overviewRoutes}
            focusTownshipId={highlightedTownshipId}
            onSelectTownship={(townshipId) => {
              if (planReady && !listedRows.some((row) => row.township_id === townshipId)) return;
              selectTownship(townshipId);
            }}
          />
        ) : (
          <div className="allocation-map-frame allocation-map-sleep" aria-hidden />
        )}
        <AllocationFloodHistory />
        <ul className="legend" aria-label="Map legend">
          <li><i style={{ background: "#0b5873" }} />East depot routes</li>
          <li><i style={{ background: "#c45a1a" }} />West depot routes</li>
          <li><i style={{ background: "#f4b942" }} />Bago depot</li>
          <li><i style={{ background: "#e07a2f" }} />Pyay depot</li>
        </ul>
        <p className="hint">{mapHint}</p>
      </section>

      <section className="allocation-split-side">
        <div className="allocation-kpi-row" aria-label="Allocation overview">
          <article className="allocation-kpi">
            <span>Affected population (est.)</span>
            <strong>
              {affectedLoading && !planReady
                ? "…"
                : totalAffectedEst == null
                  ? "—"
                  : totalAffectedEst.toLocaleString()}
            </strong>
          </article>
          <article className="allocation-kpi">
            <span>High risk townships</span>
            <strong>{affectedRows.length}</strong>
          </article>
          <article className="allocation-kpi">
            <span>{planReady ? "Shortage lines" : "Road routes loaded"}</span>
            <strong>
              {planReady
                ? (plan.data?.shortages.length ?? 0).toLocaleString()
                : networkRoutesLoading
                  ? "…"
                  : roadRouteCount.toLocaleString()}
            </strong>
          </article>
        </div>

        <article className="panel allocation-action-card">
          <div className="allocation-action-head">
            <h2>Allocation plan</h2>
            <span className="source">{priorityScopeLabel}</span>
          </div>
          <form className="allocation-plan-form allocation-plan-form-side" onSubmit={submitPlan}>
            <button type="submit" className="allocation-action primary" disabled={plan.state === "loading"}>
              {plan.state === "loading" ? "Planning…" : "Create plan"}
            </button>
            {planReady ? (
              <button
                type="button"
                className="allocation-action outline"
                disabled={plan.data?.status === "confirmed" || confirming}
                onClick={() => void confirmPlan()}
              >
                {confirming ? "Confirming…" : plan.data?.status === "confirmed" ? "Confirmed" : "Confirm plan"}
              </button>
            ) : null}
            {planReady ? (
              <button type="button" className="allocation-action outline" onClick={() => setPrintOpen(true)}>
                Print preview
              </button>
            ) : null}
          </form>
        </article>

        <article className="panel allocation-table-card" role="region" aria-label="High and severe townships">
          <div className="section-heading allocation-table-head">
            <h2>Allocation summary</h2>
            <span className="source">{affectedRows.length ? `${affectedRows.length} townships` : "No high or severe"}</span>
          </div>
          <div className="allocation-table-wrap">
            <table className="allocation-summary-table">
              <thead>
                <tr>
                  <th scope="col">Township</th>
                  <th scope="col">Risk</th>
                  <th scope="col">Affected people</th>
                </tr>
              </thead>
              <tbody>
                {affectedRows.length === 0 ? (
                  <tr className="allocation-summary-empty">
                    <td>—</td>
                    <td>—</td>
                    <td>—</td>
                  </tr>
                ) : (
                  affectedRows.map((row) => {
                    const score = scoreForTownship(row.id, row.name);
                    const risk = planReady
                      ? listedRows.find((item) => item.township_id === row.id)?.priority ?? "high"
                      : score
                        ? floodFillLevel(score)
                        : "unknown";
                    return (
                      <tr
                        key={row.id}
                        className={row.id === highlightedTownshipId ? "is-selected" : ""}
                        onClick={() => {
                          if (planReady && !listedRows.some((item) => item.township_id === row.id)) return;
                          selectTownship(row.id);
                        }}
                        onKeyDown={(event) => {
                          if (event.key !== "Enter" && event.key !== " ") return;
                          event.preventDefault();
                          if (planReady && !listedRows.some((item) => item.township_id === row.id)) return;
                          selectTownship(row.id);
                        }}
                        tabIndex={0}
                        role="button"
                      >
                        <td>{row.name}</td>
                        <td>
                          <span className={`risk-pill risk-${risk}`}>{floodBandLabel(String(risk))}</span>
                        </td>
                        <td>{affectedLabel(row.affected, row.pending)}</td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </article>
        {planReady && plan.data ? (
          <article className="panel allocation-table-card" role="region" aria-label="Allocation summary">
            <div className="section-heading allocation-table-head">
              <h2>To give</h2>
              <span className="source">
                {plan.data.totals.affected_population.toLocaleString()} people · {plan.data.shortages.length} shortages
              </span>
            </div>
            <div className="allocation-box-scroll">
          <TownshipAllocationDetail row={selectedRow} depotLabel={depotLabel} />
          {selectedRow ? (
            <button
              type="button"
              className="text-link allocation-other-roads"
              onClick={() => {
                if (routesOpen) {
                  setRoutesOpen(false);
                  setComparison(null);
                  setCompareState("idle");
                  setCompareError(undefined);
                  return;
                }
                setRoutesOpen(true);
              }}
            >
              {routesOpen ? "Hide roads" : "Other roads"}
            </button>
          ) : null}
          {routesOpen ? (
            <RouteComparison
              state={compareState}
              error={compareError}
              comparison={comparison}
              selecting={selectingRoute}
              onSelect={(optionIndex) => void chooseRoute(optionIndex)}
            />
          ) : null}
            </div>
          </article>
        ) : (
          <article className="panel allocation-table-card" role="region" aria-label="East and west stock">
            <div className="section-heading allocation-table-head">
              <h2>Depot stock</h2>
              <span className="source">East and west</span>
            </div>
            {inventoryError ? <p className="state error">Inventory unavailable: {inventoryError}</p> : null}
            {verifyError ? <p className="state error">Could not verify stock: {verifyError}</p> : null}
            <div className="allocation-box-scroll">
              <div className="allocation-stock-grid">
                {(["east", "west"] as RegionCode[]).map((region) => {
                  const lines = region === "east" ? eastStock : westStock;
                  const store = stores.find((item) => item.region === region);
                  return (
                    <div key={region} className="allocation-stock-depot">
                      <h3>
                        {depotLabel(region)}{" "}
                        {store ? (
                          <span className={store.verified_at ? "township-chip" : "shortage-tag"}>
                            {store.verified_at ? "Verified" : "Unverified"}
                          </span>
                        ) : null}
                      </h3>
                      {store && !store.verified_at ? (
                        <button type="button" className="text-link" onClick={() => void verifyDepot(region)}>
                          Mark stock verified
                        </button>
                      ) : null}
                      <ul>
                        {lines.slice(0, 4).map((item) => (
                          <li key={`${region}:${item.key}`}>
                            <span>{item.name}</span>
                            <span>
                              {item.quantity.toLocaleString()} {item.unit}
                            </span>
                          </li>
                        ))}
                        {!lines.length ? <li className="state">No stock</li> : null}
                      </ul>
                      {lines.length > 4 ? (
                        <button
                          type="button"
                          className="text-link"
                          onClick={() => {
                            setStockPage(0);
                            setStockView(region);
                          }}
                        >
                          View stock
                        </button>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            </div>
          </article>
        )}
      </section>

      {printOpen && plan.data ? (
        <AllocationPrintPreview plan={plan.data} onClose={() => setPrintOpen(false)} />
      ) : null}
      <ViewDialog
        title={stockView ? `${depotLabel(stockView)} stock` : "Stock"}
        open={stockView != null}
        onClose={() => setStockView(null)}
      >
        <ul className="allocation-line-items">
          {stockSlice.map(({ klass, item }) => (
            <li key={`${klass.code}:${item.code ?? "fund"}`}>
              <span>{item.name}</span>
              <span>
                {item.quantity.toLocaleString()} {item.unit}
              </span>
            </li>
          ))}
        </ul>
        <PageControls page={stockPage} pages={stockPages} onPage={setStockPage} />
      </ViewDialog>
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
