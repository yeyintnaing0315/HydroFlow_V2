import { useEffect } from "react";
import { useMap } from "react-leaflet";

export default function MapViewportFix() {
  const map = useMap();
  useEffect(() => {
    if (typeof map.getContainer !== "function") return;
    const container = map.getContainer();
    const fix = () => {
      try {
        const size = map.getSize();
        const box = container.getBoundingClientRect();
        if (Math.abs(size.x - box.width) > 2 || Math.abs(size.y - box.height) > 2) {
          map.invalidateSize();
        }
      } catch {
        // Leaflet can throw if the map is torn down during a reload.
      }
    };
    const frame = requestAnimationFrame(fix);
    if (typeof ResizeObserver === "undefined") {
      return () => cancelAnimationFrame(frame);
    }
    const observer = new ResizeObserver(fix);
    observer.observe(container);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, [map]);
  return null;
}
