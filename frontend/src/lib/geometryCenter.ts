import type { Geometry } from "geojson";

/** Average of polygon vertices (same approach as backend open_admin_areas). */
export function geometryCenter(geometry: Geometry | null | undefined): { latitude: number; longitude: number } | null {
  if (!geometry || !("coordinates" in geometry)) return null;
  const points: [number, number][] = [];

  const collect = (value: unknown): void => {
    if (
      Array.isArray(value) &&
      value.length >= 2 &&
      typeof value[0] === "number" &&
      typeof value[1] === "number"
    ) {
      points.push([value[0], value[1]]);
      return;
    }
    if (Array.isArray(value)) {
      for (const item of value) collect(item);
    }
  };

  collect(geometry.coordinates);
  if (!points.length) return null;
  const longitude = points.reduce((sum, point) => sum + point[0], 0) / points.length;
  const latitude = points.reduce((sum, point) => sum + point[1], 0) / points.length;
  return { latitude, longitude };
}
