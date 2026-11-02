export type DepotRegion = "east" | "west";

const DEPOT_LONGITUDE_SPLIT = 96.0;
const DEPOT_BOUNDARY_MARGIN = 0.08;

/** Match backend allocation depot split (east → Bago, west → Pyay). */
export function depotRegionForCoordinates(latitude: number, longitude: number): DepotRegion {
  if (longitude >= DEPOT_LONGITUDE_SPLIT + DEPOT_BOUNDARY_MARGIN) {
    return "east";
  }
  if (longitude <= DEPOT_LONGITUDE_SPLIT - DEPOT_BOUNDARY_MARGIN) {
    return "west";
  }
  const eastDist =
    (latitude - 17.335) * (latitude - 17.335) + (longitude - 96.481) * (longitude - 96.481);
  const westDist =
    (latitude - 18.817) * (latitude - 18.817) + (longitude - 95.217) * (longitude - 95.217);
  return eastDist <= westDist ? "east" : "west";
}
