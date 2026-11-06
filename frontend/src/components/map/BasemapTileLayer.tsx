import { TileLayer } from "react-leaflet";

/**
 * tile.openstreetmap.org does not respond on this network, so the map stays a
 * blank panel under the township colors. FOSSGIS serves the same OSM tiles.
 */
export const BASEMAP_TILE_URL = "https://tile.openstreetmap.de/{z}/{x}/{y}.png";

export const BASEMAP_ATTRIBUTION = "© OpenStreetMap contributors";

export default function BasemapTileLayer() {
  return <TileLayer attribution={BASEMAP_ATTRIBUTION} url={BASEMAP_TILE_URL} maxZoom={19} />;
}
