#!/usr/bin/env python3
"""Entrena (cuando hay aforo suficiente) y corre el modelo de biomasa
forrajera por potrero: compara Random Forest contra regresion lineal con
validacion cruzada, y predice el estado de cada potrero del GeoJSON.

Mientras no haya aforo de campo suficiente usa una formula provisional de
literatura, nunca un modelo "entrenado" con datos que no existen. Ver
README.md de esta carpeta para el contrato completo (nombres de hojas,
columnas y argumentos que espera el backend).
"""

import argparse
import json
import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd

try:
    import joblib
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.linear_model import LinearRegression
    from sklearn.metrics import mean_squared_error, r2_score
    from sklearn.model_selection import KFold
except ImportError:
    print(
        "Error: faltan dependencias de Python ('scikit-learn' y/o 'joblib').\n"
        "Instalalas con:\n"
        "    pip install -r requirements.txt"
    )
    sys.exit(1)

INDICES = ["NDVI", "GNDVI", "NDRE", "SAVI", "EVI"]
COLUMNAS_INDICES = [f"{i}_{sufijo}" for i in INDICES for sufijo in ("mean", "stdDev")]
COLUMNAS_CLIMA = ["precip_30d_mm", "temp_media_c"]

# Conversion provisional altura de pasto -> biomasa (kg MS/ha):
#   biomasa = CALIBRACION_A + CALIBRACION_B * altura_cm_promedio
# Son constantes PROVISIONALES (un punto de partida razonable, no una
# calibracion local): se reemplazan con --calibracion-a/--calibracion-b en
# cuanto se pesen aunque sea 4-5 muestras de pasto cortado y secado.
CALIBRACION_A = 50.0
CALIBRACION_B = 15.0

# Formula provisional NDVI -> biomasa, usada SOLO mientras no hay aforo
# suficiente para entrenar:
#   biomasa_kg_ms_ha = FORMULA_BASE * exp(FORMULA_K * NDVI)
# Es una aproximacion tomada del TIPO de relacion exponencial que reportan
# los estudios de pastos tropicales (p. ej. Urochloa humidicola en la
# Altillanura colombiana), con constantes redondeadas para que quede claro
# que NO es una calibracion local de esta finca: NDVI 0.45 -> ~308 kg/ha,
# 0.65 -> ~508 kg/ha, 0.80 -> ~739 kg/ha. NO usar para decisiones finas de
# carga animal; reemplazar por el modelo entrenado apenas haya aforo real.
FORMULA_BASE = 100.0
FORMULA_K = 2.5
FORMULA_BIOMASA_MAXIMA = 4000.0  # tope de cordura: nada de valores absurdos

# Si falta NDVI en la escena pero hay SAVI, se aproxima NDVI a partir de SAVI.
# El valor es el cociente NDVI/SAVI medido sobre las 80 filas del historial de
# esta finca (rango 1.34-2.13, media 1.69). Es una aproximacion local, no una
# constante universal: depende del nivel de reflectancia del pasto.
# En la practica es un camino poco frecuente: NDVI y SAVI salen de la misma
# imagen enmascarada, asi que casi siempre se anulan juntos.
SAVI_A_NDVI = 1.69

# Hiperparametros conservadores a proposito: el dataset de aforo va a ser
# diminuto (el minimo del contrato son 8 muestras), asi que un bosque
# profundo con hojas de 1 muestra memorizaria el ruido. Arboles cortos,
# hojas de al menos 2 muestras y muchos arboles para promediar la varianza.
RF_HIPERPARAMETROS = {
    "n_estimators": 300,
    "max_depth": 4,
    "min_samples_leaf": 2,
    "min_samples_split": 4,
    "max_features": "sqrt",
    "random_state": 42,
    "n_jobs": -1,
}


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Entrena y/o corre el modelo de biomasa forrajera por potrero: "
            "compara Random Forest contra regresion lineal usando indices "
            "Sentinel-2 y aforo de campo, y escribe el estado (semaforo) de "
            "cada potrero en un Excel."
        )
    )
    parser.add_argument(
        "--geojson",
        required=True,
        help="Ruta al GeoJSON de potreros exportado por SAD.",
    )
    parser.add_argument(
        "--indices",
        required=True,
        help="Ruta al historial de indices satelitales (Excel, hoja 'Indices').",
    )
    parser.add_argument(
        "--aforo",
        required=True,
        help="Ruta al aforo de campo (Excel, hoja 'Aforo'). Si no existe todavia, se usa la formula provisional.",
    )
    parser.add_argument(
        "--salida",
        required=True,
        help="Ruta del Excel de estado que se va a sobreescribir (hojas 'Potreros', 'Finca', 'Modelo_Info').",
    )
    parser.add_argument(
        "--modelo-guardado",
        default=None,
        help="Ruta del modelo entrenado en formato joblib (default: 'modelo_entrenado.joblib' junto a --salida).",
    )
    parser.add_argument(
        "--clima",
        default=None,
        help="Ruta opcional al archivo de clima diario NASA POWER (.csv o .xlsx, columnas YEAR, DOY, T2M, PRECTOTCORR).",
    )
    parser.add_argument(
        "--umbral-rojo",
        type=float,
        default=300.0,
        help="Biomasa (kg MS/ha) por debajo de la cual el potrero queda en 'rojo' (default: 300).",
    )
    parser.add_argument(
        "--umbral-ambar",
        type=float,
        default=500.0,
        help="Biomasa (kg MS/ha) a partir de la cual el potrero queda en 'verde' (default: 500).",
    )
    parser.add_argument(
        "--calibracion-a",
        type=float,
        default=CALIBRACION_A,
        help=f"Constante A de altura_cm -> biomasa: biomasa = A + B * altura (default: {CALIBRACION_A:g}).",
    )
    parser.add_argument(
        "--calibracion-b",
        type=float,
        default=CALIBRACION_B,
        help=f"Constante B de altura_cm -> biomasa: biomasa = A + B * altura (default: {CALIBRACION_B:g}).",
    )
    parser.add_argument(
        "--minimo-muestras-entrenamiento",
        type=int,
        default=8,
        help="Minimo de puntos de aforo emparejados con satelite para animarse a entrenar (default: 8).",
    )
    parser.add_argument(
        "--ventana-emparejamiento-dias",
        type=int,
        default=15,
        help="Dias maximos de diferencia entre la fecha del aforo y la de la escena satelital (default: 15).",
    )
    parser.add_argument(
        "--variables",
        default=None,
        help=(
            "Lista separada por comas de las variables de entrada a usar (por ejemplo "
            "'NDVI_mean,NDVI_stdDev,precip_30d_mm'). Por defecto se usan las 12 (10 indices "
            "+ 2 de clima). Con pocas muestras conviene reducirlas: con menos puntos que "
            "variables el modelo sobreajusta y el R2 se vuelve negativo."
        ),
    )
    parser.add_argument(
        "--modo",
        choices=["auto", "train", "predict"],
        default="auto",
        help=(
            "auto: reentrena solo si hay aforo nuevo desde el ultimo entrenamiento. "
            "train: fuerza reentrenamiento. predict: nunca entrena (default: auto)."
        ),
    )
    return parser.parse_args()


def normalizar_fecha(valor):
    """Convierte a date lo que venga de Excel/CSV (texto, datetime, Timestamp)."""
    if valor is None or (isinstance(valor, float) and np.isnan(valor)):
        return None
    if isinstance(valor, pd.Timestamp):
        return None if pd.isna(valor) else valor.date()
    if isinstance(valor, datetime):
        return valor.date()
    if hasattr(valor, "year") and hasattr(valor, "day") and not isinstance(valor, str):
        return valor
    texto = str(valor).strip()
    if not texto:
        return None
    convertida = pd.to_datetime(texto, errors="coerce", dayfirst=False)
    return None if pd.isna(convertida) else convertida.date()


def cargar_nombres_de_potreros(ruta_geojson):
    if not os.path.isfile(ruta_geojson):
        print(f"Error: no se encontro el GeoJSON de potreros en '{ruta_geojson}'.")
        sys.exit(1)
    try:
        with open(ruta_geojson, "r", encoding="utf-8") as archivo:
            datos = json.load(archivo)
    except json.JSONDecodeError as error:
        print(f"Error: '{ruta_geojson}' no es un JSON valido.\nDetalle: {error}")
        sys.exit(1)

    nombres = []
    for i, feature in enumerate(datos.get("features") or []):
        propiedades = feature.get("properties") or {}
        nombre = propiedades.get("nombre") or feature.get("nombre") or f"potrero_{i + 1}"
        nombre = str(nombre).strip()
        if nombre and nombre not in nombres:
            nombres.append(nombre)

    if not nombres:
        print(
            f"Error: '{ruta_geojson}' no tiene ningun potrero. Exporta al menos "
            "uno desde SAD antes de correr el modelo."
        )
        sys.exit(1)
    return nombres


def leer_hoja_excel(ruta, nombre_hoja):
    """Lee una hoja de Excel por nombre; si no existe, cae a la primera hoja
    (el archivo se puede haber editado a mano). Devuelve None si no se pudo."""
    try:
        with pd.ExcelFile(ruta) as libro:
            hoja = nombre_hoja if nombre_hoja in libro.sheet_names else libro.sheet_names[0]
            if hoja != nombre_hoja:
                print(f"Aviso: '{ruta}' no tiene una hoja '{nombre_hoja}'; se usara la hoja '{hoja}'.")
            df = libro.parse(hoja)
    except Exception as error:
        print(f"Aviso: no se pudo leer '{ruta}'. Detalle: {error}")
        return None
    df.columns = [str(c).strip() for c in df.columns]
    return df


def cargar_indices(ruta):
    if not os.path.isfile(ruta):
        print(
            f"Error: no se encontro el historial de indices en '{ruta}'.\n"
            "Corre primero earth-engine/extraer_indices.py (o /api/predecir del "
            "backend, que lo hace por ti) para generar al menos una consulta satelital."
        )
        sys.exit(1)

    df = leer_hoja_excel(ruta, "Indices")
    if df is None or df.empty:
        print(f"Error: el historial de indices '{ruta}' esta vacio: no hay con que predecir todavia.")
        sys.exit(1)

    if "potrero" not in df.columns:
        print(f"Error: el historial de indices '{ruta}' no tiene la columna 'potrero'.")
        sys.exit(1)
    if "fecha_escena_usada" not in df.columns:
        print(f"Error: el historial de indices '{ruta}' no tiene la columna 'fecha_escena_usada'.")
        sys.exit(1)

    df["potrero"] = df["potrero"].astype(str).str.strip()
    df["fecha_escena"] = df["fecha_escena_usada"].map(normalizar_fecha)
    df = df[df["fecha_escena"].notna()].copy()
    if df.empty:
        print(f"Error: ninguna fila de '{ruta}' tiene una 'fecha_escena_usada' legible.")
        sys.exit(1)

    for columna in COLUMNAS_INDICES:
        if columna not in df.columns:
            df[columna] = np.nan
        df[columna] = pd.to_numeric(df[columna], errors="coerce")

    return df.sort_values("fecha_escena").reset_index(drop=True)


def cargar_aforo(ruta, calibracion_a, calibracion_b):
    """Devuelve un DataFrame potrero/fecha/biomasa_kg_ms_ha. Que no exista o
    que venga vacio NO es un error: es el escenario normal al arrancar."""
    columnas = ["potrero", "fecha_aforo", "altura_cm_promedio", "biomasa_kg_ms_ha"]
    if not os.path.isfile(ruta):
        print(f"Aviso: todavia no existe el archivo de aforo '{ruta}' (no hay mediciones de campo).")
        return pd.DataFrame(columns=columnas)

    df = leer_hoja_excel(ruta, "Aforo")
    if df is None or df.empty:
        print(f"Aviso: el archivo de aforo '{ruta}' no tiene filas todavia.")
        return pd.DataFrame(columns=columnas)

    columnas_altura = [c for c in ("altura_cm_1", "altura_cm_2", "altura_cm_3") if c in df.columns]
    if "potrero" not in df.columns or "fecha" not in df.columns or not columnas_altura:
        print(
            f"Aviso: el aforo '{ruta}' no tiene las columnas esperadas "
            "(potrero, fecha, altura_cm_1..3); se ignorara."
        )
        return pd.DataFrame(columns=columnas)

    df = df.copy()
    df["potrero"] = df["potrero"].astype(str).str.strip()
    df["fecha_aforo"] = df["fecha"].map(normalizar_fecha)
    for columna in columnas_altura:
        df[columna] = pd.to_numeric(df[columna], errors="coerce")
    df["altura_cm_promedio"] = df[columnas_altura].mean(axis=1, skipna=True)

    validas = df["fecha_aforo"].notna() & df["altura_cm_promedio"].notna() & (df["altura_cm_promedio"] > 0)
    descartadas = int((~validas).sum())
    if descartadas:
        print(f"Aviso: se descartaron {descartadas} fila(s) de aforo por fecha o alturas invalidas.")
    df = df[validas].copy()
    if df.empty:
        return pd.DataFrame(columns=columnas)

    df["biomasa_kg_ms_ha"] = calibracion_a + calibracion_b * df["altura_cm_promedio"]
    return df[columnas].reset_index(drop=True)


def cargar_clima(ruta):
    """Lee el clima diario en formato NASA POWER. Si el archivo esta mal
    formado se avisa y se sigue SIN clima (no se revienta la corrida)."""
    if not ruta:
        return None
    if not os.path.isfile(ruta):
        print(f"Aviso: no se encontro el archivo de clima '{ruta}'. Se seguira sin variables climaticas.")
        return None

    try:
        if str(ruta).lower().endswith((".xlsx", ".xls")):
            crudo = pd.read_excel(ruta, header=None)
        else:
            # El CSV de NASA POWER trae un bloque -BEGIN HEADER- ... -END HEADER-
            # antes de la fila de encabezados: se busca la fila que empieza en YEAR.
            crudo = pd.read_csv(ruta, header=None, names=range(8), engine="python", on_bad_lines="skip")

        fila_encabezado = None
        for indice, valor in crudo[0].items():
            if str(valor).strip().upper() == "YEAR":
                fila_encabezado = indice
                break
        if fila_encabezado is None:
            print(f"Aviso: el archivo de clima '{ruta}' no tiene una fila de encabezados con 'YEAR'. Se seguira sin clima.")
            return None

        encabezados = [str(c).strip() for c in crudo.iloc[fila_encabezado].tolist() if str(c).strip() not in ("", "nan")]
        df = crudo.iloc[fila_encabezado + 1 :, : len(encabezados)].copy()
        df.columns = encabezados
    except Exception as error:
        print(f"Aviso: no se pudo leer el archivo de clima '{ruta}'. Se seguira sin clima.\nDetalle: {error}")
        return None

    faltantes = [c for c in ("YEAR", "DOY", "T2M", "PRECTOTCORR") if c not in df.columns]
    if faltantes:
        print(
            f"Aviso: al archivo de clima '{ruta}' le faltan las columnas {', '.join(faltantes)} "
            "(se espera el formato NASA POWER). Se seguira sin clima."
        )
        return None

    for columna in ("YEAR", "DOY", "T2M", "PRECTOTCORR"):
        df[columna] = pd.to_numeric(df[columna], errors="coerce")
    df = df[df["YEAR"].notna() & df["DOY"].notna()].copy()

    # -999 es el codigo de dato faltante de NASA POWER.
    df["T2M"] = df["T2M"].where(df["T2M"] > -900)
    df["PRECTOTCORR"] = df["PRECTOTCORR"].where(df["PRECTOTCORR"] > -900)

    df["fecha"] = pd.to_datetime(df["YEAR"].astype(int).astype(str), format="%Y") + pd.to_timedelta(
        df["DOY"].astype(int) - 1, unit="D"
    )
    df = df[["fecha", "T2M", "PRECTOTCORR"]].dropna(subset=["fecha"]).sort_values("fecha").reset_index(drop=True)
    if df.empty:
        print(f"Aviso: el archivo de clima '{ruta}' no tiene ninguna fila utilizable. Se seguira sin clima.")
        return None

    print(
        f"Clima cargado: {len(df)} dias, de {df['fecha'].min().date().isoformat()} "
        f"a {df['fecha'].max().date().isoformat()}."
    )
    return df


def resumen_clima(clima, fecha):
    """Precipitacion acumulada y temperatura media de los 30 dias previos
    (incluyendo la fecha). Devuelve NaN si esa ventana no tiene datos."""
    if clima is None or fecha is None:
        return np.nan, np.nan
    fin = pd.Timestamp(fecha)
    inicio = fin - pd.Timedelta(days=29)
    ventana = clima[(clima["fecha"] >= inicio) & (clima["fecha"] <= fin)]
    if ventana.empty:
        return np.nan, np.nan
    precipitacion = ventana["PRECTOTCORR"].sum(skipna=True) if ventana["PRECTOTCORR"].notna().any() else np.nan
    temperatura = ventana["T2M"].mean(skipna=True) if ventana["T2M"].notna().any() else np.nan
    return precipitacion, temperatura


def emparejar_aforo_con_indices(aforo, indices, ventana_dias, clima):
    """Para cada aforo busca la escena del MISMO potrero con la fecha mas
    cercana dentro de la ventana. Sin match cercano, ese punto se descarta."""
    filas = []
    descartados = 0
    for _, punto in aforo.iterrows():
        candidatas = indices[indices["potrero"] == punto["potrero"]]
        if candidatas.empty:
            descartados += 1
            print(
                f"Aviso: el aforo de '{punto['potrero']}' del {punto['fecha_aforo']} se descarta: "
                "ese potrero no tiene ninguna consulta satelital en el historial."
            )
            continue

        diferencias = candidatas["fecha_escena"].map(lambda f: abs((f - punto["fecha_aforo"]).days))
        mejor = int(diferencias.idxmin())
        dias = int(diferencias.loc[mejor])
        if dias > ventana_dias:
            descartados += 1
            print(
                f"Aviso: el aforo de '{punto['potrero']}' del {punto['fecha_aforo']} se descarta: "
                f"la escena satelital mas cercana esta a {dias} dias (maximo permitido: {ventana_dias})."
            )
            continue

        fila = {columna: candidatas.loc[mejor, columna] for columna in COLUMNAS_INDICES}
        precipitacion, temperatura = resumen_clima(clima, candidatas.loc[mejor, "fecha_escena"])
        fila["precip_30d_mm"] = precipitacion
        fila["temp_media_c"] = temperatura
        fila["biomasa_kg_ms_ha"] = punto["biomasa_kg_ms_ha"]
        fila["potrero"] = punto["potrero"]
        fila["fecha_aforo"] = punto["fecha_aforo"]
        fila["dias_diferencia"] = dias
        filas.append(fila)

    if descartados:
        print(f"Aviso: {descartados} punto(s) de aforo quedaron sin escena satelital cercana.")
    return pd.DataFrame(filas)


def columnas_de_entrada(usar_clima, seleccion=None):
    disponibles = COLUMNAS_INDICES + (COLUMNAS_CLIMA if usar_clima else [])
    if not seleccion:
        return disponibles

    pedidas = [c.strip() for c in seleccion.split(",") if c.strip()]
    desconocidas = [c for c in pedidas if c not in COLUMNAS_INDICES + COLUMNAS_CLIMA]
    if desconocidas:
        print(
            f"Error: --variables incluye nombres que no existen: {', '.join(desconocidas)}.\n"
            f"Validas: {', '.join(COLUMNAS_INDICES + COLUMNAS_CLIMA)}"
        )
        sys.exit(1)

    elegidas = [c for c in pedidas if c in disponibles]
    ignoradas = [c for c in pedidas if c not in disponibles]
    if ignoradas:
        print(f"Aviso: se ignoran {', '.join(ignoradas)} porque se corrio sin --clima.")
    if not elegidas:
        print("Error: --variables no dejo ninguna variable utilizable.")
        sys.exit(1)
    return elegidas


def validar_cruzado(modelo, X, y, k):
    """Valida con k-fold y calcula las metricas sobre las predicciones fuera
    de pliegue juntas (con pliegues de 2-3 muestras, un R2 por pliegue no
    significa nada; agrupadas si).

    Devuelve (metricas, predicciones_fuera_de_pliegue). Ademas de RMSE y R2
    se reportan MAE, sesgo y nRMSE porque son los que pide la literatura de
    estimacion de biomasa por sensores remotos: el RMSE solo no distingue
    entre un modelo que se equivoca parejo y uno que subestima siempre."""
    predicciones = np.zeros(len(y), dtype=float)
    for indices_entrenamiento, indices_prueba in KFold(n_splits=k, shuffle=True, random_state=42).split(X):
        modelo.fit(X[indices_entrenamiento], y[indices_entrenamiento])
        predicciones[indices_prueba] = modelo.predict(X[indices_prueba])

    residuos = predicciones - y
    media_observada = float(np.mean(y))
    rmse = float(np.sqrt(mean_squared_error(y, predicciones)))

    metricas = {
        "rmse": rmse,
        "r2": float(r2_score(y, predicciones)),
        "mae": float(np.mean(np.abs(residuos))),
        # Sesgo (error medio): positivo = el modelo sobreestima en promedio.
        "sesgo": float(np.mean(residuos)),
        # RMSE como % de la biomasa media observada: permite comparar contra
        # estudios de otras fincas/pastos, donde la escala de kg/ha cambia.
        "nrmse_pct": float(rmse / media_observada * 100) if media_observada else None,
    }
    return metricas, predicciones


def entrenar_modelo(emparejados, usar_clima, minimo_muestras, seleccion_variables=None):
    """Compara Random Forest contra regresion lineal y devuelve el paquete
    del ganador (o None si no hay con que entrenar)."""
    columnas = columnas_de_entrada(usar_clima, seleccion_variables)
    datos = emparejados.dropna(subset=["biomasa_kg_ms_ha"]).copy()

    # Columnas que estan completamente vacias no aportan y romperian la
    # imputacion por mediana: se sacan del juego.
    columnas = [c for c in columnas if c in datos.columns and datos[c].notna().any()]
    if not columnas:
        print("Aviso: los puntos emparejados no tienen ningun indice utilizable; no se puede entrenar.")
        return None

    medianas = {c: float(datos[c].median()) for c in columnas}
    X = datos[columnas].fillna(pd.Series(medianas)).to_numpy(dtype=float)
    y = datos["biomasa_kg_ms_ha"].to_numpy(dtype=float)

    if len(y) < minimo_muestras:
        return None

    # k adaptativo: nunca mas pliegues que muestras/2, nunca menos de 2.
    k = max(2, min(5, len(y) // 2))

    candidatos = {
        "random_forest": RandomForestRegressor(**RF_HIPERPARAMETROS),
        "regresion_lineal": LinearRegression(),
    }
    metricas = {}
    predicciones_por_algoritmo = {}
    for nombre, modelo in candidatos.items():
        metricas[nombre], predicciones_por_algoritmo[nombre] = validar_cruzado(modelo, X, y, k)
        m = metricas[nombre]
        print(
            f"  {nombre}: RMSE = {m['rmse']:.1f} kg MS/ha, R2 = {m['r2']:.3f}, "
            f"MAE = {m['mae']:.1f}, sesgo = {m['sesgo']:+.1f} (k-fold con k={k})"
        )

    ganador = min(metricas, key=lambda nombre: metricas[nombre]["rmse"])
    metricas_ganador = metricas[ganador]

    modelo_final = candidatos[ganador]
    modelo_final.fit(X, y)

    # Importancia de cada variable para el algoritmo ganador: en Random
    # Forest es feature_importances_ (ya normalizado); en regresion lineal
    # se aproxima con el valor absoluto de los coeficientes, normalizado
    # para que sume 1 (no es directamente comparable entre algoritmos, pero
    # sirve para ver que variables pesan mas dentro de cada uno).
    if ganador == "random_forest":
        pesos = np.asarray(modelo_final.feature_importances_, dtype=float)
    else:
        pesos = np.abs(np.asarray(modelo_final.coef_, dtype=float))
    total_pesos = pesos.sum()
    pesos = pesos / total_pesos if total_pesos > 0 else pesos
    importancias = sorted(
        ({"variable": col, "importancia": float(peso)} for col, peso in zip(columnas, pesos)),
        key=lambda fila: fila["importancia"],
        reverse=True,
    )

    # Observado vs predicho fuera de pliegue, punto por punto: es la tabla
    # con la que se arma el grafico de dispersion y la que permite ver si el
    # error se concentra en los potreros con mas (o menos) pasto.
    def etiqueta(columna, i):
        if columna not in datos.columns:
            return None
        valor = datos.iloc[i][columna]
        return valor.isoformat() if hasattr(valor, "isoformat") else str(valor)

    observado_vs_predicho = [
        {
            "potrero": etiqueta("potrero", i),
            "fecha_aforo": etiqueta("fecha_aforo", i),
            "observado": float(y[i]),
            "predicho": float(predicciones_por_algoritmo[ganador][i]),
            "residuo": float(predicciones_por_algoritmo[ganador][i] - y[i]),
        }
        for i in range(len(y))
    ]

    return {
        "modelo": modelo_final,
        "algoritmo": ganador,
        "columnas": columnas,
        "medianas": medianas,
        "rmse": metricas_ganador["rmse"],
        "r2": metricas_ganador["r2"],
        "mae": metricas_ganador["mae"],
        "sesgo": metricas_ganador["sesgo"],
        "nrmse_pct": metricas_ganador["nrmse_pct"],
        "n_muestras_entrenamiento": int(len(y)),
        "n_variables_entrada": len(columnas),
        "entrenado_el": datetime.now().replace(microsecond=0).isoformat(sep=" "),
        "usa_clima": bool(usar_clima and any(c in columnas for c in COLUMNAS_CLIMA)),
        "k_validacion": k,
        # Descriptivas de la muestra de entrenamiento: sin saber el rango y la
        # dispersion de la biomasa medida, un RMSE en kg/ha no se puede leer.
        "biomasa_media": float(np.mean(y)),
        "biomasa_desv": float(np.std(y, ddof=1)) if len(y) > 1 else 0.0,
        "biomasa_min": float(np.min(y)),
        "biomasa_max": float(np.max(y)),
        # Metricas de AMBOS algoritmos (no solo el ganador), para poder
        # mostrar la comparacion completa en la app.
        "metricas_comparacion": metricas,
        "importancias": importancias,
        "observado_vs_predicho": observado_vs_predicho,
        # Huella del aforo usado, para que el modo auto sepa si hay algo nuevo.
        "n_filas_aforo": None,
        "ultima_fecha_aforo": None,
    }


def biomasa_formula_provisional(fila):
    """Formula provisional NDVI -> biomasa (ver constantes arriba). Solo se
    usa mientras no hay un modelo entrenado con aforo real."""
    ndvi = fila.get("NDVI_mean")
    if ndvi is None or pd.isna(ndvi):
        savi = fila.get("SAVI_mean")
        if savi is None or pd.isna(savi):
            return None
        ndvi = float(savi) * SAVI_A_NDVI
    ndvi = float(np.clip(float(ndvi), 0.0, 1.0))
    return float(min(FORMULA_BASE * np.exp(FORMULA_K * ndvi), FORMULA_BIOMASA_MAXIMA))


def clasificar_estado(biomasa, umbral_rojo, umbral_ambar):
    if biomasa is None:
        return "sin_datos"
    if biomasa < umbral_rojo:
        return "rojo"
    if biomasa < umbral_ambar:
        return "ambar"
    return "verde"


def predecir_potreros(nombres, indices, paquete, clima, args):
    filas = []
    conteo = {"modelo_entrenado": 0, "formula_provisional": 0, "sin_datos": 0}

    for nombre in nombres:
        historial = indices[indices["potrero"] == nombre]
        if historial.empty:
            print(f"Aviso: el potrero '{nombre}' no tiene ninguna consulta satelital todavia (queda 'sin_datos').")
            filas.append(
                {
                    "nombre": nombre,
                    "estado": "sin_datos",
                    "biomasa_kg_ha": None,
                    "fecha": None,
                    "fuente_prediccion": None,
                }
            )
            conteo["sin_datos"] += 1
            continue

        # El historial ya viene ordenado por fecha de escena, pero la fila mas
        # reciente puede venir vacia (ese dia el potrero estaba bajo una nube):
        # se usa la ultima que SI tenga con que estimar, no la ultima a secas.
        utilizables = historial[historial["NDVI_mean"].notna() | historial["SAVI_mean"].notna()]
        ultima = (utilizables if not utilizables.empty else historial).iloc[-1]
        precipitacion, temperatura = resumen_clima(clima, ultima["fecha_escena"])
        valores = {c: ultima.get(c) for c in COLUMNAS_INDICES}
        valores["precip_30d_mm"] = precipitacion
        valores["temp_media_c"] = temperatura

        biomasa = None
        fuente = None
        if paquete is not None:
            # Se rellena con las medianas del entrenamiento lo que falte hoy
            # (un indice nulo por nubes, o el clima si se corrio sin --clima).
            entrada = []
            faltantes = []
            for columna in paquete["columnas"]:
                valor = valores.get(columna)
                if valor is None or pd.isna(valor):
                    faltantes.append(columna)
                    valor = paquete["medianas"].get(columna, 0.0)
                entrada.append(float(valor))
            if faltantes:
                print(
                    f"Aviso: a '{nombre}' le faltan {', '.join(faltantes)}; se usan las medianas del entrenamiento."
                )
            biomasa = float(paquete["modelo"].predict(np.array([entrada], dtype=float))[0])
            fuente = "modelo_entrenado"
        else:
            biomasa = biomasa_formula_provisional(valores)
            fuente = "formula_provisional" if biomasa is not None else None

        if biomasa is None:
            print(f"Aviso: el potrero '{nombre}' no tiene indices utilizables en su ultima escena (queda 'sin_datos').")
            estado = "sin_datos"
            conteo["sin_datos"] += 1
        else:
            biomasa = round(max(0.0, biomasa), 1)
            estado = clasificar_estado(biomasa, args.umbral_rojo, args.umbral_ambar)
            conteo[fuente] += 1

        filas.append(
            {
                "nombre": nombre,
                "estado": estado,
                "biomasa_kg_ha": biomasa,
                "fecha": ultima["fecha_escena"].isoformat() if biomasa is not None else None,
                "fuente_prediccion": fuente,
            }
        )

    return pd.DataFrame(filas), conteo


def nombre_de_finca_previo(ruta_salida):
    """Conserva el nombre de finca que ya tuviera el Excel anterior."""
    if not os.path.isfile(ruta_salida):
        return None
    try:
        df = pd.read_excel(ruta_salida, sheet_name="Finca")
    except Exception:
        return None
    if df.empty or "finca" not in df.columns:
        return None
    valor = df.iloc[0]["finca"]
    return None if pd.isna(valor) else str(valor)


def guardar_salida(ruta, potreros, paquete, args):
    carpeta = os.path.dirname(os.path.abspath(ruta))
    if carpeta:
        os.makedirs(carpeta, exist_ok=True)

    finca = nombre_de_finca_previo(ruta) or "Mi finca"
    hoja_finca = pd.DataFrame(
        [{"finca": finca, "actualizado": datetime.now().replace(microsecond=0).isoformat(sep=" ")}]
    )

    comparacion = paquete["metricas_comparacion"] if paquete else {}
    rf = comparacion.get("random_forest", {})
    rl = comparacion.get("regresion_lineal", {})

    def redondear(valor, decimales=2):
        return round(valor, decimales) if isinstance(valor, (int, float)) else None

    hoja_modelo = pd.DataFrame(
        [
            {
                "algoritmo": paquete["algoritmo"] if paquete else "formula_provisional",
                "rmse": redondear(paquete["rmse"]) if paquete else None,
                "r2": redondear(paquete["r2"], 4) if paquete else None,
                "mae": redondear(paquete["mae"]) if paquete else None,
                "sesgo": redondear(paquete["sesgo"]) if paquete else None,
                "nrmse_pct": redondear(paquete["nrmse_pct"]) if paquete else None,
                "n_muestras_entrenamiento": paquete["n_muestras_entrenamiento"] if paquete else None,
                "n_variables_entrada": paquete["n_variables_entrada"] if paquete else None,
                "entrenado_el": paquete["entrenado_el"] if paquete else None,
                "k_validacion": paquete["k_validacion"] if paquete else None,
                "usa_clima": paquete["usa_clima"] if paquete else None,
                "biomasa_media": redondear(paquete["biomasa_media"]) if paquete else None,
                "biomasa_desv": redondear(paquete["biomasa_desv"]) if paquete else None,
                "biomasa_min": redondear(paquete["biomasa_min"]) if paquete else None,
                "biomasa_max": redondear(paquete["biomasa_max"]) if paquete else None,
                "rmse_random_forest": redondear(rf.get("rmse")) if rf else None,
                "r2_random_forest": redondear(rf.get("r2"), 4) if rf else None,
                "mae_random_forest": redondear(rf.get("mae")) if rf else None,
                "sesgo_random_forest": redondear(rf.get("sesgo")) if rf else None,
                "rmse_regresion_lineal": redondear(rl.get("rmse")) if rl else None,
                "r2_regresion_lineal": redondear(rl.get("r2"), 4) if rl else None,
                "mae_regresion_lineal": redondear(rl.get("mae")) if rl else None,
                "sesgo_regresion_lineal": redondear(rl.get("sesgo")) if rl else None,
                "calibracion_a": args.calibracion_a,
                "calibracion_b": args.calibracion_b,
                "umbral_rojo": args.umbral_rojo,
                "umbral_ambar": args.umbral_ambar,
            }
        ]
    )

    hoja_importancia = pd.DataFrame(
        paquete["importancias"] if paquete else [], columns=["variable", "importancia"]
    )
    if not hoja_importancia.empty:
        hoja_importancia["importancia"] = hoja_importancia["importancia"].round(4)

    hoja_validacion = pd.DataFrame(
        paquete["observado_vs_predicho"] if paquete else [],
        columns=["potrero", "fecha_aforo", "observado", "predicho", "residuo"],
    )
    for columna in ("observado", "predicho", "residuo"):
        if columna in hoja_validacion.columns and not hoja_validacion.empty:
            hoja_validacion[columna] = hoja_validacion[columna].round(1)

    with pd.ExcelWriter(ruta, engine="openpyxl") as escritor:
        potreros.to_excel(escritor, sheet_name="Potreros", index=False)
        hoja_finca.to_excel(escritor, sheet_name="Finca", index=False)
        hoja_modelo.to_excel(escritor, sheet_name="Modelo_Info", index=False)
        hoja_importancia.to_excel(escritor, sheet_name="Modelo_Importancia", index=False)
        hoja_validacion.to_excel(escritor, sheet_name="Modelo_Validacion", index=False)


def cargar_modelo_guardado(ruta):
    if not os.path.isfile(ruta):
        return None
    try:
        return joblib.load(ruta)
    except Exception as error:
        print(f"Aviso: no se pudo leer el modelo guardado en '{ruta}' (se ignorara).\nDetalle: {error}")
        return None


def huella_del_aforo(aforo):
    """Identifica el estado actual del aforo (cuantas filas y la mas
    reciente) para decidir en modo auto si hay algo nuevo que aprender."""
    if aforo.empty:
        return 0, None
    ultima = max(aforo["fecha_aforo"])
    return int(len(aforo)), ultima.isoformat()


def main():
    args = parse_args()

    if args.umbral_rojo > args.umbral_ambar:
        print(
            f"Error: --umbral-rojo ({args.umbral_rojo:g}) no puede ser mayor que "
            f"--umbral-ambar ({args.umbral_ambar:g})."
        )
        sys.exit(1)
    if args.minimo_muestras_entrenamiento < 2:
        print("Error: --minimo-muestras-entrenamiento no puede ser menor que 2.")
        sys.exit(1)
    if args.ventana_emparejamiento_dias < 0:
        print("Error: --ventana-emparejamiento-dias no puede ser negativo.")
        sys.exit(1)

    ruta_modelo = args.modelo_guardado or os.path.join(
        os.path.dirname(os.path.abspath(args.salida)), "modelo_entrenado.joblib"
    )

    nombres = cargar_nombres_de_potreros(args.geojson)
    indices = cargar_indices(args.indices)
    aforo = cargar_aforo(args.aforo, args.calibracion_a, args.calibracion_b)
    clima = cargar_clima(args.clima)

    paquete_guardado = cargar_modelo_guardado(ruta_modelo)
    filas_aforo, ultima_fecha_aforo = huella_del_aforo(aforo)

    if args.modo == "predict":
        if paquete_guardado is None:
            print(
                "Error: se pidio --modo predict pero todavia no hay ningun modelo "
                f"entrenado en '{ruta_modelo}'.\n"
                "Registra aforo de campo y corre el script en --modo auto (o train) "
                "para entrenarlo, o deja que el backend lo haga por ti."
            )
            sys.exit(1)
        paquete = paquete_guardado
        print(f"Modo predict: se usa el modelo guardado ({paquete['algoritmo']}, entrenado el {paquete['entrenado_el']}).")
    else:
        hay_aforo_nuevo = paquete_guardado is None or (
            filas_aforo != paquete_guardado.get("n_filas_aforo")
            or ultima_fecha_aforo != paquete_guardado.get("ultima_fecha_aforo")
        )
        # Cambiar --variables (o --clima) tiene que reentrenar igual que un
        # aforo nuevo: si no, se predice con un modelo viejo que no
        # corresponde a la configuracion pedida, y las metricas que se
        # muestran son las de otra corrida.
        columnas_pedidas = columnas_de_entrada(clima is not None, args.variables)
        cambio_configuracion = paquete_guardado is not None and (
            list(paquete_guardado.get("columnas") or []) != list(columnas_pedidas)
        )
        debe_entrenar = args.modo == "train" or hay_aforo_nuevo or cambio_configuracion

        if not debe_entrenar:
            paquete = paquete_guardado
            print(
                f"Modo auto: no hay aforo nuevo desde el ultimo entrenamiento "
                f"({paquete['entrenado_el']}); se reutiliza el modelo guardado ({paquete['algoritmo']})."
            )
        else:
            if cambio_configuracion and not hay_aforo_nuevo and args.modo != "train":
                print("Modo auto: cambiaron las variables de entrada respecto al modelo guardado; se reentrena.")
            paquete = None
            emparejados = pd.DataFrame()
            if not aforo.empty:
                emparejados = emparejar_aforo_con_indices(
                    aforo, indices, args.ventana_emparejamiento_dias, clima
                )

            if len(emparejados) < args.minimo_muestras_entrenamiento:
                print(
                    f"No se entrena: hay {len(emparejados)} punto(s) de aforo emparejados con "
                    f"satelite y el minimo es {args.minimo_muestras_entrenamiento} "
                    "(entrenar con menos produciria un modelo sobreajustado y poco confiable).\n"
                    "Se usara la formula provisional de literatura para todos los potreros."
                )
                if args.modo == "train":
                    print("Aviso: se pidio --modo train, pero no hay datos suficientes para entrenar nada.")
            else:
                print(f"Entrenando con {len(emparejados)} punto(s) de aforo emparejados con satelite:")
                paquete = entrenar_modelo(
                    emparejados, clima is not None, args.minimo_muestras_entrenamiento, args.variables
                )

            if paquete is not None:
                paquete["n_filas_aforo"] = filas_aforo
                paquete["ultima_fecha_aforo"] = ultima_fecha_aforo
                os.makedirs(os.path.dirname(os.path.abspath(ruta_modelo)) or ".", exist_ok=True)
                joblib.dump(paquete, ruta_modelo)
                print(
                    f"Gana {paquete['algoritmo']} (menor RMSE). Modelo guardado en: "
                    f"{os.path.abspath(ruta_modelo)}"
                )
            elif paquete_guardado is not None:
                # Si ya habia un modelo entrenado y hoy no se pudo reentrenar,
                # es mejor seguir usando el viejo que caer a la formula.
                paquete = paquete_guardado
                print(f"Se sigue usando el modelo guardado anterior ({paquete['algoritmo']}, {paquete['entrenado_el']}).")

    potreros, conteo = predecir_potreros(nombres, indices, paquete, clima, args)
    guardar_salida(args.salida, potreros, paquete, args)

    print("\nListo.")
    print(f"Potreros procesados: {len(potreros)}")
    if paquete is not None:
        print(
            f"Modelo: {paquete['algoritmo']} | RMSE = {paquete['rmse']:.1f} kg MS/ha "
            f"({paquete['nrmse_pct']:.1f}% de la media) | R2 = {paquete['r2']:.3f} | "
            f"MAE = {paquete['mae']:.1f} | sesgo = {paquete['sesgo']:+.1f}"
        )
        print(
            f"  {paquete['n_muestras_entrenamiento']} muestras, {paquete['n_variables_entrada']} variables, "
            f"k-fold k={paquete['k_validacion']} | biomasa observada: "
            f"{paquete['biomasa_media']:.0f} +/- {paquete['biomasa_desv']:.0f} kg/ha "
            f"(rango {paquete['biomasa_min']:.0f}-{paquete['biomasa_max']:.0f}) | "
            f"entrenado el {paquete['entrenado_el']}"
        )
    else:
        print("Modelo: formula_provisional (aproximacion de literatura, todavia sin calibrar con aforo local).")
    for estado in ("verde", "ambar", "rojo", "sin_datos"):
        cantidad = int((potreros["estado"] == estado).sum())
        if cantidad:
            print(f"  {estado}: {cantidad} potrero(s)")
    print(
        f"Fuente de la prediccion: modelo_entrenado = {conteo['modelo_entrenado']}, "
        f"formula_provisional = {conteo['formula_provisional']}, sin datos = {conteo['sin_datos']}"
    )
    print(f"Archivo generado en: {os.path.abspath(args.salida)}")


if __name__ == "__main__":
    main()
