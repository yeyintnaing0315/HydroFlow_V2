export function splitAffectedBySex(
  affectedTotal: number,
  male: number,
  female: number,
): { total: number; male: number; female: number } {
  const total = Math.max(0, Math.round(affectedTotal));
  const base = male + female;
  if (total === 0 || base <= 0) {
    return { total: 0, male: 0, female: 0 };
  }
  const maleShare = male / base;
  const maleCount = Math.round(total * maleShare);
  return {
    total,
    male: maleCount,
    female: Math.max(0, total - maleCount),
  };
}
