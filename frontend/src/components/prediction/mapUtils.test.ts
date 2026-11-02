import { describe, expect, it } from "vitest";
import { displayRiskLevel, floodFillLevel } from "./mapUtils";

describe("displayRiskLevel", () => {
  it("uses the primary model band for the selected day", () => {
    expect(
      floodFillLevel({
        probability_risk_level: "low",
        horizon_3d: 0.35,
        early_warning: true,
        warning_level: "high",
      }),
    ).toBe("low");
  });

  it("maps very_high risk_band to severe", () => {
    expect(displayRiskLevel({ risk_band: "very_high", probability_risk_level: null })).toBe("severe");
  });
});
