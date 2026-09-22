// Acepta líneas tipo "4.6148, -72.1300" o "4.6148 -72.1300" (lat, lon).
// Ignora líneas vacías o mal formadas.
export function parseBoundaryText(text) {
  const lines = text.split("\n").map((l) => l.trim()).filter(Boolean);
  const points = [];
  for (const line of lines) {
    const parts = line.split(/[,\s]+/).map(Number);
    if (parts.length >= 2 && !Number.isNaN(parts[0]) && !Number.isNaN(parts[1])) {
      points.push([parts[0], parts[1]]); // [lat, lon]
    }
  }
  return points;
}
