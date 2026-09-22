// Cliente HTTP hacia el backend (ver backend/README.md). La URL se puede
// cambiar sin tocar código con la variable de entorno VITE_API_BASE_URL
// (archivo .env en la raíz del repo, o configurada en el hosting donde se
// publique el build de producción).
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

async function extraerMensajeError(respuesta) {
  try {
    const datos = await respuesta.json();
    if (datos && typeof datos.detail === "string") return datos.detail;
  } catch {
    // sin cuerpo JSON legible
  }
  return `Ocurrió un error inesperado (código ${respuesta.status}).`;
}

export async function obtenerPotreros() {
  const respuesta = await fetch(`${API_BASE_URL}/api/potreros`);
  if (!respuesta.ok) throw new Error(await extraerMensajeError(respuesta));
  return respuesta.json();
}

export async function dispararPrediccion() {
  const respuesta = await fetch(`${API_BASE_URL}/api/predecir`, { method: "POST" });
  if (!respuesta.ok) throw new Error(await extraerMensajeError(respuesta));
  return respuesta.json();
}

export async function guardarGeojson(geojson) {
  const respuesta = await fetch(`${API_BASE_URL}/api/geojson`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(geojson),
  });
  if (!respuesta.ok) throw new Error(await extraerMensajeError(respuesta));
  return respuesta.json();
}

export async function eliminarPotrero(nombrePotrero) {
  const respuesta = await fetch(`${API_BASE_URL}/api/potreros/${encodeURIComponent(nombrePotrero)}`, {
    method: "DELETE",
  });
  if (!respuesta.ok) throw new Error(await extraerMensajeError(respuesta));
  return respuesta.json();
}

export async function registrarAforo(nombrePotrero, cuerpo) {
  const respuesta = await fetch(`${API_BASE_URL}/api/potreros/${encodeURIComponent(nombrePotrero)}/aforo`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(cuerpo),
  });
  if (!respuesta.ok) throw new Error(await extraerMensajeError(respuesta));
  return respuesta.json();
}
