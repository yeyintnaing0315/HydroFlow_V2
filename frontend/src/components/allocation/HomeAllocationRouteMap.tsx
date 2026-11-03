import { useEffect, useMemo, useState } from "react";
import { api } from "../../api";
import { depotRegionForCoordinates } from "../../lib/depotRegion";
import { isDepotTownship } from "../../lib/isDepotTownship";
import { depotReferenceCoords, resolveTownshipPosition } from "../../lib/resolveTownshipPosition";
import type {
  AllocationStoreStatus,
  BagoAreasResponse,
  Coordinates,
  InventorySnapshot,
  LoadState,
} from "../../types";
import AllocationFloodHistory from "./AllocationFloodHistory";
import AllocationRouteMapPanel from "./AllocationRouteMapPanel";
import type { OverviewDepot, OverviewRoute, OverviewTownship } from "./AllocationOverviewMap";

interface HomeAllocationRouteMapProps {
  areas: {
    state: LoadState;
    data?: BagoAreasResponse;
  };
  inventory: {
    state: LoadState;
    data?: InventorySnapshot[];
  };
  planningDate: string;
}

function overviewTownshipsFromAreas(areas?: BagoAreasResponse): OverviewTownship[] {
  return (areas?.districts ?? []).flatMap((district) =>
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
}

function depotsFromStoresAndInventory(
  stores: AllocationStoreStatus[],
  locations: InventorySnapshot[] | undefined,
): OverviewDepot[] {
  const eastStore = stores.find((store) => store.region === "east");
  const westStore = stores.find((store) => store.region === "west");
  const eastInventory = locations?.find((store) => store.region === "east");
  const westInventory = locations?.find((store) => store.region === "west");
  const eastRef = depotReferenceCoords("east");
  const westRef = depotReferenceCoords("west");
  return [
    {
      id: "depot-bago",
      name: eastStore?.name ?? eastInventory?.location ?? "Bago depot (east)",
      latitude: eastStore?.latitude ?? eastRef.latitude,
      longitude: eastStore?.longitude ?? eastRef.longitude,
      region: "east",
    },
    {
      id: "depot-pyay",
      name: westStore?.name ?? westInventory?.location ?? "Pyay depot (west)",
      latitude: westStore?.latitude ?? westRef.latitude,
      longitude: westStore?.longitude ?? westRef.longitude,
      region: "west",
    },
  ];
}

export default function HomeAllocationRouteMap({
  areas,
  inventory,
  planningDate,
}: HomeAllocationRouteMapProps) {
  const [stores, setStores] = useState<AllocationStoreStatus[]>([]);
  const [networkRoutesByTownship, setNetworkRoutesByTownship] = useState<
    Record<string, { path: Coordinates[]; distanceM: number | null }>
  >({});
  const [networkRoutesLoading, setNetworkRoutesLoading] = useState(false);

  const areaTownships = useMemo(() => overviewTownshipsFromAreas(areas.data), [areas.data]);

  useEffect(() => {
    let active = true;
    api
      .allocationStores()
      .then((data) => {
        if (active) setStores(data);
      })
      .catch(() => {
        if (active) setStores([]);
      });
    return () => {
      active = false;
    };
  }, []);

  const depots = useMemo(
    () => depotsFromStoresAndInventory(stores, inventory.data),
    [stores, inventory.data],
  );

  const townships = useMemo((): OverviewTownship[] => {
    const base = areaTownships.filter((township) => !isDepotTownship(township.name));
    const routedIds = Object.keys(networkRoutesByTownship);
    if (routedIds.length === 0) {
      return networkRoutesLoading ? [] : base;
    }
    const visible = new Set(routedIds);
    return base.filter((township) => visible.has(township.id));
  }, [areaTownships, networkRoutesByTownship, networkRoutesLoading]);

  useEffect(() => {
    if (areas.state !== "ready" || !areas.data) return;
    const east = depots.find((depot) => depot.region === "east");
    const west = depots.find((depot) => depot.region === "west");
    if (!east || !west) return;
    const targets = areaTownships.filter((township) => !isDepotTownship(township.name));
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
  }, [areas.state, areas.data, depots, areaTownships]);

  const routes = useMemo((): OverviewRoute[] => {
    const east = depots.find((depot) => depot.region === "east");
    const west = depots.find((depot) => depot.region === "west");
    if (!east || !west) return [];
    return areaTownships
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
            path: network.path,
          },
        ];
      });
  }, [depots, areaTownships, networkRoutesByTownship]);

  const loadingMessage = networkRoutesLoading ? "Loading routes…" : null;

  if (areas.state === "loading") {
    return <p className="state">Loading area data for the route map…</p>;
  }
  if (areas.state === "error") {
    return <p className="state">Area data is required to draw depot routes.</p>;
  }

  return (
    <div className="home-allocation-route-wrap">
      <AllocationRouteMapPanel
        headingLevel="h3"
        stackClassName="allocation-map-stack home-allocation-map-stack"
        instanceKey="home-allocation-route-map"
        planningDate={planningDate}
        townshipLabel="All high and severe"
        sourceNote={null}
        townships={townships}
        depots={depots}
        routes={routes}
        focusTownshipId={null}
        loadingMessage={loadingMessage}
      />
      <details className="allocation-flood-history-details">
        <summary>Flood history</summary>
        <AllocationFloodHistory />
      </details>
    </div>
  );
}
