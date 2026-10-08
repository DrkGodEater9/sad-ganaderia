// Acepta líneas tipo "4.6148, -72.1300" o "4.6148 -72.1300" (lat, lon).
// Ignora líneas vacías, mal formadas o con coordenadas fuera de rango.
export function esCoordenadaValida(lat, lon) {
  return Number.isFinite(lat) && Number.isFinite(lon) && Math.abs(lat) <= 90 && Math.abs(lon) <= 180;
}

export function parseBoundaryText(text) {
  const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  const points = [];
  for (const line of lines) {
    const parts = line.split(/[,\s]+/).filter(Boolean).map(Number);
    if (parts.length >= 2 && esCoordenadaValida(parts[0], parts[1])) {
      points.push([parts[0], parts[1]]); // [lat, lon]
    }
  }
  return points;
}
