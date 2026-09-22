// Iconos simples en SVG (sin librería externa) para que cada estado del
// semáforo se reconozca por forma además de por color.

export function IconoEstado({ estado }) {
  const comunes = { width: 18, height: 18, viewBox: "0 0 20 20", fill: "none", "aria-hidden": true, className: "icono-estado" };

  if (estado === "verde") {
    return (
      <svg {...comunes}>
        <circle cx="10" cy="10" r="8" stroke="currentColor" strokeWidth="1.6" />
        <path d="M6.5 10.3l2.3 2.3 4.7-5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }
  if (estado === "ambar") {
    return (
      <svg {...comunes}>
        <path d="M10 3.5l7.5 13h-15z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
        <line x1="10" y1="8.3" x2="10" y2="12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        <circle cx="10" cy="14.3" r="0.9" fill="currentColor" />
      </svg>
    );
  }
  if (estado === "rojo") {
    return (
      <svg {...comunes}>
        <circle cx="10" cy="10" r="8" stroke="currentColor" strokeWidth="1.6" />
        <path d="M7 7l6 6M13 7l-6 6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
    );
  }
  return (
    <svg {...comunes}>
      <circle cx="10" cy="10" r="8" stroke="currentColor" strokeWidth="1.6" />
      <line x1="6.5" y1="10" x2="13.5" y2="10" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}
