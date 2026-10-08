import { describe, expect, it } from "vitest";
import { formatearFecha, hoyISO } from "../formato.js";
import { parseBoundaryText } from "../parseBoundary.js";
import { parseBoundaryFile } from "../parseBoundaryFile.js";
import { areaHectares, latLonToLocalXY, localXYToLatLon } from "../geo.js";
import { buildGeoJSON } from "../exportGeoJSON.js";

describe("formatearFecha", () => {
  it("no corre un dia una fecha solo-dia (bug de zona horaria UTC)", () => {
    expect(formatearFecha("2026-09-22")).toContain("22");
  });
  it("devuelve 'Sin dato' si no hay fecha y el texto original si es invalida", () => {
    expect(formatearFecha(null)).toBe("Sin dato");
    expect(formatearFecha("no-es-fecha")).toBe("no-es-fecha");
  });
  it("hoyISO tiene formato AAAA-MM-DD", () => {
    expect(hoyISO()).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
});

describe("parseBoundaryText", () => {
  it("lee lat, lon con coma o espacio y con CRLF", () => {
    expect(parseBoundaryText("4.6, -72.1\r\n4.7 -72.2")).toEqual([
      [4.6, -72.1],
      [4.7, -72.2],
    ]);
  });
  it("descarta lineas vacias, mal formadas y fuera de rango", () => {
    expect(parseBoundaryText("hola\n,5\n95, 10\n10, 190\n1, 2")).toEqual([[1, 2]]);
  });
});

describe("parseBoundaryFile", () => {
  it("lee un GeoJSON Polygon como lat, lon", () => {
    const gj = JSON.stringify({ type: "Polygon", coordinates: [[[-72, 4], [-71, 4], [-71, 5], [-72, 4]]] });
    expect(parseBoundaryFile(gj).split("\n")[0]).toBe("4, -72");
  });
  it("lee KML (lon,lat,alt)", () => {
    expect(parseBoundaryFile("<kml><coordinates>-72,4,0 -71,5,0</coordinates></kml>")).toBe("4, -72\n5, -71");
  });
  it("devuelve vacio con basura", () => {
    expect(parseBoundaryFile("basura")).toBe("");
  });
});

describe("geo", () => {
  it("ida y vuelta lat/lon <-> metros locales", () => {
    const ref = { lat: 4.6, lon: -72.1 };
    const [lat, lon] = localXYToLatLon(latLonToLocalXY([4.61, -72.09], ref), ref);
    expect(lat).toBeCloseTo(4.61, 8);
    expect(lon).toBeCloseTo(-72.09, 8);
  });
  it("area de un cuadrado de 100 m = 1 ha", () => {
    expect(areaHectares([[0, 0], [100, 0], [100, 100], [0, 100]])).toBeCloseTo(1);
  });
});

describe("buildGeoJSON", () => {
  it("cierra el anillo y usa [lon, lat]", () => {
    const ref = { lat: 4.6, lon: -72.1 };
    const gj = buildGeoJSON([{ name: "P1", areaHa: 1, pointsXY: [[0, 0], [100, 0], [100, 100]] }], ref);
    const anillo = gj.features[0].geometry.coordinates[0];
    expect(anillo).toHaveLength(4);
    expect(anillo[0]).toEqual(anillo[3]);
    expect(anillo[0][0]).toBeCloseTo(-72.1);
  });
});
