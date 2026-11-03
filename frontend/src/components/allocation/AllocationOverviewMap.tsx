import { useEffect } from "react";
import { CircleMarker, MapContainer, Pane, Polyline, Popup, Tooltip, useMap } from "react-leaflet";
import BasemapTileLayer from "../map/BasemapTileLayer";
import MapViewportFix from "../map/MapViewportFix";
import { formatDistance } from "./routeFormat";
import type { Coordinates } from "../../types";

export interface OverviewTownship {
  id: string;
  name: string;
  latitude: number;
  longitude: number;
  districtId: string;
}

export interface OverviewDepot {
  id: string;
  name: string;
  latitude: number;
  longitude: number;
  region: "east" | "west";
}

export interface OverviewRoute {
  id: string;
  label: string;
  path: Coordinates[];
  depotRegion: "east" | "west";
  distanceM: number | null;
  emphasized?: boolean;
  dimmed?: boolean;
}

interface AllocationOverviewMapProps {
  townships: OverviewTownship[];
  depots: OverviewDepot[];
  routes: OverviewRoute[];
  focusTownshipId?: string | null;
  onSelectTownship?: (townshipId: string) => void;
  /** Shown over the map while OSRM or route comparison is in flight. */
  loadingMessage?: string | null;
  /** Separate Leaflet instances (dashboard vs print) must not mount at the same time. */
  instanceKey?: string;
}

const ROUTE_COLORS = { east: "#0b5873", west: "#c45a1a" } as const;
const DEPOT_STYLE = {
  east: { color: "#17324a", fillColor: "#f4b942" },
  west: { color: "#4a1730", fillColor: "#e07a2f" },
} as const;

function fitPointsForOverview(
  townships: OverviewTownship[],
  depots: OverviewDepot[],
  routes: OverviewRoute[],
  focusTownshipId?: string | null,
): [number, number][] {
  const routesForFit =
    focusTownshipId && routes.some((route) => route.id === focusTownshipId)
      ? routes.filter((route) => route.id === focusTownshipId)
      : routes;
  const routedIds = new Set(routesForFit.map((route) => route.id));
  const depotRegions = new Set(routesForFit.map((route) => route.depotRegion));

  const points: [number, number][] = [];
  for (const depot of depots) {
    if (routesForFit.length === 0 || depotRegions.has(depot.region)) {
      points.push([depot.latitude, depot.longitude]);
    }
  }
  for (const township of townships) {
    if (routesForFit.length === 0) continue;
    if (routedIds.has(township.id) || township.id === focusTownshipId) {
      points.push([township.latitude, township.longitude]);
    }
  }
  for (const route of routesForFit) {
    for (const point of route.path) points.push([point.latitude, point.longitude]);
  }
  return points;
}

function FitOverview({
  townships,
  depots,
  routes,
  focusTownshipId,
}: {
  townships: OverviewTownship[];
  depots: OverviewDepot[];
  routes: OverviewRoute[];
  focusTownshipId?: string | null;
}) {
  const map = useMap();
  useEffect(() => {
    if (typeof map.getContainer !== "function") return;
    const container = map.getContainer();
    const points = fitPointsForOverview(townships, depots, routes, focusTownshipId);
    if (points.length === 0) return;

    const focused = Boolean(
      focusTownshipId && routes.some((route) => route.id === focusTownshipId),
    );
    const maxZoom = focused ? 13 : routes.length > 0 ? 11 : 10;
    const padding: [number, number] = focused ? [14, 14] : [16, 16];

    const fit = () => {
      try {
        map.invalidateSize();
        if (points.length === 1) map.setView(points[0], maxZoom);
        else map.fitBounds(points, { padding, maxZoom });
      } catch {
        // Leaflet can throw if the map is torn down during a reload.
      }
    };
    const frame = requestAnimationFrame(fit);
    if (typeof ResizeObserver === "undefined") {
      return () => cancelAnimationFrame(frame);
    }
    const observer = new ResizeObserver(() => {
      const size = map.getSize();
      const box = container.getBoundingClientRect();
      if (Math.abs(size.x - box.width) > 2 || Math.abs(size.y - box.height) > 2) fit();
    });
    observer.observe(container);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, [map, townships, depots, routes, focusTownshipId]);
  return null;
}

function pathEndsNear(
  path: Coordinates[],
  latitude: number,
  longitude: number,
  maxDelta = 0.015,
): boolean {
  const last = path[path.length - 1];
  if (!last) return false;
  return Math.abs(last.latitude - latitude) <= maxDelta && Math.abs(last.longitude - longitude) <= maxDelta;
}

function routePathForTownship(route: OverviewRoute, township: OverviewTownship): Coordinates[] {
  if (route.path.length < 2) return route.path;
  if (pathEndsNear(route.path, township.latitude, township.longitude)) return route.path;
  return [
    ...route.path,
    { latitude: township.latitude, longitude: township.longitude },
  ];
}

export default function AllocationOverviewMap({
  townships,
  depots,
  routes,
  focusTownshipId,
  onSelectTownship,
  loadingMessage = null,
  instanceKey = "allocation-overview-map",
}: AllocationOverviewMapProps) {
  const routeById = new Map(routes.map((route) => [route.id, route]));
  const routeByName = new Map(routes.map((route) => [route.label.trim().toLowerCase(), route]));

  return (
    <div className="allocation-map-frame">
      {loadingMessage ? (
        <div className="allocation-map-loading-overlay" role="status" aria-live="polite">
          {loadingMessage}
        </div>
      ) : null}
      <MapContainer
        key={instanceKey}
        center={[18.26, 96.07]}
        zoom={10}
        scrollWheelZoom={false}
        className="allocation-map"
        aria-label="Allocation route map"
        data-testid="map"
      >
        <BasemapTileLayer />
        <MapViewportFix />
        <FitOverview
          townships={townships}
          depots={depots}
          routes={routes}
          focusTownshipId={focusTownshipId}
        />
        <Pane name="allocation-routes" style={{ zIndex: 450 }}>
          {routes.map((route) => {
            const township =
              townships.find((item) => item.id === route.id) ??
              townships.find((item) => item.name.trim().toLowerCase() === route.label.trim().toLowerCase());
            const path =
              township && route.path.length > 1
                ? routePathForTownship(route, township)
                : route.path;
            if (path.length < 2) return null;
            return (
              <Polyline
                key={`route-${route.id}`}
                positions={path.map((point) => [point.latitude, point.longitude] as [number, number])}
                pathOptions={{
                  color: ROUTE_COLORS[route.depotRegion],
                  weight: route.emphasized ? 5 : route.dimmed ? 2 : 2.5,
                  opacity: route.emphasized ? 0.95 : route.dimmed ? 0.5 : 0.85,
                  dashArray: route.dimmed ? "10 8" : undefined,
                }}
              />
            );
          })}
        </Pane>
        <Pane name="township-pins" style={{ zIndex: 520 }}>
          {townships.map((township) => {
            const selected = township.id === focusTownshipId;
            const route = routeById.get(township.id) ?? routeByName.get(township.name.trim().toLowerCase());
            return (
              <CircleMarker
                key={`pin-${township.id}`}
                center={[township.latitude, township.longitude]}
                radius={selected ? 8 : 6}
                pathOptions={{
                  color: selected ? "#ffffff" : "#0b5873",
                  fillColor: selected ? "#2f6fed" : "#ffffff",
                  fillOpacity: 0.95,
                  weight: selected ? 3 : 2,
                }}
                eventHandlers={onSelectTownship ? { click: () => onSelectTownship(township.id) } : undefined}
              >
                {route && route.emphasized ? (
                  <Tooltip
                    permanent
                    direction="top"
                    offset={[0, -6]}
                    className="allocation-distance-tip"
                  >
                    {formatDistance(route.distanceM)}
                  </Tooltip>
                ) : null}
                <Popup>
                  <strong>{township.name}</strong>
                  {route ? (
                    <>
                      <br />
                      {route.depotRegion === "east" ? "Bago depot (east)" : "Pyay depot (west)"}
                      <br />
                      Road {formatDistance(route.distanceM)}
                    </>
                  ) : null}
                </Popup>
              </CircleMarker>
            );
          })}
        </Pane>
        <Pane name="depot-pins" style={{ zIndex: 540 }}>
          {depots.map((depot) => {
            const style = DEPOT_STYLE[depot.region];
            return (
              <CircleMarker
                key={depot.id}
                center={[depot.latitude, depot.longitude]}
                radius={11}
                pathOptions={{ color: style.color, fillColor: style.fillColor, fillOpacity: 0.95, weight: 3 }}
              >
                <Popup>
                  <strong>{depot.name}</strong>
                  <br />
                  Inventory base
                </Popup>
              </CircleMarker>
            );
          })}
        </Pane>
      </MapContainer>
    </div>
  );
}
