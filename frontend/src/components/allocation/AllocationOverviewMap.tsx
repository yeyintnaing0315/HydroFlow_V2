import { useEffect } from "react";
import { CircleMarker, MapContainer, Pane, Polyline, Popup, Tooltip, useMap } from "react-leaflet";
import BasemapTileLayer from "../map/BasemapTileLayer";
import MapViewportFix from "../map/MapViewportFix";
import { formatMeters } from "./routeFormat";
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
}

interface AllocationOverviewMapProps {
  townships: OverviewTownship[];
  depots: OverviewDepot[];
  routes: OverviewRoute[];
  focusTownshipId?: string | null;
  onSelectTownship?: (townshipId: string) => void;
  /** Separate Leaflet instances (dashboard vs print) must not mount at the same time. */
  instanceKey?: string;
}

const ROUTE_COLORS = { east: "#0b5873", west: "#c45a1a" } as const;
const DEPOT_STYLE = {
  east: { color: "#17324a", fillColor: "#f4b942" },
  west: { color: "#4a1730", fillColor: "#e07a2f" },
} as const;

function FitOverview({
  townships,
  depots,
  routes,
}: {
  townships: OverviewTownship[];
  depots: OverviewDepot[];
  routes: OverviewRoute[];
}) {
  const map = useMap();
  useEffect(() => {
    if (typeof map.getContainer !== "function") return;
    const points: [number, number][] = [
      ...townships.map((township) => [township.latitude, township.longitude] as [number, number]),
      ...depots.map((depot) => [depot.latitude, depot.longitude] as [number, number]),
    ];
    for (const route of routes) {
      for (const point of route.path) points.push([point.latitude, point.longitude]);
    }
    if (points.length === 0) return;
    const fit = () => {
      try {
        map.invalidateSize();
        if (points.length === 1) map.setView(points[0], 8);
        else map.fitBounds(points, { padding: [24, 24], maxZoom: 9 });
      } catch {
        // Leaflet can throw if the map is torn down during a reload.
      }
    };
    const frame = requestAnimationFrame(fit);
    return () => cancelAnimationFrame(frame);
  }, [map, townships, depots, routes]);
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
  instanceKey = "allocation-overview-map",
}: AllocationOverviewMapProps) {
  const routeById = new Map(routes.map((route) => [route.id, route]));
  const routeByName = new Map(routes.map((route) => [route.label.trim().toLowerCase(), route]));

  return (
    <div className="allocation-map-frame">
      <MapContainer
        key={instanceKey}
        center={[18.26, 96.07]}
        zoom={8}
        scrollWheelZoom={false}
        className="allocation-map"
        aria-label="Allocation route map"
      >
        <BasemapTileLayer />
        <MapViewportFix />
        <FitOverview townships={townships} depots={depots} routes={routes} />
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
                  weight: route.emphasized ? 5 : 2.5,
                  opacity: route.emphasized ? 0.95 : 0.85,
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
                    {formatMeters(route.distanceM)}
                  </Tooltip>
                ) : null}
                <Popup>
                  <strong>{township.name}</strong>
                  {route ? (
                    <>
                      <br />
                      {route.depotRegion === "east" ? "Bago depot (east)" : "Pyay depot (west)"}
                      <br />
                      Road {formatMeters(route.distanceM)}
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
