import { useState } from "react";

export default function PotreroTable({ potreros, onDelete }) {
  const [confirmando, setConfirmando] = useState(null); // indice de la fila a confirmar, o null

  if (potreros.length === 0) {
    return <p className="empty">Todavía no has cerrado ningún potrero.</p>;
  }

  return (
    <table>
      <thead>
        <tr>
          <th></th>
          <th>Nombre</th>
          <th>Vértices</th>
          <th>Área aprox. (ha)</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {potreros.map((p, i) => (
          <tr key={i}>
            <td>
              <span className="swatch" style={{ background: p.color }} />
            </td>
            <td>{p.name}</td>
            <td>{p.pointsXY.length}</td>
            <td>{p.areaHa.toFixed(2)}</td>
            <td>
              {confirmando === i ? (
                <span className="confirmar-borrado">
                  <button
                    type="button"
                    onClick={() => {
                      setConfirmando(null);
                      onDelete(i);
                    }}
                  >
                    Sí
                  </button>
                  <button type="button" onClick={() => setConfirmando(null)}>
                    No
                  </button>
                </span>
              ) : (
                <button type="button" onClick={() => setConfirmando(i)}>
                  Eliminar
                </button>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
