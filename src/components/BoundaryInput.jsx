import { useState, useRef } from "react";
import { parseBoundaryFile } from "../utils/parseBoundaryFile.js";

const EJEMPLO = `4.614796, -72.129994
4.613315, -72.130961
4.609507, -72.131676
4.607933, -72.132395
4.603174, -72.134577
4.600749, -72.135691
4.598587, -72.136688`;

export default function BoundaryInput({ onSubmit }) {
  const [text, setText] = useState("");
  const [fileError, setFileError] = useState("");
  const [textError, setTextError] = useState("");
  const fileInputRef = useRef(null);

  function handleFile(e) {
    const file = e.target.files[0];
    if (!file) return;
    setFileError("");
    const reader = new FileReader();
    reader.onload = () => {
      const parsed = parseBoundaryFile(reader.result);
      if (!parsed) {
        setFileError(
          "No se pudo leer ese archivo. Debe ser un .kml o .geojson con un polígono."
        );
        return;
      }
      setText(parsed);
    };
    reader.readAsText(file);
    e.target.value = ""; // permite volver a subir el mismo archivo si se corrige
  }

  function handleUsarContorno() {
    const error = onSubmit(text);
    setTextError(error || "");
  }

  return (
    <div className="card">
      <h2>1. Contorno de la finca</h2>
      <p className="hint">
        Sube el archivo del perímetro de tu finca (.kml o .geojson) o pega los
        vértices a mano, uno por línea, en formato <code>latitud, longitud</code>{" "}
        (puedes sacarlos de Google Maps o Google Earth). Sirve para cualquier
        finca del mundo.
      </p>

      <div className="toolbar">
        <button onClick={() => fileInputRef.current.click()}>
          Subir archivo (.kml / .geojson)
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept=".kml,.geojson,.json"
          style={{ display: "none" }}
          onChange={handleFile}
        />
      </div>
      {fileError && <p className="texto-estado texto-estado-error">{fileError}</p>}

      <textarea
        rows={7}
        placeholder={EJEMPLO}
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          if (textError) setTextError("");
        }}
      />
      {textError && <p className="texto-estado texto-estado-error">{textError}</p>}
      <div className="toolbar">
        <button className="primary" onClick={handleUsarContorno}>
          Usar este contorno
        </button>
        <button onClick={() => setText(EJEMPLO)}>Cargar ejemplo</button>
      </div>
    </div>
  );
}
