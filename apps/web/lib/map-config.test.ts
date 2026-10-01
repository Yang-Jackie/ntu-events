import { describe, expect, it } from "vitest";

import { basemapProvider, basemapStyle } from "./map-config";

describe("basemap configuration", () => {
  it("defaults unknown and absent values to OpenFreeMap", () => {
    expect(basemapProvider(undefined)).toBe("openfreemap");
    expect(basemapProvider("unexpected")).toBe("openfreemap");
  });

  it("builds an attributed OpenStreetMap Standard raster style", () => {
    const style = basemapStyle(basemapProvider("openstreetmap"));

    expect(style).toMatchObject({
      version: 8,
      sources: {
        "openstreetmap-standard": {
          type: "raster",
          tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
          attribution: expect.stringContaining("OpenStreetMap contributors"),
        },
      },
    });
  });

  it("keeps OpenFreeMap as the default vector style", () => {
    expect(basemapStyle("openfreemap")).toContain(
      "tiles.openfreemap.org/styles/liberty",
    );
  });
});
