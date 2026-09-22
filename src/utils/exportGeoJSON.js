import { localXYToLatLon } from "./geo.js";

// Construye un FeatureCollection GeoJSON estándar (abrible en QGIS, Google Earth,
// Google Earth Engine, geojson.io, etc.) a partir de los potreros dibujados
// (que se guardan internamente en metros locales) y el punto de referencia
// usado para la proyección.
export function buildGeoJSON(potreros, ref) {
  return {
    type: "FeatureCollection",
    properties: {
      generado_por: "SAD",
      referencia_lat: ref.lat,
      referencia_lon: ref.lon,
      nota: "Coordenadas reconstruidas por proyección local equirectangular anclada al punto de referencia.",
    },
    features: potreros.map((p) => ({
      type: "Feature",
      properties: { nombre: p.name, area_ha: p.areaHa },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            ...p.pointsXY.map((pt) => {
              const [lat, lon] = localXYToLatLon(pt, ref);
              return [lon, lat]; // GeoJSON usa [lon, lat]
            }),
            (() => {
              const [lat, lon] = localXYToLatLon(p.pointsXY[0], ref);
              return [lon, lat];
            })(),
          ],
        ],
      },
    })),
  };
}

export function downloadJSON(obj, filename) {
  const blob = new Blob([JSON.stringify(obj, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
