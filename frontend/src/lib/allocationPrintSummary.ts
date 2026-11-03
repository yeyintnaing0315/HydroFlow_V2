import type { AllocationPlanResponse } from "../types";
import { formatDistance, routeMethodLabel } from "../components/allocation/routeFormat";

export interface PlanResourceSummary {
  fundAllocatedMmk: number;
  otherUnitsAllocated: number;
  skuTypes: number;
  people: number;
  townshipCount: number;
  shortageLines: number;
  depotLabels: string[];
}

export function summarizePlanResources(plan: AllocationPlanResponse): PlanResourceSummary {
  let fundAllocatedMmk = 0;
  let otherUnitsAllocated = 0;
  const skuKeys = new Set<string>();
  for (const row of plan.rows) {
    for (const item of row.line_items) {
      const key = `${item.category_code}:${item.item_code ?? "fund"}`;
      skuKeys.add(key);
      if (item.category_code === "fund" && item.item_code == null) {
        fundAllocatedMmk += item.allocated;
      } else {
        otherUnitsAllocated += item.allocated;
      }
    }
  }
  const warehouses = plan.warehouses.length ? plan.warehouses : [plan.warehouse];
  return {
    fundAllocatedMmk,
    otherUnitsAllocated,
    skuTypes: skuKeys.size,
    people: plan.totals.affected_population,
    townshipCount: plan.rows.length,
    shortageLines: plan.shortages.length,
    depotLabels: warehouses.map((warehouse) => warehouse.name),
  };
}

export function planRouteSummaries(plan: AllocationPlanResponse): string[] {
  return plan.routes.map((route) => {
    const distance = formatDistance(route.distance_m);
    const method = routeMethodLabel(route.routing_method);
    const depot = route.depot_region === "east" ? "Bago (east)" : "Pyay (west)";
    return `${route.route_id} · ${depot} · ${route.stop_count} stop(s) · ${method}${distance === "—" ? "" : ` · ${distance}`}`;
  });
}

export function selectedRouteLabels(plan: AllocationPlanResponse): string[] {
  return plan.rows.map((row) => {
    const picked =
      row.route_options?.find((option) => option.selected) ??
      row.route_options?.find((option) => option.recommended);
    const saved = plan.routes.find((route) => route.route_id === row.route_id);
    const distance = formatDistance(picked?.distance_m ?? saved?.distance_m);
    const method = routeMethodLabel(picked?.routing_method ?? saved?.routing_method);
    const label = picked?.label ?? row.route_id;
    return `${row.township_name}: ${label} (${method}${distance === "—" ? "" : ` · ${distance}`})`;
  });
}
