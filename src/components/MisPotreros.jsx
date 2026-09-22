import { useEffect, useState } from "react";
import { obtenerPotreros, dispararPrediccion } from "../utils/api.js";
import { formatearFecha } from "../utils/formato.js";
import { IconoEstado } from "./Iconos.jsx";

const TEXTOS_ESTADO = {
  verde: "Buen pasto, listo para pastorear.",
  ambar: "Pasto regular, hay que vigilarlo pronto.",
  rojo: "Pasto bajo, este potrero necesita descanso.",
  sin_datos: "Todavía no hay datos de este potrero.",
};

const NOMBRES_ESTADO = {
  verde: "Bien",
  ambar: "Regular",
  rojo: "Bajo",
  sin_datos: "Sin datos",
};

const NOMBRES_ALGORITMO = {
  random_forest: "Random Forest",
  regresion_lineal: "regresión lineal",
};

export default function MisPotreros() {
  const [datos, setDatos] = useState(null);
  const [error, setError] = useState(null);
  const [actualizando, setActualizando] = useState(false);
  const [resultadoActualizar, setResultadoActualizar] = useState(null); // { tipo: "ok"|"error", texto }

  function cargar() {
    setError(null);
    obtenerPotreros()
      .then(setDatos)
      .catch((err) => setError(err.message));
  }

  useEffect(() => {
    // Version con "activo" para no actualizar el estado si el componente
    // ya se desmonto antes de que la respuesta llegue (ver regla
    // react-hooks/set-state-in-effect). "error" ya arranca en null, no
    // hace falta reiniciarlo aqui.
    let activo = true;
    obtenerPotreros()
      .then((respuesta) => {
        if (activo) setDatos(respuesta);
      })
      .catch((err) => {
        if (activo) setError(err.message);
      });
    return () => {
      activo = false;
    };
  }, []);

  async function actualizar() {
    setActualizando(true);
    setResultadoActualizar(null);
    try {
      const respuesta = await dispararPrediccion();
      setDatos(respuesta);
      setResultadoActualizar({ tipo: "ok", texto: "Listo, la información de los potreros se actualizó." });
    } catch (err) {
      setResultadoActualizar({ tipo: "error", texto: `No se pudo actualizar: ${err.message}` });
    } finally {
      setActualizando(false);
    }
  }

  if (error) {
    return (
      <div className="contenido">
        <p className="texto-estado texto-estado-error">No se pudo cargar la información: {error}</p>
        <button type="button" className="boton boton-secundario boton-ancho" onClick={cargar}>
          Reintentar
        </button>
      </div>
    );
  }

  if (!datos) {
    return (
      <div className="contenido">
        <p className="texto-suave">Cargando información…</p>
      </div>
    );
  }

  const potreros = datos.potreros || [];
  const conteos = { verde: 0, ambar: 0, rojo: 0, sin_datos: 0 };
  potreros.forEach((p) => {
    conteos[p.estado] = (conteos[p.estado] || 0) + 1;
  });
  const modelo = datos.modelo;
  const modeloCalibrado = modelo && modelo.algoritmo && modelo.algoritmo !== "formula_provisional";

  return (
    <>
      <header className="encabezado">
        <h1>Hola, {datos.finca || "productor"}</h1>
        <p className="texto-suave">
          {datos.actualizado
            ? `Última actualización: ${formatearFecha(datos.actualizado)}`
            : "Todavía no se ha hecho ninguna actualización."}
        </p>
        {modeloCalibrado && (
          <p className="nota-modelo">
            Modelo calibrado con tus mediciones de campo (
            {NOMBRES_ALGORITMO[modelo.algoritmo] || modelo.algoritmo}
            {modelo.n_muestras_entrenamiento ? `, ${modelo.n_muestras_entrenamiento} mediciones` : ""}).
          </p>
        )}
      </header>

      <div className="contenido">
        <div className="resumen">
          {[
            ["verde", "Bien"],
            ["ambar", "Regular"],
            ["rojo", "Bajo"],
          ].map(([clave, etiqueta]) => (
            <div key={clave} className={`chip-resumen chip-${clave}`}>
              <span className="chip-numero">{conteos[clave]}</span>
              <span className="chip-etiqueta">
                <IconoEstado estado={clave} />
                {etiqueta}
              </span>
            </div>
          ))}
          {conteos.sin_datos > 0 && (
            <div className="chip-resumen chip-neutro">
              <span className="chip-numero">{conteos.sin_datos}</span>
              <span className="chip-etiqueta">
                <IconoEstado estado="sin_datos" />
                Sin datos
              </span>
            </div>
          )}
        </div>

        <button type="button" className="boton boton-primario boton-ancho" onClick={actualizar} disabled={actualizando}>
          Actualizar recomendaciones
        </button>

        {actualizando && (
          <p className="texto-estado texto-estado-cargando">
            <span className="giro" aria-hidden="true"></span>
            Consultando el satélite y actualizando…
          </p>
        )}
        {!actualizando && resultadoActualizar && (
          <p className={`texto-estado texto-estado-${resultadoActualizar.tipo}`}>
            {resultadoActualizar.texto}
            {resultadoActualizar.tipo === "error" && (
              <>
                <br />
                <button type="button" className="boton-enlace" onClick={actualizar}>
                  Reintentar
                </button>
              </>
            )}
          </p>
        )}

        <div className="lista-potreros">
          {potreros.length === 0 && <p className="texto-suave">Todavía no hay potreros cargados.</p>}
          {potreros.map((potrero) => {
            const estado = TEXTOS_ESTADO[potrero.estado] ? potrero.estado : "sin_datos";
            const esAproximado = potrero.fuente_prediccion === "formula_provisional";
            return (
              <article key={potrero.nombre} className={`tarjeta-potrero tarjeta-${estado}`}>
                <div className="tarjeta-cabecera">
                  <span className="tarjeta-nombre">
                    {potrero.nombre}
                    {esAproximado && <span className="insignia-aproximado">Estimado</span>}
                  </span>
                  <span className="tarjeta-chip">
                    <IconoEstado estado={estado} />
                    {NOMBRES_ESTADO[estado]}
                  </span>
                </div>
                <div className="tarjeta-detalle-interior">
                  <p>{TEXTOS_ESTADO[estado]}</p>
                  <p>
                    Biomasa estimada:{" "}
                    <strong>{potrero.biomasa_kg_ha != null ? `${potrero.biomasa_kg_ha} kg/ha` : "Sin dato"}</strong>
                  </p>
                  <p>Dato del: {formatearFecha(potrero.fecha)}</p>
                  {esAproximado && (
                    <p className="aviso-aproximado">
                      Estimación aproximada, todavía no calibrada con mediciones de campo. Ve a &quot;Registrar
                      medición&quot; para mejorarla.
                    </p>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      </div>
    </>
  );
}
