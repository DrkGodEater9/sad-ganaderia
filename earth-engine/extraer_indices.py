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

# Factor de escala de COPERNICUS/S2_SR_HARMONIZED: la reflectancia viene como
# entero multiplicado por 10000. Ver enmascarar_y_calcular_indices().
ESCALA_REFLECTANCIA = 10000

# Cuantas escenas de la ventana se pueden llegar a probar buscando uno que
# deje indices utilizables en los potreros. Cada intento es una consulta mas
# a Earth Engine, asi que se corta en un numero razonable en vez de recorrer
# toda la ventana.
MAX_ESCENAS_CANDIDATAS = 25


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
    nombres = []
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
        nombres.append(nombre)

    if not features_ee:
        print("Error: no se pudo construir ningun potrero valido a partir del GeoJSON.")
        sys.exit(1)

    return ee.FeatureCollection(features_ee), nombres


def buscar_escenas_candidatas(area_total, fecha_objetivo, ventana_dias, umbral_nubes, limite=MAX_ESCENAS_CANDIDATAS):
    """Devuelve las escenas de la ventana que pasan el filtro de nubes,
    ordenadas de la mas cercana a la mas lejana respecto a --fecha.

    Devuelve varias y no solo la mejor a proposito: CLOUDY_PIXEL_PERCENTAGE
    es el porcentaje de nubes del TILE completo de Sentinel-2 (110 x 110 km),
    asi que una escena puede pasar el filtro y aun asi tener justo los
    potreros tapados por una nube o su sombra. En ese caso hay que poder
    seguir con la siguiente escena mas cercana en vez de quedarse sin dato.
    """
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
        .limit(limite)
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

    lista = coleccion.toList(cantidad)
    candidatas = []
    for indice in range(cantidad):
        imagen = ee.Image(lista.get(indice))
        try:
            propiedades = imagen.toDictionary(
                ["system:time_start", "CLOUDY_PIXEL_PERCENTAGE", "dias_diferencia", "system:index"]
            ).getInfo()
        except Exception as error:
            print(f"Aviso: no se pudieron leer los metadatos de una escena, se omite. Detalle: {error}")
            continue

        candidatas.append(
            {
                "imagen": imagen,
                "fecha_escena": datetime.utcfromtimestamp(propiedades["system:time_start"] / 1000).date(),
                "dias_diferencia": round(propiedades["dias_diferencia"]),
                "nubes": propiedades.get("CLOUDY_PIXEL_PERCENTAGE"),
                "id_escena": propiedades.get("system:index"),
            }
        )

    return candidatas


def recolectar_indices_por_potrero(potreros, nombres_potreros, candidatas):
    """Recorre las escenas candidatas de la mas cercana a la mas lejana y se
    queda, para CADA potrero, con la primera que le dio indices utilizables.

    Potreros distintos pueden terminar con escenas de fechas distintas: es
    preferible un dato real de hace unos dias que ningun dato porque justo
    ese dia habia una nube encima."""
    pendientes = set(nombres_potreros)
    resultados = {}

    for candidata in candidatas:
        if not pendientes:
            break

        imagen_indices = enmascarar_y_calcular_indices(candidata["imagen"])
        features = calcular_estadisticas_por_potrero(imagen_indices, potreros)

        for feature in features:
            propiedades = feature["properties"]
            nombre = propiedades.get("potrero")
            if nombre not in pendientes:
                continue
            # Sin NDVI ni SAVI la fila no le sirve al modelo: ese potrero
            # quedo enmascarado (nube o sombra encima) en esta escena.
            if propiedades.get("NDVI_mean") is None and propiedades.get("SAVI_mean") is None:
                continue

            fila = {
                "fecha_escena_usada": candidata["fecha_escena"].isoformat(),
                "dias_diferencia_con_fecha_objetivo": candidata["dias_diferencia"],
                "id_escena": candidata["id_escena"],
                "nubes_escena": candidata["nubes"],
            }
            for indice in INDICES:
                fila[f"{indice}_mean"] = propiedades.get(f"{indice}_mean")
                fila[f"{indice}_stdDev"] = propiedades.get(f"{indice}_stdDev")
            resultados[nombre] = fila
            pendientes.discard(nombre)

        if pendientes:
            print(
                f"Aviso: la escena del {candidata['fecha_escena'].isoformat()} no dejo indices utilizables "
                f"para {len(pendientes)} potrero(s) (nube o sombra encima); se probara con la siguiente."
            )

    return resultados, pendientes


def enmascarar_y_calcular_indices(imagen):
    scl = imagen.select("SCL")
    mascara_valida = scl.eq(CLASES_SCL_VALIDAS[0])
    for clase in CLASES_SCL_VALIDAS[1:]:
        mascara_valida = mascara_valida.Or(scl.eq(clase))
    imagen = imagen.updateMask(mascara_valida)

    # S2_SR_HARMONIZED entrega la reflectancia como entero escalado x10000
    # (valores tipicos 1000-4000), no en [0, 1]. NDVI, GNDVI y NDRE son
    # cocientes y no se ven afectados, pero SAVI y EVI tienen constantes
    # ADITIVAS (el L=0.5 de SAVI y el +1 de EVI) que solo significan algo con
    # reflectancia en [0, 1]: frente a valores de orden 1e3 quedan anuladas y
    # SAVI degenera en exactamente 1.5*NDVI mientras EVI se satura en su tope.
    # Por eso hay que dividir ANTES de evaluar las expresiones.
    reflectancia = imagen.divide(ESCALA_REFLECTANCIA)

    ndvi = reflectancia.normalizedDifference(["B8", "B4"]).rename("NDVI")
    gndvi = reflectancia.normalizedDifference(["B8", "B3"]).rename("GNDVI")
    ndre = reflectancia.normalizedDifference(["B8", "B5"]).rename("NDRE")

    savi = reflectancia.expression(
        "((NIR - RED) / (NIR + RED + 0.5)) * 1.5",
        {"NIR": reflectancia.select("B8"), "RED": reflectancia.select("B4")},
    ).rename("SAVI")

    evi = (
        reflectancia.expression(
            "2.5 * ((NIR - RED) / (NIR + 6 * RED - 7.5 * BLUE + 1))",
            {
                "NIR": reflectancia.select("B8"),
                "RED": reflectancia.select("B4"),
                "BLUE": reflectancia.select("B2"),
            },
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


def construir_dataframe(nombres_potreros, resultados, candidata_mas_cercana):
    """Una fila por potrero, siempre -- los que no consiguieron indices en
    ninguna escena quedan con la fecha de la escena mas cercana y los indices
    vacios (el modelo los interpreta como 'sin_datos')."""
    columnas = ["potrero", "fecha_escena_usada", "dias_diferencia_con_fecha_objetivo"]
    for indice in INDICES:
        columnas += [f"{indice}_mean", f"{indice}_stdDev"]

    filas = []
    for nombre in nombres_potreros:
        resultado = resultados.get(nombre)
        if resultado is None:
            resultado = {
                "fecha_escena_usada": candidata_mas_cercana["fecha_escena"].isoformat(),
                "dias_diferencia_con_fecha_objetivo": candidata_mas_cercana["dias_diferencia"],
            }

        fila = {
            "potrero": nombre,
            "fecha_escena_usada": resultado["fecha_escena_usada"],
            "dias_diferencia_con_fecha_objetivo": resultado["dias_diferencia_con_fecha_objetivo"],
        }
        for indice in INDICES:
            fila[f"{indice}_mean"] = resultado.get(f"{indice}_mean")
            fila[f"{indice}_stdDev"] = resultado.get(f"{indice}_stdDev")
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

    potreros, nombres_potreros = cargar_potreros(args.geojson)

    candidatas = buscar_escenas_candidatas(
        potreros.geometry(), fecha_objetivo, args.ventana_dias, args.umbral_nubes
    )
    resultados, pendientes = recolectar_indices_por_potrero(potreros, nombres_potreros, candidatas)

    if not resultados:
        print(
            f"\nNo se consiguieron indices utilizables para ningun potrero: las {len(candidatas)} escena(s) "
            f"de la ventana (+/- {args.ventana_dias} dias, nubes < {args.umbral_nubes}%) tienen los potreros "
            "tapados por nubes o sus sombras.\n\n"
            "Sugerencia: aumenta --ventana-dias para buscar en un rango de fechas mas amplio."
        )
        sys.exit(1)

    df = construir_dataframe(nombres_potreros, resultados, candidatas[0])

    if str(args.salida).lower().endswith(".xlsx"):
        df.to_excel(args.salida, index=False)
    else:
        df.to_csv(args.salida, index=False)

    fechas_usadas = sorted({fila["fecha_escena_usada"] for fila in resultados.values()})

    print("\nListo.")
    print(f"Potreros procesados: {len(nombres_potreros)}")
    print(f"Potreros con indices utilizables: {len(resultados)}")
    if pendientes:
        print(f"Potreros sin dato (nubes en todas las escenas probadas): {', '.join(sorted(pendientes))}")
    print(f"Escenas Sentinel-2 usadas: {', '.join(fechas_usadas)} (fecha objetivo: {fecha_objetivo.isoformat()})")
    print(f"Archivo generado en: {os.path.abspath(args.salida)}")


if __name__ == "__main__":
    main()
