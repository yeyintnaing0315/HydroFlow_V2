import type { Geometry } from "geojson";
import mapPoints from "../data/township_map_points.json";
import { geometryCenter } from "./geometryCenter";

type MapPointRow = { name_en: string; latitude: number; longitude: number };

const NAME_ALIASES: Record<string, string> = {
  okpho: "okpo",
  paukkhaung: "paukkaung",
  phyu: "pyu",
};

function nameKey(name: string): string {
  const compact = name.trim().toLowerCase().replace(/[^a-z0-9]/g, "");
  return NAME_ALIASES[compact] ?? compact;
}

const mapLabelByKey = new Map<string, MapPointRow>(
  (mapPoints.townships as MapPointRow[]).map((row) => [nameKey(row.name_en), row]),
);

/** Map pins and OSRM preview legs: town seats (Open Admin), then admin API, then polygon average. */
export function resolveTownshipPosition(
  nameEn: string,
  adminLat: number,
  adminLon: number,
  geometry?: Geometry | null,
): { latitude: number; longitude: number } {
  const label = mapLabelByKey.get(nameKey(nameEn));
  if (label) {
    return { latitude: label.latitude, longitude: label.longitude };
  }
  if (Number.isFinite(adminLat) && Number.isFinite(adminLon)) {
    return { latitude: adminLat, longitude: adminLon };
  }
  const fromGeometry = geometryCenter(geometry ?? undefined);
  if (fromGeometry) return fromGeometry;
  return { latitude: adminLat, longitude: adminLon };
}

/** Inventory depots (discharge / warehouse), not township town seats. */
export function depotReferenceCoords(region: "east" | "west"): { latitude: number; longitude: number } {
  return region === "east"
    ? { latitude: 17.335, longitude: 96.481 }
    : { latitude: 18.817, longitude: 95.217 };
}
