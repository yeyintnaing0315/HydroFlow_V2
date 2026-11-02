import type { Geometry } from "geojson";
import bago28 from "../data/bago28_locations.json";
import { geometryCenter } from "./geometryCenter";

type Bago28Row = {
  township: string;
  township_id: string;
  latitude: number;
  longitude: number;
  discharge_latitude: number;
  discharge_longitude: number;
};

const bago28ByName = new Map<string, Bago28Row>(
  (bago28 as Bago28Row[]).map((row) => [row.township.trim().toLowerCase(), row]),
);

/** Pin and OSRM legs share one point: official bago28, then polygon centroid, then admin. */
export function resolveTownshipPosition(
  nameEn: string,
  adminLat: number,
  adminLon: number,
  geometry?: Geometry | null,
): { latitude: number; longitude: number } {
  const reference = bago28ByName.get(nameEn.trim().toLowerCase());
  if (reference) {
    return { latitude: reference.latitude, longitude: reference.longitude };
  }
  const fromGeometry = geometryCenter(geometry ?? undefined);
  if (fromGeometry) return fromGeometry;
  return { latitude: adminLat, longitude: adminLon };
}

export function depotReferenceCoords(region: "east" | "west"): { latitude: number; longitude: number } {
  const name = region === "east" ? "bago" : "pyay";
  const row = (bago28 as Bago28Row[]).find((item) => item.township_id === name);
  if (!row) {
    return region === "east"
      ? { latitude: 17.335, longitude: 96.481 }
      : { latitude: 18.817, longitude: 95.217 };
  }
  return { latitude: row.discharge_latitude, longitude: row.discharge_longitude };
}
