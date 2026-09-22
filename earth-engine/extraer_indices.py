#!/usr/bin/env python3
"""Calcula indices de vegetacion (Sentinel-2) por potrero a partir de un
GeoJSON exportado por SAD, usando Google Earth Engine.

Pieza independiente del pipeline: no forma parte del build de Vite/React
de la carpeta src/, es un script de Python que se corre a mano cuando se
necesita el dato de una jornada de aforo. Ver README.md de esta carpeta
para instrucciones de instalacion y uso.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta

import pandas as pd

try:
    import ee
except ImportError:
    print(
        "Error: no esta instalada la libreria 'earthengine-api'.\n"
        "Instala las dependencias con:\n"
        "    pip install -r requirements.txt"
    )
    sys.exit(1)

INDICES = ["NDVI", "GNDVI", "NDRE", "SAVI", "EVI"]
CLASES_SCL_VALIDAS = [4, 5, 7]  # 4=vegetacion, 5=suelo desnudo, 7=no vegetado/cobertura baja


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Calcula NDVI, GNDVI, NDRE, SAVI y EVI (Sentinel-2) por cada "
            "potrero de un GeoJSON, para la fecha mas cercana a una jornada "
            "de campo, usando Google Earth Engine."
        )
    )
    parser.add_argument(
        "--geojson",
        required=True,
        help="Ruta al archivo GeoJSON exportado por SAD (FeatureCollection de potreros).",
    )
    parser.add_argument(
        "--fecha",
        required=True,
        help="Fecha objetivo en formato YYYY-MM-DD (por ejemplo, la fecha de una jornada de aforo).",
    )
    parser.add_argument(
        "--ventana-dias",
        type=int,
        default=10,
        help="Dias antes/despues de --fecha para buscar la escena Sentinel-2 mas cercana sin nubes (default: 10).",
    )
    parser.add_argument(
        "--umbral-nubes",
        type=float,
        default=40,
        help="Porcentaje maximo de CLOUDY_PIXEL_PERCENTAGE aceptado (default: 40).",
    )
    parser.add_argument(
        "--salida",
        default="indices_potreros.csv",
        help="Ruta del archivo de salida: .csv o .xlsx segun la extension (default: indices_potreros.csv).",
    )
    parser.add_argument(
        "--proyecto",
        default=None,
        help="ID del proyecto de Google Cloud para Earth Engine. Si no se indica, se usa la variable de entorno EE_PROJECT.",
    )
    return parser.parse_args()


def inicializar_earth_engine(proyecto):
    if not proyecto:
        proyecto = os.environ.get("EE_PROJECT")
    if not proyecto:
        print(
            "Error: falta el proyecto de Google Cloud para Earth Engine.\n"
            "Pasalo con --proyecto mi-proyecto-gee o exporta la variable de "
            "entorno EE_PROJECT antes de correr el script."
        )
        sys.exit(1)

    try:
        ee.Initialize(project=proyecto)
        return
    except Exception:
        pass  # probablemente no hay credenciales todavia: se autentica abajo

    try:
        print("No se encontraron credenciales de Earth Engine. Abriendo el navegador para autenticarse...")
        ee.Authenticate()
        ee.Initialize(project=proyecto)
    except Exception as error:
        print(
            "Error al autenticarse o inicializar Earth Engine.\n"
            "Revisa tu conexion a internet, que hayas iniciado sesion con la "
            "cuenta de Google correcta y que el proyecto de Google Cloud "
            f"'{proyecto}' tenga la API de Earth Engine habilitada.\n"
            f"Detalle: {error}"
        )
        sys.exit(1)


def cargar_potreros(ruta_geojson):
    if not os.path.isfile(ruta_geojson):
        print(f"Error: no se encontro el archivo GeoJSON en '{ruta_geojson}'.")
        sys.exit(1)

    try:
        with open(ruta_geojson, "r", encoding="utf-8") as archivo:
            datos = json.load(archivo)
    except json.JSONDecodeError as error:
        print(f"Error: '{ruta_geojson}' no es un JSON valido.\nDetalle: {error}")
        sys.exit(1)

    features = datos.get("features")
    if not features:
        print(f"Error: '{ruta_geojson}' no tiene ninguna feature. Exporta al menos un potrero desde SAD.")
        sys.exit(1)

    features_ee = []
    for i, feature in enumerate(features):
        propiedades = feature.get("properties") or {}
        nombre = propiedades.get("nombre") or feature.get("nombre")
        if not nombre:
            nombre = f"potrero_{i + 1}"
            print(f"Aviso: una feature no tiene propiedad 'nombre', se usara '{nombre}'.")

        geometria = feature.get("geometry")
        if not geometria:
            print(f"Aviso: la feature '{nombre}' no tiene geometria, se omite.")
            continue

        features_ee.append(ee.Feature(ee.Geometry(geometria), {"potrero": nombre}))

    if not features_ee:
        print("Error: no se pudo construir ningun potrero valido a partir del GeoJSON.")
        sys.exit(1)

    return ee.FeatureCollection(features_ee)


def buscar_mejor_escena(area_total, fecha_objetivo, ventana_dias, umbral_nubes):
    inicio = fecha_objetivo - timedelta(days=ventana_dias)
    fin = fecha_objetivo + timedelta(days=ventana_dias + 1)  # +1 para incluir el ultimo dia de la ventana

    fecha_objetivo_millis = ee.Date(fecha_objetivo.isoformat()).millis()

    def con_diferencia_de_dias(imagen):
        diferencia_millis = ee.Number(imagen.get("system:time_start")).subtract(fecha_objetivo_millis).abs()
        dias = diferencia_millis.divide(1000 * 60 * 60 * 24)
        return imagen.set("dias_diferencia", dias)

    coleccion = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterDate(inicio.isoformat(), fin.isoformat())
        .filterBounds(area_total)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", umbral_nubes))
        .map(con_diferencia_de_dias)
        .sort("dias_diferencia")
    )

    try:
        cantidad = coleccion.size().getInfo()
    except Exception as error:
        print(
            "Error al consultar Earth Engine (posible problema de red o de "
            f"permisos del proyecto).\nDetalle: {error}"
        )
        sys.exit(1)

    if cantidad == 0:
        print(
            "No se encontro ninguna escena Sentinel-2 que cumpla las condiciones:\n"
            f"  - entre {inicio.isoformat()} y {fin.isoformat()} "
            f"(ventana de {ventana_dias} dias alrededor de {fecha_objetivo.isoformat()})\n"
            f"  - CLOUDY_PIXEL_PERCENTAGE < {umbral_nubes}\n"
            "  - que intersecte el area de los potreros\n\n"
            "Sugerencia: aumenta --ventana-dias o --umbral-nubes e intenta de nuevo."
        )
        sys.exit(1)

    imagen = ee.Image(coleccion.first())
    propiedades = imagen.toDictionary(["system:time_start", "CLOUDY_PIXEL_PERCENTAGE", "dias_diferencia", "system:index"]).getInfo()

    fecha_escena = datetime.utcfromtimestamp(propiedades["system:time_start"] / 1000).date()
    dias_diferencia = round(propiedades["dias_diferencia"])
    nubes = propiedades.get("CLOUDY_PIXEL_PERCENTAGE")
    id_escena = propiedades.get("system:index")

    return imagen, fecha_escena, dias_diferencia, nubes, id_escena


def enmascarar_y_calcular_indices(imagen):
    scl = imagen.select("SCL")
    mascara_valida = scl.eq(CLASES_SCL_VALIDAS[0])
    for clase in CLASES_SCL_VALIDAS[1:]:
        mascara_valida = mascara_valida.Or(scl.eq(clase))
    imagen = imagen.updateMask(mascara_valida)

    ndvi = imagen.normalizedDifference(["B8", "B4"]).rename("NDVI")
    gndvi = imagen.normalizedDifference(["B8", "B3"]).rename("GNDVI")
    ndre = imagen.normalizedDifference(["B8", "B5"]).rename("NDRE")

    savi = imagen.expression(
        "((NIR - RED) / (NIR + RED + 0.5)) * 1.5",
        {"NIR": imagen.select("B8"), "RED": imagen.select("B4")},
    ).rename("SAVI")

    evi = (
        imagen.expression(
            "2.5 * ((NIR - RED) / (NIR + 6 * RED - 7.5 * BLUE + 1))",
            {"NIR": imagen.select("B8"), "RED": imagen.select("B4"), "BLUE": imagen.select("B2")},
        )
        .clamp(-1, 1)
        .rename("EVI")
    )

    return ee.Image.cat([ndvi, gndvi, ndre, savi, evi])


def calcular_estadisticas_por_potrero(imagen_indices, potreros):
    reductor = ee.Reducer.mean().combine(reducer2=ee.Reducer.stdDev(), sharedInputs=True)
    try:
        resultado = imagen_indices.reduceRegions(collection=potreros, reducer=reductor, scale=10)
        features = resultado.getInfo()["features"]
    except Exception as error:
        print(f"Error al calcular los indices en Earth Engine (posible problema de red).\nDetalle: {error}")
        sys.exit(1)
    return features


def construir_dataframe(features, fecha_escena, dias_diferencia):
    columnas = ["potrero", "fecha_escena_usada", "dias_diferencia_con_fecha_objetivo"]
    for indice in INDICES:
        columnas += [f"{indice}_mean", f"{indice}_stdDev"]

    filas = []
    for feature in features:
        propiedades = feature["properties"]
        fila = {
            "potrero": propiedades.get("potrero"),
            "fecha_escena_usada": fecha_escena.isoformat(),
            "dias_diferencia_con_fecha_objetivo": dias_diferencia,
        }
        for indice in INDICES:
            fila[f"{indice}_mean"] = propiedades.get(f"{indice}_mean")
            fila[f"{indice}_stdDev"] = propiedades.get(f"{indice}_stdDev")
        filas.append(fila)

    return pd.DataFrame(filas, columns=columnas)


def main():
    args = parse_args()

    try:
        fecha_objetivo = datetime.strptime(args.fecha, "%Y-%m-%d").date()
    except ValueError:
        print(f"Error: '--fecha {args.fecha}' no tiene formato YYYY-MM-DD.")
        sys.exit(1)

    if args.ventana_dias < 0:
        print("Error: --ventana-dias no puede ser negativo.")
        sys.exit(1)
    if not (0 < args.umbral_nubes <= 100):
        print("Error: --umbral-nubes debe estar entre 0 y 100.")
        sys.exit(1)

    inicializar_earth_engine(args.proyecto)

    potreros = cargar_potreros(args.geojson)
    cantidad_potreros = potreros.size().getInfo()

    imagen, fecha_escena, dias_diferencia, nubes, id_escena = buscar_mejor_escena(
        potreros.geometry(), fecha_objetivo, args.ventana_dias, args.umbral_nubes
    )

    imagen_indices = enmascarar_y_calcular_indices(imagen)
    features = calcular_estadisticas_por_potrero(imagen_indices, potreros)
    df = construir_dataframe(features, fecha_escena, dias_diferencia)

    if str(args.salida).lower().endswith(".xlsx"):
        df.to_excel(args.salida, index=False)
    else:
        df.to_csv(args.salida, index=False)

    print("\nListo.")
    print(f"Potreros procesados: {cantidad_potreros}")
    print(f"Escena Sentinel-2 usada: {id_escena} (fecha real: {fecha_escena.isoformat()}, nubes: {nubes:.1f}%)")
    print(f"Diferencia con la fecha objetivo ({fecha_objetivo.isoformat()}): {dias_diferencia} dia(s)")
    print(f"Archivo generado en: {os.path.abspath(args.salida)}")


if __name__ == "__main__":
    main()
