import { describe, expect, it } from "vitest";
import { resolveHighSevereAffectedPeople, syntheticAffectedPeople } from "./syntheticAffectedEstimate";

describe("syntheticAffectedEstimate", () => {
  it("returns stable counts between 100 and 10,000", () => {
    const a = syntheticAffectedPeople("MMR007001701", "2024-09-11");
    const b = syntheticAffectedPeople("MMR007001701", "2024-09-11");
    expect(a).toBe(b);
    expect(a).toBeGreaterThanOrEqual(100);
    expect(a).toBeLessThanOrEqual(10_000);
  });

  it("uses API value when positive", () => {
    expect(resolveHighSevereAffectedPeople("t1", "2024-09-11", 1525, "severe")).toBe(1525);
  });

  it("falls back for high/severe when API is zero", () => {
    const value = resolveHighSevereAffectedPeople("t1", "2024-09-11", 0, "high");
    expect(value).toBeGreaterThanOrEqual(100);
    expect(value).toBeLessThanOrEqual(10_000);
  });
});
