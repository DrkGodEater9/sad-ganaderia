import { useEffect, useMemo, useState } from "react";
import BoundaryInput from "./components/BoundaryInput.jsx";
import MapCanvas from "./components/MapCanvas.jsx";
import Toolbar from "./components/Toolbar.jsx";
import PotreroTable from "./components/PotreroTable.jsx";
import MisPotreros from "./components/MisPotreros.jsx";
import RegistrarMedicion from "./components/RegistrarMedicion.jsx";
import EstadisticasModelo from "./components/EstadisticasModelo.jsx";
import ErrorBoundary from "./components/ErrorBoundary.jsx";
import { parseBoundaryText } from "./utils/parseBoundary.js";
import { latLonToLocalXY, areaHectares } from "./utils/geo.js";
import { buildGeoJSON, downloadJSON } from "./utils/exportGeoJSON.js";
import { guardarGeojson, eliminarPotrero } from "./utils/api.js";

const PALETTE = ["#2e7d32", "#c99b4a", "#1565c0", "#ad1457", "#00838f", "#6a1b9a", "#ef6c00", "#558b2f"];

// El dibujo en curso se guarda en el navegador para no perderlo si se
// recarga la página sin querer -- se borra al usarlo en la app, al
// exportarlo, o al darle a "Cambiar de finca".
const CLAVE_GUARDADO = "potrero-mapper:dibujo-en-curso";

function cargarDibujoGuardado() {
  try {
    const crudo = localStorage.getItem(CLAVE_GUARDADO);
    return crudo ? JSON.parse(crudo) : null;
  } catch {
    return null;
  }
}

function guardarDibujoEnNavegador(datos) {
  try {
    localStorage.setItem(CLAVE_GUARDADO, JSON.stringify(datos));
  } catch {
    // almacenamiento lleno o deshabilitado (ej. navegacion privada): no es critico
  }
}

function borrarDibujoGuardado() {
  try {
    localStorage.removeItem(CLAVE_GUARDADO);
  } catch {
    // nada que hacer
  }
}

const VISTAS = [
  { clave: "dibujar", etiqueta: "Dibujar potreros" },
  { clave: "productor", etiqueta: "Mis potreros" },
  { clave: "aforo", etiqueta: "Registrar medición" },
  { clave: "estadisticas", etiqueta: "Estadísticas" },
];

export default function App() {
  const [vista, setVista] = useState("dibujar");
  const dibujoGuardado = useMemo(() => cargarDibujoGuardado(), []);
  const [ref, setRef] = useState(dibujoGuardado?.ref ?? null); // {lat, lon} punto de referencia para la proyección
  const [boundary, setBoundary] = useState(dibujoGuardado?.boundary ?? []); // [[x,y], ...] en metros locales
  const [potreros, setPotreros] = useState(dibujoGuardado?.potreros ?? []);
  const [current, setCurrent] = useState(dibujoGuardado?.current ?? []);
  const [pendiente, setPendiente] = useState(dibujoGuardado?.pendiente ?? null); // { pointsXY, areaHa } potrero cerrado, esperando nombre
  const [nombrePendiente, setNombrePendiente] = useState(dibujoGuardado?.nombrePendiente ?? "");
  const [errorNombrePendiente, setErrorNombrePendiente] = useState(null);
  const [guardandoEnApp, setGuardandoEnApp] = useState(false);
  const [resultadoGuardar, setResultadoGuardar] = useState(null); // { tipo: "ok"|"error", texto }

  useEffect(() => {
    if (boundary.length === 0) return;
    guardarDibujoEnNavegador({ ref, boundary, potreros, current, pendiente, nombrePendiente });
  }, [ref, boundary, potreros, current, pendiente, nombrePendiente]);

  function handleBoundarySubmit(text) {
    const latLonPoints = parseBoundaryText(text);
    if (latLonPoints.length < 3) {
      return "Pega al menos 3 puntos válidos (latitud, longitud), uno por línea.";
    }
    const reference = { lat: latLonPoints[0][0], lon: latLonPoints[0][1] };
    const xy = latLonPoints.map((p) => latLonToLocalXY(p, reference));
    setRef(reference);
    setBoundary(xy);
    setPotreros([]);
    setCurrent([]);
    return null;
  }

  function handleAddPoint(xy) {
    if (pendiente) return; // esperando que le pongan nombre al potrero recien cerrado
    if (xy === null) {
      closeCurrentPotrero();
      return;
    }
    setCurrent((prev) => [...prev, xy]);
  }

  function closeCurrentPotrero() {
    if (current.length < 3) return;
    // No usamos prompt() (dialogo nativo del navegador, desentona con el
    // resto de la app): se deja el potrero "pendiente de nombre" y se pide
    // el nombre con un campo normal, dentro de la misma tarjeta.
    setPendiente({ pointsXY: current, areaHa: areaHectares(current) });
    setNombrePendiente(`Potrero_${potreros.length + 1}`);
    setCurrent([]);
  }

  function confirmarNombrePotrero(evento) {
    evento.preventDefault();
    if (!pendiente) return;
    const nombre = nombrePendiente.trim();
    if (!nombre) return;
    if (potreros.some((p) => p.name.toLowerCase() === nombre.toLowerCase())) {
      setErrorNombrePendiente(`Ya hay un potrero llamado "${nombre}". Ponle un nombre distinto.`);
      return;
    }
    setPotreros((prev) => [
      ...prev,
      { name: nombre, pointsXY: pendiente.pointsXY, areaHa: pendiente.areaHa, color: PALETTE[prev.length % PALETTE.length] },
    ]);
    setPendiente(null);
    setNombrePendiente("");
    setErrorNombrePendiente(null);
  }

  function cancelarPotreroPendiente() {
    // no se pierden los puntos: vuelven al dibujo en curso para seguir editando
    if (pendiente) setCurrent(pendiente.pointsXY);
    setPendiente(null);
    setNombrePendiente("");
    setErrorNombrePendiente(null);
  }

  function handleExport() {
    if (potreros.length === 0) return;
    const geojson = buildGeoJSON(potreros, ref);
    downloadJSON(geojson, "potreros.geojson");
  }

  async function handleUsarEnApp() {
    if (potreros.length === 0) return;
    setGuardandoEnApp(true);
    setResultadoGuardar(null);
    try {
      const geojson = buildGeoJSON(potreros, ref);
      const respuesta = await guardarGeojson(geojson);
      setResultadoGuardar({
        tipo: "ok",
        texto: `Listo: se guardaron ${respuesta.potreros.length} potreros. Ya los puedes ver en "Mis potreros" y "Registrar medición".`,
      });
    } catch (err) {
      setResultadoGuardar({ tipo: "error", texto: `No se pudo guardar: ${err.message}` });
    } finally {
      setGuardandoEnApp(false);
    }
  }

  async function handleDeletePotrero(index) {
    const potrero = potreros[index];
    setPotreros((prev) => prev.filter((_, idx) => idx !== index));
    try {
      // Si ese potrero ya estaba guardado en el backend (por "Usar estos
      // potreros en la app"), lo borra de ahi tambien -- para que
      // desaparezca de "Mis potreros", "Registrar medición" y
      // "Estadísticas", no solo del dibujo. Si nunca se habia guardado
      // (o el backend no esta corriendo), esto simplemente falla y no
      // pasa nada: el borrado local ya se hizo.
      await eliminarPotrero(potrero.name);
    } catch {
      // silencioso a propósito, ver comentario de arriba
    }
  }

  const currentColor = PALETTE[potreros.length % PALETTE.length];

  return (
    <>
      <ErrorBoundary key={vista}>
      {vista === "dibujar" && (
        <div className="wrap">
          <h1>SAD</h1>
          <p className="subtitle">
            Dibuja los potreros de cualquier finca sobre su contorno real y exporta las coordenadas
            en formato GeoJSON estándar (abrible en QGIS, Google Earth Engine, geojson.io, etc).
          </p>

          {dibujoGuardado && boundary.length > 0 && (
            <p className="hint">
              Recuperamos el dibujo que tenías antes de recargar la página ({potreros.length} potrero
              {potreros.length === 1 ? "" : "s"} cerrado{potreros.length === 1 ? "" : "s"}).
            </p>
          )}

          {boundary.length === 0 ? (
            <BoundaryInput onSubmit={handleBoundarySubmit} />
          ) : (
            <>
              <div className="card">
                <h2>2. Dibuja los potreros</h2>
                <p className="hint">
                  Haz clic dentro del contorno para marcar cada esquina. Cierra el polígono haciendo
                  clic cerca del primer punto, o con el botón de abajo.
                </p>
                <Toolbar
                  onUndo={() => setCurrent((prev) => prev.slice(0, -1))}
                  onCancel={() => setCurrent([])}
                  onClose={closeCurrentPotrero}
                  canClose={current.length >= 3}
                  disabled={!!pendiente}
                />
                <MapCanvas
                  boundary={boundary}
                  potreros={potreros}
                  current={current}
                  onAddPoint={handleAddPoint}
                  currentColor={currentColor}
                />

                {pendiente && (
                  <>
                    <form className="toolbar" onSubmit={confirmarNombrePotrero}>
                      <input
                        type="text"
                        value={nombrePendiente}
                        onChange={(e) => {
                          setNombrePendiente(e.target.value);
                          if (errorNombrePendiente) setErrorNombrePendiente(null);
                        }}
                        placeholder="Nombre del potrero"
                        aria-label="Nombre del potrero"
                        autoFocus
                        required
                      />
                      <button type="submit" className="primary">
                        Guardar potrero
                      </button>
                      <button type="button" onClick={cancelarPotreroPendiente}>
                        Cancelar
                      </button>
                    </form>
                    {errorNombrePendiente && (
                      <p className="texto-estado texto-estado-error">{errorNombrePendiente}</p>
                    )}
                  </>
                )}

                <button
                  type="button"
                  className="boton boton-primario boton-ancho"
                  onClick={handleUsarEnApp}
                  disabled={guardandoEnApp || potreros.length === 0}
                >
                  {guardandoEnApp ? "Guardando…" : "Usar estos potreros en la app"}
                </button>

                {potreros.length === 0 ? (
                  <p className="hint">Cierra al menos un potrero arriba para poder guardarlo.</p>
                ) : (
                  <p className="hint">
                    Deja listos estos {potreros.length} potrero{potreros.length === 1 ? "" : "s"} para
                    &quot;Mis potreros&quot; y &quot;Registrar medición&quot; (necesita el backend
                    corriendo).
                  </p>
                )}
                {resultadoGuardar && (
                  <p className={`texto-estado texto-estado-${resultadoGuardar.tipo}`}>{resultadoGuardar.texto}</p>
                )}
              </div>

              <div className="card">
                <h2>Potreros marcados</h2>
                <PotreroTable potreros={potreros} onDelete={handleDeletePotrero} />
              </div>

              <div className="card">
                <h2>Otras opciones</h2>
                <div className="toolbar">
                  <button onClick={handleExport} disabled={potreros.length === 0}>
                    Descargar GeoJSON
                  </button>
                  <button
                    onClick={() => {
                      setBoundary([]);
                      setPotreros([]);
                      setCurrent([]);
                      setPendiente(null);
                      setNombrePendiente("");
                      setRef(null);
                      setResultadoGuardar(null);
                      borrarDibujoGuardado();
                    }}
                  >
                    Cambiar de finca
                  </button>
                </div>
                <p className="hint">
                  &quot;Descargar GeoJSON&quot; guarda el archivo por si lo quieres abrir en QGIS,
                  Google Earth Engine, etc. &quot;Cambiar de finca&quot; borra el dibujo actual para
                  empezar de nuevo.
                </p>
              </div>
            </>
          )}
        </div>
      )}

      {vista === "productor" && <MisPotreros />}
      {vista === "aforo" && <RegistrarMedicion />}
      {vista === "estadisticas" && <EstadisticasModelo />}
      </ErrorBoundary>

      <nav className="nav-inferior">
        {VISTAS.map((v) => (
          <button
            key={v.clave}
            type="button"
            className={`nav-boton${vista === v.clave ? " nav-boton-activo" : ""}`}
            onClick={() => setVista(v.clave)}
          >
            {v.etiqueta}
          </button>
        ))}
      </nav>
    </>
  );
}
