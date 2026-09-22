// Proyección local equirectangular: válida para áreas del tamaño de una finca
// (unos pocos kilómetros), sin depender de ningún sistema de coordenadas
// específico de un país. Todo se ancla al primer punto que el usuario ingresa
// como referencia (refLat, refLon).

const METERS_PER_DEG_LAT = 110540; // aprox., varía muy poco con la latitud
const metersPerDegLon = (lat) => 111320 * Math.cos((lat * Math.PI) / 180);

export function latLonToLocalXY([lat, lon], ref) {
  const x = (lon - ref.lon) * metersPerDegLon(ref.lat);
  const y = (lat - ref.lat) * METERS_PER_DEG_LAT;
  return [x, y]; // metros, X=este, Y=norte
}

export function localXYToLatLon([x, y], ref) {
  const lon = ref.lon + x / metersPerDegLon(ref.lat);
  const lat = ref.lat + y / METERS_PER_DEG_LAT;
  return [lat, lon];
}

// Área de un polígono simple (shoelace), recibe puntos en metros locales.
export function areaHectares(pointsXY) {
  const n = pointsXY.length;
  if (n < 3) return 0;
  let s = 0;
  for (let i = 0; i < n; i++) {
    const [x1, y1] = pointsXY[i];
    const [x2, y2] = pointsXY[(i + 1) % n];
    s += x1 * y2 - x2 * y1;
  }
  return Math.abs(s) / 2 / 10000;
}

// Bounding box de un conjunto de polígonos (en metros locales), con margen.
export function boundingBox(polygons, paddingRatio = 0.08) {
  const allPts = polygons.flat();
  if (allPts.length === 0) return { xmin: -100, xmax: 100, ymin: -100, ymax: 100 };
  const xs = allPts.map((p) => p[0]);
  const ys = allPts.map((p) => p[1]);
  let xmin = Math.min(...xs), xmax = Math.max(...xs);
  let ymin = Math.min(...ys), ymax = Math.max(...ys);
  const w = xmax - xmin || 100;
  const h = ymax - ymin || 100;
  const size = Math.max(w, h);
  const pad = size * paddingRatio;
  const cx = (xmin + xmax) / 2, cy = (ymin + ymax) / 2;
  const half = size / 2 + pad;
  return { xmin: cx - half, xmax: cx + half, ymin: cy - half, ymax: cy + half };
}
