/** Match backend demo_affected.demo_affected_people for display. */
export function demoAffectedPeople(townshipId: string, date: string, raw: number): number {
  if (raw <= 0) return 0;
  const key = `${townshipId}:${date}`;
  let seed = 0;
  for (let index = 0; index < key.length; index += 1) {
    seed += key.charCodeAt(index);
  }
  if (seed % 10 < 3) {
    return 10 + (seed % 91);
  }
  return (1 + (seed % 9)) * 100;
}
