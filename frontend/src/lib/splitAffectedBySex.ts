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
  if (!profile) return { total, male: 0, female: 0 };
  const maleBase = profile.population.male;
  const femaleBase = profile.population.female;
  const base = maleBase + femaleBase;
  if (base <= 0) return { total, male: 0, female: 0 };
  const male = Math.round((total * maleBase) / base);
  const female = Math.max(0, total - male);
  return { total, male, female };
}
