export function routeMethodLabel(method: string | undefined): string {
  if (method === "osrm_road") return "OSRM road route";
  if (method === "flood_aware_blocked") return "Flood-aware path (high-risk corridor blocked)";
  if (method === "flood_aware_graph") return "Flood-aware graph path";
  if (method === "straight_line_fallback") return "Straight-line fallback (OSRM unavailable)";
  return method ? method : "Route unavailable";
}

export function formatDistance(meters: number | null | undefined): string {
  if (meters == null || Number.isNaN(meters)) return "—";
  return `${(meters / 1000).toFixed(1)} km`;
}

export function formatMeters(meters: number | null | undefined): string {
  if (meters == null || Number.isNaN(meters)) return "—";
  return `${Math.round(meters).toLocaleString()} m`;
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || Number.isNaN(seconds)) return "—";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  return `${hours} h ${minutes % 60} min`;
}

export function floodExposureLabel(exposure: string | undefined): string {
  if (exposure === "clear") return "Clear of flooded townships";
  if (exposure === "penalized") return "Passes near a flooded township";
  if (exposure === "blocked") return "Crosses a flooded township";
  return "Flood exposure unknown";
}

export function formatMeasure(value: number | null | undefined, digits = 1): string {
  if (value == null || Number.isNaN(value)) return "—";
  return value.toLocaleString(undefined, { maximumFractionDigits: digits });
}
