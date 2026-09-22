import { useEffect, useState } from "react";
import {
  obtenerPotreros,
  registrarAforo,
  obtenerHistorialAforo,
  editarAforo,
  borrarAforo,
} from "../utils/api.js";
import { formatearFecha } from "../utils/formato.js";

function hoyISO() {
  return new Date().toISOString().slice(0, 10);
}

export default function RegistrarMedicion() {
  const [potreros, setPotreros] = useState([]);
  const [cargandoPotreros, setCargandoPotreros] = useState(true);
  const [errorPotreros, setErrorPotreros] = useState(null);

  const [potrero, setPotrero] = useState("");
  const [fecha, setFecha] = useState(hoyISO);
  const [altura1, setAltura1] = useState("");
  const [altura2, setAltura2] = useState("");
  const [altura3, setAltura3] = useState("");
  const [mensaje, setMensaje] = useState(null); // { tipo: "ok"|"error"|"cargando", texto }
  const [guardando, setGuardando] = useState(false);
  const [editandoId, setEditandoId] = useState(null);

  const [historial, setHistorial] = useState(null); // null mientras carga
  const [errorHistorial, setErrorHistorial] = useState(null);
  const [confirmandoBorrado, setConfirmandoBorrado] = useState(null);
  const [borrandoId, setBorrandoId] = useState(null);

  function cargarPotreros() {
    setCargandoPotreros(true);
    setErrorPotreros(null);
    obtenerPotreros()
      .then((datos) => setPotreros(datos.potreros || []))
      .catch((err) => setErrorPotreros(err.message))
      .finally(() => setCargandoPotreros(false));
  }

  function cargarHistorial() {
    setErrorHistorial(null);
    obtenerHistorialAforo()
      .then((datos) => setHistorial(datos.aforo || []))
      .catch((err) => setErrorHistorial(err.message));
  }

  useEffect(() => {
    let activo = true;
    obtenerPotreros()
      .then((datos) => {
        if (activo) setPotreros(datos.potreros || []);
      })
      .catch((err) => {
        if (activo) setErrorPotreros(err.message);
      })
      .finally(() => {
        if (activo) setCargandoPotreros(false);
      });
    return () => {
      activo = false;
    };
  }, []);

  useEffect(() => {
    let activo = true;
    obtenerHistorialAforo()
      .then((datos) => {
        if (activo) setHistorial(datos.aforo || []);
      })
      .catch((err) => {
        if (activo) setErrorHistorial(err.message);
      });
    return () => {
      activo = false;
    };
  }, []);

  function limpiarFormulario() {
    setEditandoId(null);
    setPotrero("");
    setFecha(hoyISO());
    setAltura1("");
    setAltura2("");
    setAltura3("");
  }

  function iniciarEdicion(registro) {
    setMensaje(null);
    setEditandoId(registro.id);
    setPotrero(registro.potrero || "");
    setFecha(registro.fecha || hoyISO());
    setAltura1(registro.altura_cm_1 != null ? String(registro.altura_cm_1) : "");
    setAltura2(registro.altura_cm_2 != null ? String(registro.altura_cm_2) : "");
    setAltura3(registro.altura_cm_3 != null ? String(registro.altura_cm_3) : "");
  }

  async function guardar(evento) {
    evento.preventDefault();

    if (!potrero) {
      setMensaje({ tipo: "error", texto: "Elige un potrero antes de guardar." });
      return;
    }

    const medidas = [
      ["la primera medida", altura1],
      ["la segunda medida", altura2],
      ["la tercera medida", altura3],
    ];
    for (const [etiqueta, valorTexto] of medidas) {
      const valor = parseFloat(valorTexto);
      if (Number.isNaN(valor) || valor <= 0 || valor > 200) {
        setMensaje({ tipo: "error", texto: `Revisa ${etiqueta}: debe ser un número entre 0 y 200 cm.` });
        return;
      }
    }

    setGuardando(true);
    setMensaje({ tipo: "cargando", texto: editandoId ? "Guardando cambios…" : "Guardando…" });
    try {
      if (editandoId) {
        await editarAforo(editandoId, {
          potrero,
          fecha,
          altura_cm_1: parseFloat(altura1),
          altura_cm_2: parseFloat(altura2),
          altura_cm_3: parseFloat(altura3),
        });
        setMensaje({ tipo: "ok", texto: "Medición actualizada." });
      } else {
        await registrarAforo(potrero, {
          altura_cm_1: parseFloat(altura1),
          altura_cm_2: parseFloat(altura2),
          altura_cm_3: parseFloat(altura3),
          fecha: fecha || undefined,
        });
        setMensaje({ tipo: "ok", texto: "Medición guardada. Ya puedes registrar el siguiente potrero." });
      }
      limpiarFormulario();
      cargarHistorial();
    } catch (err) {
      setMensaje({ tipo: "error", texto: `No se pudo guardar: ${err.message}` });
    } finally {
      setGuardando(false);
    }
  }

  async function confirmarBorrado(id) {
    setConfirmandoBorrado(null);
    setBorrandoId(id);
    try {
      await borrarAforo(id);
      setHistorial((actual) => (actual || []).filter((registro) => registro.id !== id));
      if (editandoId === id) limpiarFormulario();
    } catch (err) {
      setErrorHistorial(`No se pudo borrar la medición: ${err.message}`);
    } finally {
      setBorrandoId(null);
    }
  }

  return (
    <div className="contenido">
      <h2>{editandoId ? "Editar medición" : "Registrar medición"}</h2>
      <p className="texto-suave">
        {editandoId
          ? "Corrige los datos de esta medición y guarda los cambios."
          : "Elige el potrero y anota las tres medidas de altura del pasto que tomaste en el campo."}
      </p>

      {errorPotreros && (
        <>
          <p className="texto-estado texto-estado-error">
            No se pudo cargar la lista de potreros: {errorPotreros}
          </p>
          <button type="button" className="boton boton-secundario boton-ancho" onClick={cargarPotreros}>
            Reintentar
          </button>
        </>
      )}

      {!cargandoPotreros && !errorPotreros && potreros.length === 0 && (
        <p className="texto-estado texto-estado-error">
          Todavía no hay potreros guardados. Ve a la pestaña &quot;Dibujar potreros&quot; y guárdalos
          primero.
        </p>
      )}

      <form onSubmit={guardar}>
        <label htmlFor="selector-potrero">Potrero</label>
        <select id="selector-potrero" value={potrero} onChange={(e) => setPotrero(e.target.value)} required>
          <option value="" disabled>
            Elige un potrero
          </option>
          {potreros.map((p) => (
            <option key={p.nombre} value={p.nombre}>
              {p.nombre}
            </option>
          ))}
        </select>

        <label htmlFor="campo-fecha">Fecha de la medición</label>
        <input
          type="date"
          id="campo-fecha"
          value={fecha}
          onChange={(e) => setFecha(e.target.value)}
          required
        />

        <label htmlFor="altura1">Primera medida (cm)</label>
        <input
          type="number"
          inputMode="decimal"
          step="0.1"
          min="0"
          max="200"
          id="altura1"
          placeholder="Ej: 12.5"
          value={altura1}
          onChange={(e) => setAltura1(e.target.value)}
          required
        />

        <label htmlFor="altura2">Segunda medida (cm)</label>
        <input
          type="number"
          inputMode="decimal"
          step="0.1"
          min="0"
          max="200"
          id="altura2"
          placeholder="Ej: 14.0"
          value={altura2}
          onChange={(e) => setAltura2(e.target.value)}
          required
        />

        <label htmlFor="altura3">Tercera medida (cm)</label>
        <input
          type="number"
          inputMode="decimal"
          step="0.1"
          min="0"
          max="200"
          id="altura3"
          placeholder="Ej: 13.2"
          value={altura3}
          onChange={(e) => setAltura3(e.target.value)}
          required
        />

        {mensaje && (
          <p className={`mensaje-formulario mensaje-${mensaje.tipo}`}>
            {mensaje.tipo === "cargando" && <span className="giro" aria-hidden="true"></span>}
            {mensaje.texto}
          </p>
        )}

        <button type="submit" className="boton boton-primario boton-ancho" disabled={guardando}>
          {editandoId ? "Guardar cambios" : "Guardar medición"}
        </button>
        {editandoId && (
          <button
            type="button"
            className="boton boton-secundario boton-ancho"
            onClick={limpiarFormulario}
            disabled={guardando}
          >
            Cancelar edición
          </button>
        )}
      </form>

      <section className="historial-aforo">
        <h3>Historial de mediciones</h3>

        {errorHistorial && (
          <>
            <p className="texto-estado texto-estado-error">
              No se pudo cargar el historial: {errorHistorial}
            </p>
            <button type="button" className="boton boton-secundario boton-ancho" onClick={cargarHistorial}>
              Reintentar
            </button>
          </>
        )}

        {historial === null && !errorHistorial && <p className="texto-suave">Cargando historial…</p>}

        {historial !== null && historial.length === 0 && !errorHistorial && (
          <p className="texto-suave">Todavía no has registrado ninguna medición.</p>
        )}

        <div className="lista-historial">
          {(historial || []).map((registro) => (
            <article key={registro.id} className="tarjeta-aforo">
              <div className="tarjeta-aforo-info">
                <span className="tarjeta-aforo-potrero">{registro.potrero}</span>
                <span className="tarjeta-aforo-fecha">{formatearFecha(registro.fecha)}</span>
                <span className="tarjeta-aforo-alturas">
                  {registro.altura_cm_1} / {registro.altura_cm_2} / {registro.altura_cm_3} cm
                </span>
              </div>
              <div className="tarjeta-aforo-acciones">
                {confirmandoBorrado === registro.id ? (
                  <span className="confirmar-borrado">
                    <button type="button" className="boton-enlace" onClick={() => confirmarBorrado(registro.id)}>
                      Sí, borrar
                    </button>
                    <button type="button" className="boton-enlace" onClick={() => setConfirmandoBorrado(null)}>
                      Cancelar
                    </button>
                  </span>
                ) : (
                  <>
                    <button
                      type="button"
                      className="boton-enlace"
                      onClick={() => iniciarEdicion(registro)}
                      disabled={borrandoId === registro.id}
                    >
                      Editar
                    </button>
                    <button
                      type="button"
                      className="boton-enlace boton-enlace-peligro"
                      onClick={() => setConfirmandoBorrado(registro.id)}
                      disabled={borrandoId === registro.id}
                    >
                      {borrandoId === registro.id ? "Borrando…" : "Eliminar"}
                    </button>
                  </>
                )}
              </div>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
