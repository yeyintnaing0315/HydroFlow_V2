import { describe, expect, it } from "vitest";
import { aggregateInventoryStats } from "./inventoryStats";
import type { InventorySnapshot } from "../types";

describe("aggregateInventoryStats", () => {
  it("merges class quantities across depot snapshots", () => {
    const east: InventorySnapshot = {
      region: "east",
      location: "Bago East",
      classes: [
        {
          code: "foods",
          name: "Food",
          entry_mode: "scan_or_manual",
          quantity: 4000,
          items: [
            { code: "rice", name: "Rice", quantity: 0, unit: "kg", capacity: 5000 },
            { code: "water", name: "Clean Water", quantity: 4000, unit: "L", capacity: 5000 },
          ],
        },
      ],
      movements: [],
    };
    const west: InventorySnapshot = {
      region: "west",
      location: "Bago West",
      classes: [
        {
          code: "utilities",
          name: "Utilities",
          entry_mode: "scan_or_manual",
          quantity: 1000,
          items: [{ code: "jackets", name: "Life Jackets", quantity: 1000, unit: "pcs", capacity: 5000 }],
        },
      ],
      movements: [],
    };

    const stats = aggregateInventoryStats([east, west]);
    expect(stats.totalQuantity).toBe(5000);
    expect(stats.classes).toHaveLength(2);
    expect(stats.classes.find((row) => row.code === "foods")?.quantity).toBe(4000);
    expect(stats.classes.find((row) => row.code === "utilities")?.quantity).toBe(1000);
  });
});
