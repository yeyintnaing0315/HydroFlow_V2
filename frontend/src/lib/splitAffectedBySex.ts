import type { CensusResponse } from "../types";

function normalizeName(value: string): string {
  return value.trim().toLowerCase();
}

function townshipFromCensus(townshipNameEn: string, census: CensusResponse | undefined) {
  if (!census) return undefined;
  const needle = normalizeName(townshipNameEn);
  for (const district of census.districts) {
    for (const township of district.townships) {
      if (normalizeName(township.name_en) === needle) return township;
    }
  }
  return undefined;
}

/** Split an affected total using 2024 census sex ratios for the township. */
export function splitAffectedBySex(
  townshipNameEn: string,
  affectedTotal: number,
  census: CensusResponse | undefined,
): { total: number; male: number; female: number } {
  const total = Math.max(0, Math.round(affectedTotal));
  if (total <= 0) return { total: 0, male: 0, female: 0 };
  const profile = townshipFromCensus(townshipNameEn, census);
  if (!profile) {
    const male = Math.round(total * 0.48);
    return { total, male, female: Math.max(0, total - male) };
  }
  const maleBase = profile.population.male;
  const femaleBase = profile.population.female;
  const base = maleBase + femaleBase;
  if (base <= 0) {
    const male = Math.round(total * 0.48);
    return { total, male, female: Math.max(0, total - male) };
  }
  const male = Math.round((total * maleBase) / base);
  const female = Math.max(0, total - male);
  return { total, male, female };
}

/** Use API/census split when present; otherwise derive male/female from the affected total. */
export function ensureAffectedSexSplit(
  townshipNameEn: string,
  affectedTotal: number | null | undefined,
  male: number | null | undefined,
  female: number | null | undefined,
  census: CensusResponse | undefined,
): { male: number | null; female: number | null } {
  if (affectedTotal == null || affectedTotal <= 0) {
    return { male: null, female: null };
  }
  const hasExplicit =
    male != null &&
    female != null &&
    (male > 0 || female > 0 || male + female === affectedTotal);
  if (hasExplicit) {
    return { male, female };
  }
  const split = splitAffectedBySex(townshipNameEn, affectedTotal, census);
  return { male: split.male, female: split.female };
}
