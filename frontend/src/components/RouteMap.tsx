import { useEffect } from "react";
import { CircleMarker, MapContainer, Polyline, Popup, useMap } from "react-leaflet";
import type { Coordinates } from "../types";
import BasemapTileLayer from "./map/BasemapTileLayer";
import MapViewportFix from "./map/MapViewportFix";

export interface MapStop {
  id: string;
  name: string;
  latitude: number;
  longitude: number;
  kind: "depot-east" | "depot-west" | "township" | "risk-township";
}

export interface MapRoutePath {
  path: Coordinates[];
  depotRegion: "east" | "west";
  blocked?: boolean;
  blockedSegments?: Coordinates[][];
  emphasized?: boolean;
  dimmed?: boolean;
}

interface RouteMapProps {
  center: [number, number];
  stops: MapStop[];
  paths: MapRoutePath[];
  focusTownshipId?: string | null;
  onSelectStop?: (townshipId: string) => void;
}

const DEPOT_COLORS = {
  east: { stroke: "#17324a", fill: "#f4b942" },
  west: { stroke: "#4a1730", fill: "#e07a2f" },
} as const;

const ROUTE_COLORS = {
  east: "#0b5873",
  west: "#c45a1a",
} as const;

const HIGH_RISK_RED = "#d64545";

function FitRoute({ stops, paths }: { stops: MapStop[]; paths: MapRoutePath[] }) {
  const map = useMap();
  useEffect(() => {
    const points: [number, number][] = stops.map((stop) => [stop.latitude, stop.longitude]);
    for (const route of paths) {
      for (const point of route.path) {
        points.push([point.latitude, point.longitude]);
      }
    }
    if (points.length === 0) return;
    if (points.length === 1) {
      map.setView(points[0], 8);
      return;
    }
    map.fitBounds(points, { padding: [28, 28] });
  }, [map, stops, paths]);
  return null;
}

function depotStyle(kind: MapStop["kind"]) {
  if (kind === "depot-west") {
    return { ...DEPOT_COLORS.west, radius: 12, weight: 3 };
  }
  if (kind === "depot-east") {
    return { ...DEPOT_COLORS.east, radius: 12, weight: 3 };
  }
  if (kind === "risk-township") {
    return { color: "#d86a1a", fillColor: "#ffe8d6", fillOpacity: 0.95, radius: 7, weight: 2 };
  }
  return { color: "#2f6fed", fillColor: "#ffffff", fillOpacity: 0.95, radius: 8, weight: 2 };
}

export default function RouteMap({ center, stops, paths, focusTownshipId, onSelectStop }: RouteMapProps) {
  return (
    <div className="allocation-map-frame">
      <MapContainer center={center} zoom={8} scrollWheelZoom={false} className="allocation-map">
        <BasemapTileLayer />
        <MapViewportFix />
        <FitRoute stops={stops} paths={paths} />
        {paths.map((route, index) =>
          route.path.length > 1 ? (
            <Polyline
              key={`route-${index}`}
              positions={route.path.map((point) => [point.latitude, point.longitude] as [number, number])}
              pathOptions={{
                color:
                  route.blocked && !(route.blockedSegments && route.blockedSegments.length)
                    ? HIGH_RISK_RED
                    : ROUTE_COLORS[route.depotRegion],
                weight: route.emphasized ? 6 : 3,
                opacity: route.dimmed ? 0.35 : 0.9,
              }}
            />
          ) : null,
        )}
        {paths.map((route, index) =>
          (route.blockedSegments ?? []).map((segment, segmentIndex) =>
            segment.length > 1 ? (
              <Polyline
                key={`blocked-${index}-${segmentIndex}`}
                positions={segment.map((point) => [point.latitude, point.longitude] as [number, number])}
                pathOptions={{ color: HIGH_RISK_RED, weight: 5, opacity: 0.95 }}
              />
            ) : null,
          ),
        )}
        {stops.map((stop) => {
          const style = depotStyle(stop.kind);
          const focused = focusTownshipId != null && stop.id === focusTownshipId;
          const radius = focused ? (style.radius ?? 8) + 4 : style.radius;
          const selectable = stop.kind === "township" || stop.kind === "risk-township";
          return (
            <CircleMarker
              key={stop.id}
              center={[stop.latitude, stop.longitude]}
              radius={radius}
              pathOptions={{
                color: style.color ?? style.stroke,
                fillColor: style.fillColor ?? style.fill,
                fillOpacity: style.fillOpacity ?? 0.95,
                weight: style.weight,
              }}
              eventHandlers={
                selectable && onSelectStop
                  ? { click: () => onSelectStop(stop.id) }
                  : undefined
              }
            >
              <Popup>
                <strong>{stop.name}</strong>
                <br />
                {stop.kind === "township" ? "Delivery stop" : "Depot"}
              </Popup>
            </CircleMarker>
          );
        })}
      </MapContainer>
    </div>
  );
}
