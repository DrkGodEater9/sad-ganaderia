// Convierte el contenido de un archivo KML o GeoJSON en una lista de
// puntos [lat, lon], para que el usuario pueda subir el contorno de
// CUALQUIER finca en lugar de escribirlo a mano.

function parseKML(text) {
  const match = text.match(/<coordinates>([\s\S]*?)<\/coordinates>/i);
  if (!match) return [];
  const tokens = match[1].trim().split(/\s+/);
  const points = [];
  for (const t of tokens) {
    const parts = t.split(",").map(Number);
    if (parts.length >= 2 && !Number.isNaN(parts[0]) && !Number.isNaN(parts[1])) {
      // KML guarda lon,lat,alt -> lo pasamos a [lat, lon]
      points.push([parts[1], parts[0]]);
    }
  }
  return points;
}

function ringToLatLon(ring) {
  // GeoJSON guarda [lon, lat] -> lo pasamos a [lat, lon]
  return ring.map(([lon, lat]) => [lat, lon]);
}

function parseGeoJSON(text) {
  let obj;
  try {
    obj = JSON.parse(text);
  } catch {
    return [];
  }
  function firstPolygonRing(node) {
    if (!node) return null;
    if (node.type === "FeatureCollection") {
      for (const f of node.features || []) {
        const r = firstPolygonRing(f);
        if (r) return r;
      }
      return null;
    }
    if (node.type === "Feature") return firstPolygonRing(node.geometry);
    if (node.type === "Polygon") return node.coordinates[0];
    if (node.type === "MultiPolygon") return node.coordinates[0][0];
    return null;
  }
  const ring = firstPolygonRing(obj);
  return ring ? ringToLatLon(ring) : [];
}

// Detecta el formato por el contenido (no solo por la extensión, para ser
// más tolerante) y devuelve los puntos como texto "lat, lon" por línea,
// listo para mostrar en el textarea de contorno.
export function parseBoundaryFile(text) {
  const trimmed = text.trim();
  const points = trimmed.startsWith("<") ? parseKML(trimmed) : parseGeoJSON(trimmed);
  return points.map(([lat, lon]) => `${lat}, ${lon}`).join("\n");
}
