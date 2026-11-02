import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "./api";

describe("API client", () => {
  afterEach(() => vi.restoreAllMocks());

  it("posts the location and start date without manual weather values", async () => {
    const input = {
      date: "2026-10-01",
      township_id: "bago",
      latitude: 17.336,
      longitude: 96.481,
    };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(
      async () =>
        new Response(JSON.stringify({
          township_id: "bago",
          source: "Open-Meteo rainfall and GloFAS discharge",
          model_version: "test",
          days: [],
        }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
    );

    await expect(api.outlook(input)).resolves.toMatchObject({ township_id: "bago", days: [] });
    await expect(api.help(input)).resolves.toMatchObject({ township_id: "bago", days: [] });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/help",
      expect.objectContaining({ method: "POST", body: JSON.stringify(input) }),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/outlook",
      expect.objectContaining({ method: "POST", body: JSON.stringify(input) }),
    );
  });

  it("turns a backend detail into a typed API error", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "Model unavailable" }), {
        status: 503,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await expect(api.health()).rejects.toEqual(
      expect.objectContaining({ message: "Model unavailable", status: 503 }),
    );
  });
});
