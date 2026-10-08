// "2026-09-22" (solo fecha) se parsea como UTC medianoche con new Date(), que
// en Colombia (UTC-5) se mostraba como el 21. Se arma en hora local.
function aFechaLocal(iso) {
  const soloFecha = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(iso).trim());
  if (soloFecha) return new Date(Number(soloFecha[1]), Number(soloFecha[2]) - 1, Number(soloFecha[3]));
  return new Date(iso);
}

export function formatearFecha(iso) {
  if (!iso) return "Sin dato";
  const fecha = aFechaLocal(iso);
  if (Number.isNaN(fecha.getTime())) return String(iso);
  return fecha.toLocaleDateString("es-CO", { day: "numeric", month: "long", year: "numeric" });
}

// Fecha de hoy (AAAA-MM-DD) en hora local; toISOString() usa UTC y desde las
// 7 pm en Colombia ya devolvia el dia siguiente.
export function hoyISO() {
  const ahora = new Date();
  const mes = String(ahora.getMonth() + 1).padStart(2, "0");
  const dia = String(ahora.getDate()).padStart(2, "0");
  return `${ahora.getFullYear()}-${mes}-${dia}`;
}
