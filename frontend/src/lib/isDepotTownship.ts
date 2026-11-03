const DEPOT_TOWNSHIP_NAMES = new Set(["bago", "pyay"]);

export function isDepotTownship(name: string): boolean {
  return DEPOT_TOWNSHIP_NAMES.has(name.trim().toLowerCase());
}
