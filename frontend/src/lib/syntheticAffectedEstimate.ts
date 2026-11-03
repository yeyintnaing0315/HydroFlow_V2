import { needsResourceAllocation } from "./allocationFocus";
import type { RiskLevel } from "../types";

/** Stable pseudo-random affected count in [100, 5000] for demo when API returns zero. */
export function syntheticAffectedPeople(townshipId: string, planningDate: string): number {
  let hash = 2166136261;
  const key = `${townshipId}:${planningDate}`;
  for (let i = 0; i < key.length; i += 1) {
    hash ^= key.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return 100 + (hash >>> 0) % 4901;
}

export function resolveHighSevereAffectedPeople(
  townshipId: string,
  planningDate: string,
  fromApi: number | null | undefined,
  riskLevel: RiskLevel | "unknown" | null | undefined,
): number | null {
  if (!needsResourceAllocation(riskLevel)) {
    return fromApi != null && fromApi > 0 ? fromApi : null;
  }
  if (fromApi != null && fromApi > 0) {
    return fromApi;
  }
  return syntheticAffectedPeople(townshipId, planningDate);
}
