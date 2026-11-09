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

const CONNECTOR_MAX_M = 3_000;

function gapMeters(from: Coordinates, to: Coordinates): number {
  const midLat = ((from.latitude + to.latitude) / 2) * (Math.PI / 180);
  const dLat = (from.latitude - to.latitude) * 111_320;
  const dLon = (from.longitude - to.longitude) * 111_320 * Math.cos(midLat);
  return Math.hypot(dLat, dLon);
}

/** Join a road to the town pin only when the road already ends nearby. */
export function routePathForTownship(path: Coordinates[], township: Coordinates): Coordinates[] {
  if (path.length < 2) return path;
  const last = path[path.length - 1];
  const gap = gapMeters(last, township);
  if (gap <= CONNECTOR_MAX_M && gap > 1) {
    return [...path, { latitude: township.latitude, longitude: township.longitude }];
  }
  return path;
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
    return [
      {
        id: row.township_id,
        label: row.township_name,
        depotRegion: row.depot_region,
        distanceM: null,
        emphasized: row.township_id === emphasizedTownshipId,
        path: [
          { latitude: depot.latitude, longitude: depot.longitude },
          destination,
        ],
      },
    ];
  });
}
