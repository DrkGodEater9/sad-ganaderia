export function formatearFecha(iso) {
  if (!iso) return "Sin dato";
  try {
    return new Date(iso).toLocaleDateString("es-CO", { day: "numeric", month: "long", year: "numeric" });
  } catch {
    return iso;
  }
}
