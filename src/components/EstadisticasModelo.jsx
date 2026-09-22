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

function conSigno(valor, decimales = 1) {
  if (typeof valor !== "number" || Number.isNaN(valor)) return "—";
  return `${valor >= 0 ? "+" : ""}${valor.toFixed(decimales)}`;
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

// Dispersión observado vs. predicho con la recta 1:1. Es la figura estándar
// para reportar un modelo de estimación de biomasa: cuanto más pegados a la
// diagonal los puntos, mejor. Escalas iguales en ambos ejes a propósito (si
// no, la diagonal deja de ser el 45° real y engaña).
function GraficoDispersion({ validacion }) {
  const [activo, setActivo] = useState(null);

  if (!validacion || validacion.length === 0) return null;

  const valores = validacion.flatMap((p) => [p.observado, p.predicho]).filter((v) => typeof v === "number");
  if (valores.length === 0) return null;

  const margen = (Math.max(...valores) - Math.min(...valores)) * 0.12 || 10;
  const minimo = Math.max(0, Math.min(...valores) - margen);
  const maximo = Math.max(...valores) + margen;

  const LADO = 300;
  const PAD = 44;
  const escala = (valor) => PAD + ((valor - minimo) / (maximo - minimo)) * (LADO - PAD * 1.4);
  const escalaY = (valor) => LADO - escala(valor) + PAD * 0.2;

  const ticks = [minimo, (minimo + maximo) / 2, maximo];

  return (
    <div className="grafico">
      <svg
        viewBox={`0 0 ${LADO} ${LADO}`}
        className="dispersion"
        role="img"
        aria-label="Dispersión de biomasa observada contra biomasa predicha por el modelo"
      >
        {ticks.map((t) => (
          <g key={`gx-${t}`}>
            <line x1={escala(t)} y1={escalaY(minimo)} x2={escala(t)} y2={escalaY(maximo)} className="dispersion-grid" />
            <line x1={escala(minimo)} y1={escalaY(t)} x2={escala(maximo)} y2={escalaY(t)} className="dispersion-grid" />
            <text x={escala(t)} y={escalaY(minimo) + 16} className="dispersion-tick" textAnchor="middle">
              {Math.round(t)}
            </text>
            <text x={escala(minimo) - 6} y={escalaY(t) + 4} className="dispersion-tick" textAnchor="end">
              {Math.round(t)}
            </text>
          </g>
        ))}

        <line
          x1={escala(minimo)}
          y1={escalaY(minimo)}
          x2={escala(maximo)}
          y2={escalaY(maximo)}
          className="dispersion-diagonal"
        />

        {validacion.map((punto, i) => (
          <circle
            key={i}
            cx={escala(punto.observado)}
            cy={escalaY(punto.predicho)}
            r="6"
            fill={COLOR_RANDOM_FOREST}
            className="dispersion-punto"
            tabIndex={0}
            onMouseEnter={() => setActivo(punto)}
            onMouseLeave={() => setActivo(null)}
            onFocus={() => setActivo(punto)}
            onBlur={() => setActivo(null)}
          >
            <title>
              {punto.potrero} ({punto.fecha_aforo}): observado {numero(punto.observado)}, predicho{" "}
              {numero(punto.predicho)} kg/ha
            </title>
          </circle>
        ))}

        <text x={LADO / 2} y={LADO - 2} className="dispersion-eje" textAnchor="middle">
          Observado (kg MS/ha)
        </text>
        <text x={12} y={LADO / 2} className="dispersion-eje" textAnchor="middle" transform={`rotate(-90 12 ${LADO / 2})`}>
          Predicho (kg MS/ha)
        </text>
      </svg>

      <p className="grafico-pie">
        {activo
          ? `${activo.potrero} · ${formatearFecha(activo.fecha_aforo)} · observado ${numero(activo.observado)} vs. predicho ${numero(activo.predicho)} kg/ha (residuo ${conSigno(activo.residuo)})`
          : "Cada punto es una medición de campo; la diagonal es la predicción perfecta. Pasa el cursor por un punto para ver el detalle."}
      </p>
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
  const n = modelo.n_muestras_entrenamiento;
  const modeloDebil = typeof modelo.r2 === "number" && modelo.r2 < 0.5;
  const muestraChica = typeof n === "number" && n < 30;

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
          <span className="chip-numero">{n ?? "—"}</span>
          <span className="chip-etiqueta">Mediciones usadas</span>
        </div>
      </div>

      {(modeloDebil || muestraChica) && (
        <p className="aviso-metodologico">
          <strong>Léelo con cuidado antes de citarlo.</strong>{" "}
          {muestraChica && `Con ${n} mediciones y ${modelo.n_variables_entrada ?? "varias"} variables de entrada, el modelo tiene muy pocos datos por variable: las métricas son inestables y pueden cambiar bastante con una medición más. `}
          {modeloDebil &&
            `Un R² de ${numero(modelo.r2, 2)} significa que el modelo todavía explica poco de la variación real de la biomasa${typeof modelo.r2 === "number" && modelo.r2 < 0 ? " (un R² negativo es peor que predecir siempre el promedio)" : ""}. `}
          Sirve como prueba de concepto del sistema, no como calibración definitiva de la finca.
        </p>
      )}

      <h2>Métricas de validación</h2>
      <p className="texto-suave">
        Calculadas sobre las predicciones fuera de pliegue de una validación cruzada k-fold (k ={" "}
        {modelo.k_validacion ?? "—"}), es decir sobre datos que el modelo no vio al entrenarse.
      </p>
      <div className="tabla-scroll">
        <table className="tabla-metricas">
          <tbody>
            <tr>
              <th scope="row">RMSE</th>
              <td>{numero(modelo.rmse)} kg MS/ha</td>
              <td className="tabla-nota">Error típico de una predicción</td>
            </tr>
            <tr>
              <th scope="row">nRMSE</th>
              <td>{numero(modelo.nrmse_pct)} %</td>
              <td className="tabla-nota">RMSE como % de la biomasa media</td>
            </tr>
            <tr>
              <th scope="row">MAE</th>
              <td>{numero(modelo.mae)} kg MS/ha</td>
              <td className="tabla-nota">Error absoluto promedio</td>
            </tr>
            <tr>
              <th scope="row">Sesgo</th>
              <td>{conSigno(modelo.sesgo)} kg MS/ha</td>
              <td className="tabla-nota">
                {typeof modelo.sesgo === "number" && modelo.sesgo >= 0 ? "Sobreestima" : "Subestima"} en promedio
              </td>
            </tr>
            <tr>
              <th scope="row">R²</th>
              <td>{numero(modelo.r2, 3)}</td>
              <td className="tabla-nota">Variación explicada (1 = perfecto)</td>
            </tr>
            <tr>
              <th scope="row">n</th>
              <td>{n ?? "—"}</td>
              <td className="tabla-nota">Puntos aforo ↔ satélite emparejados</td>
            </tr>
            <tr>
              <th scope="row">Variables</th>
              <td>{modelo.n_variables_entrada ?? "—"}</td>
              <td className="tabla-nota">{modelo.usa_clima ? "Índices + clima" : "Solo índices de satélite"}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <h2>La muestra de entrenamiento</h2>
      <div className="tabla-scroll">
        <table className="tabla-metricas">
          <tbody>
            <tr>
              <th scope="row">Biomasa media</th>
              <td>
                {numero(modelo.biomasa_media)} ± {numero(modelo.biomasa_desv)} kg MS/ha
              </td>
            </tr>
            <tr>
              <th scope="row">Rango</th>
              <td>
                {numero(modelo.biomasa_min)} – {numero(modelo.biomasa_max)} kg MS/ha
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      {modelo.validacion && modelo.validacion.length > 0 && (
        <>
          <h2>Observado vs. predicho</h2>
          <GraficoDispersion validacion={modelo.validacion} />
          <div className="tabla-scroll">
            <table className="tabla-metricas tabla-validacion">
              <thead>
                <tr>
                  <th scope="col">Potrero</th>
                  <th scope="col">Fecha</th>
                  <th scope="col">Observado</th>
                  <th scope="col">Predicho</th>
                  <th scope="col">Residuo</th>
                </tr>
              </thead>
              <tbody>
                {modelo.validacion.map((fila, i) => (
                  <tr key={i}>
                    <td>{fila.potrero}</td>
                    <td>{fila.fecha_aforo}</td>
                    <td>{numero(fila.observado)}</td>
                    <td>{numero(fila.predicho)}</td>
                    <td>{conSigno(fila.residuo)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {hayComparacion && (
        <>
          <h2>Random Forest vs. regresión lineal</h2>
          <GraficoComparacion
            rmseRandomForest={comparacion.random_forest}
            rmseRegresionLineal={comparacion.regresion_lineal}
            ganador={modelo.algoritmo}
          />
          <div className="tabla-scroll">
            <table className="tabla-metricas tabla-validacion">
              <thead>
                <tr>
                  <th scope="col">Algoritmo</th>
                  <th scope="col">RMSE</th>
                  <th scope="col">R²</th>
                  <th scope="col">MAE</th>
                  <th scope="col">Sesgo</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>Random Forest</td>
                  <td>{numero(modelo.rmse_random_forest)}</td>
                  <td>{numero(modelo.r2_random_forest, 3)}</td>
                  <td>{numero(modelo.mae_random_forest)}</td>
                  <td>{conSigno(modelo.sesgo_random_forest)}</td>
                </tr>
                <tr>
                  <td>Regresión lineal</td>
                  <td>{numero(modelo.rmse_regresion_lineal)}</td>
                  <td>{numero(modelo.r2_regresion_lineal, 3)}</td>
                  <td>{numero(modelo.mae_regresion_lineal)}</td>
                  <td>{conSigno(modelo.sesgo_regresion_lineal)}</td>
                </tr>
              </tbody>
            </table>
          </div>
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
