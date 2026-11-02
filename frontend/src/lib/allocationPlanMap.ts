import type { AllocationPlanResponse, Coordinates } from "../types";
import type { OverviewDepot, OverviewRoute, OverviewTownship } from "../components/allocation/AllocationOverviewMap";
import { depotReferenceCoords, resolveTownshipPosition } from "./resolveTownshipPosition";

function warehouses(plan: AllocationPlanResponse) {
  return plan.warehouses.length ? plan.warehouses : [plan.warehouse];
}

export function depotsFromPlan(plan: AllocationPlanResponse): OverviewDepot[] {
  return warehouses(plan).map((warehouse) => {
    const ref = depotReferenceCoords(warehouse.region);
    return {
      id: warehouse.id,
      name: warehouse.name,
      latitude: ref.latitude,
      longitude: ref.longitude,
      region: warehouse.region,
    };
  });
}

export function townshipsFromPlan(plan: AllocationPlanResponse): OverviewTownship[] {
  return plan.rows.map((row) => {
    const position = resolveTownshipPosition(row.township_name, row.latitude, row.longitude);
    return {
      id: row.township_id,
      name: row.township_name,
      latitude: position.latitude,
      longitude: position.longitude,
      districtId: "",
    };
  });
}

function rowPosition(row: AllocationPlanResponse["rows"][number]): Coordinates {
  const position = resolveTownshipPosition(row.township_name, row.latitude, row.longitude);
  return { latitude: position.latitude, longitude: position.longitude };
}

export function routesFromPlan(
  plan: AllocationPlanResponse,
  depots: OverviewDepot[],
  emphasizedTownshipId?: string | null,
): OverviewRoute[] {
  const depotFor = (region: "east" | "west") => depots.find((depot) => depot.region === region);
  return plan.rows.flatMap((row) => {
    const depot = depotFor(row.depot_region);
    if (!depot) return [];
    const destination = rowPosition(row);
    const saved = plan.routes.find((route) => route.route_id === row.route_id && route.path.length >= 2);
    const path =
      saved && saved.path.length >= 2
        ? saved.path
        : [
            { latitude: depot.latitude, longitude: depot.longitude },
            destination,
          ];
    return [
      {
        id: row.township_id,
        label: row.township_name,
        depotRegion: row.depot_region,
        distanceM: saved?.distance_m ?? null,
        emphasized: row.township_id === emphasizedTownshipId,
        path,
      },
    ];
  });
}
