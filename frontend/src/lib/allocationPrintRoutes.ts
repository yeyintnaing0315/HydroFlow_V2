import type { AllocationPlanResponse, AllocationTownshipRow, Coordinates } from "../types";
import type { OverviewDepot, OverviewRoute } from "../components/allocation/AllocationOverviewMap";
import { depotsFromPlan, routesFromPlan } from "./allocationPlanMap";

export type PrintRouteMode = "single" | "dual";

/** Road geometry already drawn on the plan map (OSRM leg per township). */
export interface PrintRoadRoute {
  path: Coordinates[];
  distanceM: number | null;
}

function isDetailedRoad(path: Coordinates[], method?: string | null): boolean {
  return path.length > 2 && method !== "straight_line_fallback";
}

/** Saved plan geometry, used when the live road preview has not arrived yet. */
function savedRoad(plan: AllocationPlanResponse, row: AllocationTownshipRow): PrintRoadRoute | null {
  const option =
    row.route_options?.find((item) => item.selected) ??
    row.route_options?.find((item) => item.recommended);
  if (option && isDetailedRoad(option.path, option.routing_method)) {
    return { path: option.path, distanceM: option.distance_m };
  }
  const route = plan.routes.find((item) => item.route_id === row.route_id);
  if (route && route.stop_count === 1 && isDetailedRoad(route.path, route.routing_method)) {
    return { path: route.path, distanceM: route.distance_m ?? null };
  }
  return null;
}

export function printMapRoutes(
  plan: AllocationPlanResponse,
  mode: PrintRouteMode,
  emphasizedTownshipId?: string | null,
  roadByTownship?: Record<string, PrintRoadRoute>,
  roadsLoading = false,
): { depots: OverviewDepot[]; routes: OverviewRoute[] } {
  const depots = depotsFromPlan(plan);
  const rowById = new Map(plan.rows.map((row) => [row.township_id, row]));
  const primary = routesFromPlan(plan, depots, emphasizedTownshipId).map((route) => {
    const live = roadByTownship?.[route.id];
    if (live && live.path.length >= 2) {
      return { ...route, path: live.path, distanceM: live.distanceM };
    }
    const row = rowById.get(route.id);
    const saved = row ? savedRoad(plan, row) : null;
    if (saved) {
      return { ...route, path: saved.path, distanceM: saved.distanceM };
    }
    if (roadsLoading) {
      return { ...route, path: [] };
    }
    return route;
  });
  if (mode === "single") {
    return { depots, routes: primary };
  }
  const alternates: OverviewRoute[] = [];
  for (const row of plan.rows) {
    const options = row.route_options ?? [];
    if (options.length < 2) continue;
    const alternate =
      options.find((option) => !option.selected && option.recommended) ??
      options.find((option) => !option.selected) ??
      options[1];
    if (!alternate || alternate.path.length < 2) continue;
    alternates.push({
      id: `${row.township_id}-alt`,
      label: `${row.township_name} alt`,
      depotRegion: row.depot_region,
      distanceM: alternate.distance_m,
      emphasized: false,
      dimmed: true,
      path: alternate.path,
    });
  }
  return { depots, routes: [...primary, ...alternates] };
}
