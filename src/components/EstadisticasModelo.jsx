import { useEffect, useState } from "react";
import { obtenerPotreros } from "../utils/api.js";
import { formatearFecha } from "../utils/formato.js";

const NOMBRES_ALGORITMO = {
  random_forest: "Random Forest",
  regresion_lineal: "Regresión lineal",
};

// Paleta de datos validada contra colorblind-safety (ver dataviz skill),
// deliberadamente distinta del semáforo verde/ámbar/rojo y de la marca:
// aquí el color identifica el ALGORITMO, no un estado del potrero.
const COLOR_RANDOM_FOREST = "#2a78d6";
const COLOR_REGRESION_LINEAL = "#4a3aa7";

function numero(valor, decimales = 1) {
  return typeof valor === "number" && !Number.isNaN(valor) ? valor.toFixed(decimales) : "—";
}

function GraficoComparacion({ rmseRandomForest, rmseRegresionLineal, ganador }) {
  const maximo = Math.max(rmseRandomForest || 0, rmseRegresionLineal || 0, 1);
  const barras = [
    { clave: "random_forest", etiqueta: "Random Forest", valor: rmseRandomForest, color: COLOR_RANDOM_FOREST },
    { clave: "regresion_lineal", etiqueta: "Regresión lineal", valor: rmseRegresionLineal, color: COLOR_REGRESION_LINEAL },
  ];

  return (
    <div className="grafico">
      <div className="grafico-leyenda">
        {barras.map((b) => (
          <span key={b.clave} className="grafico-leyenda-item">
            <span className="grafico-leyenda-punto" style={{ background: b.color }} />
            {b.etiqueta}
            {b.clave === ganador && <span className="insignia-ganador">Ganador</span>}
          </span>
        ))}
      </div>
      {barras.map((b) => (
        <div key={b.clave} className="grafico-fila">
          <div className="grafico-pista">
            <div
              className="grafico-relleno"
              style={{ width: `${Math.max(4, ((b.valor || 0) / maximo) * 100)}%`, background: b.color }}
            />
          </div>
          <span className="grafico-valor">{numero(b.valor)} kg/ha</span>
        </div>
      ))}
      <p className="grafico-pie">Error promedio (RMSE) por validación cruzada — menor es mejor.</p>
    </div>
  );
}

function GraficoImportancia({ importancias }) {
  if (!importancias || importancias.length === 0) return null;
  const maximo = Math.max(...importancias.map((f) => f.importancia || 0), 0.0001);

  return (
    <div className="grafico">
      {importancias.map((fila) => (
        <div key={fila.variable} className="grafico-fila grafico-fila-etiquetada">
          <span className="grafico-etiqueta">{fila.variable}</span>
          <div className="grafico-pista">
            <div
              className="grafico-relleno"
              style={{ width: `${Math.max(4, (fila.importancia / maximo) * 100)}%`, background: COLOR_RANDOM_FOREST }}
            />
          </div>
          <span className="grafico-valor">{Math.round((fila.importancia || 0) * 100)}%</span>
        </div>
      ))}
    </div>
  );
}

export default function EstadisticasModelo() {
  const [modelo, setModelo] = useState(undefined); // undefined = cargando, null = sin datos
  const [error, setError] = useState(null);

  function cargar() {
    setModelo(undefined);
    setError(null);
    obtenerPotreros()
      .then((respuesta) => setModelo(respuesta.modelo || null))
      .catch((err) => setError(err.message));
  }

  useEffect(() => {
    let activo = true;
    obtenerPotreros()
      .then((respuesta) => {
        if (activo) setModelo(respuesta.modelo || null);
      })
      .catch((err) => {
        if (activo) setError(err.message);
      });
    return () => {
      activo = false;
    };
  }, []);

  if (error) {
    return (
      <div className="contenido">
        <h2>Estadísticas del modelo</h2>
        <p className="texto-estado texto-estado-error">No se pudo cargar la información: {error}</p>
        <button type="button" className="boton boton-secundario boton-ancho" onClick={cargar}>
          Reintentar
        </button>
      </div>
    );
  }

  if (modelo === undefined) {
    return (
      <div className="contenido">
        <h2>Estadísticas del modelo</h2>
        <p className="texto-suave">Cargando información…</p>
      </div>
    );
  }

  const entrenado = modelo && modelo.algoritmo && modelo.algoritmo !== "formula_provisional";

  if (!entrenado) {
    return (
      <div className="contenido">
        <h2>Estadísticas del modelo</h2>
        <p className="texto-suave">
          Todavía no hay un modelo entrenado: las estimaciones de biomasa de hoy usan una fórmula
          aproximada basada en literatura, no en datos de tu finca. En cuanto registres al menos 8
          mediciones de aforo (pestaña &quot;Registrar medición&quot;) y le des a &quot;Actualizar
          recomendaciones&quot;, el sistema entrena un modelo real y esta pantalla se llena con sus
          estadísticas: qué algoritmo ganó, qué tan preciso es, y qué variables de satélite pesan más.
        </p>
      </div>
    );
  }

  const comparacion = {
    random_forest: modelo.rmse_random_forest,
    regresion_lineal: modelo.rmse_regresion_lineal,
  };
  const hayComparacion = comparacion.random_forest != null && comparacion.regresion_lineal != null;

  return (
    <div className="contenido">
      <h2>Estadísticas del modelo</h2>
      <p className="texto-suave">
        Modelo entrenado con tus mediciones de campo — así de bien está prediciendo la biomasa de
        cada potrero a partir de los índices de satélite.
      </p>

      <div className="resumen">
        <div className="chip-resumen chip-neutro">
          <span className="chip-numero">{NOMBRES_ALGORITMO[modelo.algoritmo] || modelo.algoritmo}</span>
          <span className="chip-etiqueta">Algoritmo ganador</span>
        </div>
        <div className="chip-resumen chip-neutro">
          <span className="chip-numero">{numero(modelo.rmse)}</span>
          <span className="chip-etiqueta">RMSE (kg/ha)</span>
        </div>
        <div className="chip-resumen chip-neutro">
          <span className="chip-numero">{numero(modelo.r2, 2)}</span>
          <span className="chip-etiqueta">R²</span>
        </div>
        <div className="chip-resumen chip-neutro">
          <span className="chip-numero">{modelo.n_muestras_entrenamiento ?? "—"}</span>
          <span className="chip-etiqueta">Mediciones usadas</span>
        </div>
      </div>

      {hayComparacion && (
        <>
          <h2>Random Forest vs. regresión lineal</h2>
          <GraficoComparacion
            rmseRandomForest={comparacion.random_forest}
            rmseRegresionLineal={comparacion.regresion_lineal}
            ganador={modelo.algoritmo}
          />
        </>
      )}

      {modelo.importancias && modelo.importancias.length > 0 && (
        <>
          <h2>Qué variables pesan más</h2>
          <p className="texto-suave">
            Importancia relativa de cada índice de satélite (y clima, si se usó) en la predicción
            del algoritmo ganador.
          </p>
          <GraficoImportancia importancias={modelo.importancias} />
        </>
      )}

      <h2>Cómo se calibró</h2>
      <p className="texto-suave">
        Entrenado el <strong>{formatearFecha(modelo.entrenado_el)}</strong> con validación cruzada
        (k = {modelo.k_validacion ?? "—"}){modelo.usa_clima ? ", usando también variables de clima" : ""}.
      </p>
      <p className="texto-suave">
        Conversión altura de pasto → biomasa:{" "}
        <strong>
          {numero(modelo.calibracion_a, 0)} + {numero(modelo.calibracion_b, 0)} × altura (cm)
        </strong>
        .
      </p>
      <p className="texto-suave">
        Semáforo: menos de <strong>{numero(modelo.umbral_rojo, 0)} kg/ha</strong> es rojo, más de{" "}
        <strong>{numero(modelo.umbral_ambar, 0)} kg/ha</strong> es verde.
      </p>
    </div>
  );
}
