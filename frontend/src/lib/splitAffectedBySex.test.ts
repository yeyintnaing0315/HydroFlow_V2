import { describe, expect, it } from "vitest";
import { ensureAffectedSexSplit, splitAffectedBySex } from "./splitAffectedBySex";

describe("splitAffectedBySex", () => {
  it("splits without census using default ratio", () => {
    const split = splitAffectedBySex("Monyo", 1259, undefined);
    expect(split.male + split.female).toBe(1259);
    expect(split.male).toBeGreaterThan(0);
    expect(split.female).toBeGreaterThan(0);
  });

  it("re-splits when stored male and female are both zero", () => {
    const sex = ensureAffectedSexSplit("Monyo", 1259, 0, 0, undefined);
    expect((sex.male ?? 0) + (sex.female ?? 0)).toBe(1259);
  });
});
