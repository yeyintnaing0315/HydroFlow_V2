import type { AllocationPlanResponse } from "../types";
import type { OverviewDepot, OverviewRoute } from "../components/allocation/AllocationOverviewMap";
import { depotsFromPlan, routesFromPlan } from "./allocationPlanMap";

export type PrintRouteMode = "single" | "dual";

export function printMapRoutes(
  plan: AllocationPlanResponse,
  mode: PrintRouteMode,
  emphasizedTownshipId?: string | null,
): { depots: OverviewDepot[]; routes: OverviewRoute[] } {
  const depots = depotsFromPlan(plan);
  const primary = routesFromPlan(plan, depots, emphasizedTownshipId);
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
