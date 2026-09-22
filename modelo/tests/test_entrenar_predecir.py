"""Pruebas de la logica pura del modelo: formula provisional, semaforo,
calibracion altura->biomasa, parseo de clima NASA POWER y emparejamiento
aforo<->indices por fecha. No entrena nada aqui (eso se prueba aparte, es
mas lento) -- son las piezas donde un error se traduce directo en una
recomendacion equivocada para el productor."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import entrenar_predecir as ep


def test_clasificar_estado_limites():
    assert ep.clasificar_estado(None, 300, 500) == "sin_datos"
    assert ep.clasificar_estado(299.9, 300, 500) == "rojo"
    assert ep.clasificar_estado(300, 300, 500) == "ambar"  # el limite inferior ya cuenta como ambar
    assert ep.clasificar_estado(499.9, 300, 500) == "ambar"
    assert ep.clasificar_estado(500, 300, 500) == "verde"


def test_formula_provisional_usa_ndvi():
    biomasa = ep.biomasa_formula_provisional({"NDVI_mean": 0.45})
    # ver modelo/README.md: NDVI 0.45 -> ~308 kg/ha
    assert 290 < biomasa < 320


def test_formula_provisional_cae_a_savi_si_falta_ndvi():
    con_ndvi = ep.biomasa_formula_provisional({"NDVI_mean": 0.5})
    con_savi_equivalente = ep.biomasa_formula_provisional({"NDVI_mean": None, "SAVI_mean": 0.5 / ep.SAVI_A_NDVI})
    assert con_savi_equivalente == pytest.approx(con_ndvi, rel=1e-6)


def test_formula_provisional_sin_ndvi_ni_savi_es_none():
    assert ep.biomasa_formula_provisional({}) is None


def test_formula_provisional_respeta_tope_de_cordura():
    biomasa = ep.biomasa_formula_provisional({"NDVI_mean": 1.0})
    assert biomasa <= ep.FORMULA_BIOMASA_MAXIMA


def test_cargar_aforo_calibracion_lineal(tmp_path):
    ruta = tmp_path / "aforo.xlsx"
    df = pd.DataFrame(
        {
            "potrero": ["Potrero 1"],
            "fecha": ["2026-09-18"],
            "altura_cm_1": [12.0],
            "altura_cm_2": [14.0],
            "altura_cm_3": [13.0],
        }
    )
    df.to_excel(ruta, sheet_name="Aforo", index=False)

    resultado = ep.cargar_aforo(str(ruta), calibracion_a=50.0, calibracion_b=15.0)
    assert len(resultado) == 1
    assert resultado.loc[0, "altura_cm_promedio"] == pytest.approx(13.0)
    assert resultado.loc[0, "biomasa_kg_ms_ha"] == pytest.approx(50.0 + 15.0 * 13.0)


def test_cargar_aforo_descarta_filas_invalidas(tmp_path):
    ruta = tmp_path / "aforo.xlsx"
    df = pd.DataFrame(
        {
            "potrero": ["Potrero 1", "Potrero 2"],
            "fecha": ["2026-09-18", "fecha-invalida"],
            "altura_cm_1": [12.0, 12.0],
            "altura_cm_2": [14.0, 14.0],
            "altura_cm_3": [13.0, 13.0],
        }
    )
    df.to_excel(ruta, sheet_name="Aforo", index=False)

    resultado = ep.cargar_aforo(str(ruta), calibracion_a=50.0, calibracion_b=15.0)
    assert len(resultado) == 1
    assert resultado.loc[0, "potrero"] == "Potrero 1"


def test_cargar_aforo_archivo_inexistente_no_es_error(tmp_path):
    resultado = ep.cargar_aforo(str(tmp_path / "no_existe.xlsx"), 50.0, 15.0)
    assert resultado.empty


def test_cargar_clima_formato_nasa_power_con_cabecera(tmp_path):
    ruta = tmp_path / "clima.csv"
    ruta.write_text(
        "-BEGIN HEADER-\n"
        "Dates: 03/01/2025 through 03/02/2025\n"
        "-END HEADER-\n"
        "YEAR,DOY,T2M,PRECTOTCORR\n"
        "2025,60,27.97,2.92\n"
        "2025,61,-999,0.39\n",  # -999 = dato faltante
        encoding="utf-8",
    )
    clima = ep.cargar_clima(str(ruta))
    assert clima is not None
    assert len(clima) == 2
    assert pd.isna(clima.loc[clima["fecha"] == pd.Timestamp("2025-03-02"), "T2M"].iloc[0])
    assert clima.loc[clima["fecha"] == pd.Timestamp("2025-03-01"), "T2M"].iloc[0] == pytest.approx(27.97)


def test_cargar_clima_archivo_inexistente_no_revienta(tmp_path):
    assert ep.cargar_clima(str(tmp_path / "no_existe.csv")) is None


def test_cargar_clima_ninguno_si_no_se_paso():
    assert ep.cargar_clima(None) is None


def test_resumen_clima_ventana_30_dias():
    fechas = pd.date_range("2026-01-01", periods=40, freq="D")
    clima = pd.DataFrame({"fecha": fechas, "T2M": 20.0, "PRECTOTCORR": 1.0})
    precip, temp = ep.resumen_clima(clima, pd.Timestamp("2026-01-30"))
    assert precip == pytest.approx(30.0)  # 30 dias * 1mm/dia
    assert temp == pytest.approx(20.0)


def test_resumen_clima_sin_datos_en_ventana():
    clima = pd.DataFrame({"fecha": pd.date_range("2020-01-01", periods=5), "T2M": 20.0, "PRECTOTCORR": 1.0})
    precip, temp = ep.resumen_clima(clima, pd.Timestamp("2026-01-01"))
    assert np.isnan(precip) and np.isnan(temp)


def test_emparejar_aforo_con_indices_respeta_ventana():
    aforo = pd.DataFrame(
        {
            "potrero": ["Potrero 1", "Potrero 1"],
            "fecha_aforo": [pd.Timestamp("2026-09-18"), pd.Timestamp("2026-09-18")],
            "altura_cm_promedio": [13.0, 13.0],
            "biomasa_kg_ms_ha": [245.0, 245.0],
        }
    )
    indices_cerca = pd.DataFrame(
        {"potrero": ["Potrero 1"], "fecha_escena": [pd.Timestamp("2026-09-20")], "NDVI_mean": [0.45]}
    )
    for columna in ep.COLUMNAS_INDICES:
        if columna not in indices_cerca.columns:
            indices_cerca[columna] = np.nan

    emparejados = ep.emparejar_aforo_con_indices(aforo.iloc[[0]], indices_cerca, ventana_dias=15, clima=None)
    assert len(emparejados) == 1

    indices_lejos = indices_cerca.copy()
    indices_lejos["fecha_escena"] = pd.Timestamp("2026-01-01")
    descartados = ep.emparejar_aforo_con_indices(aforo.iloc[[1]], indices_lejos, ventana_dias=15, clima=None)
    assert descartados.empty


def test_huella_del_aforo():
    assert ep.huella_del_aforo(pd.DataFrame(columns=["fecha_aforo"])) == (0, None)
    df = pd.DataFrame({"fecha_aforo": [pd.Timestamp("2026-09-01"), pd.Timestamp("2026-09-18")]})
    cantidad, ultima = ep.huella_del_aforo(df)
    assert cantidad == 2
    assert ultima == "2026-09-18T00:00:00"


def test_entrenar_modelo_menos_del_minimo_devuelve_none():
    emparejados = pd.DataFrame({"NDVI_mean": [0.3, 0.4, 0.5], "biomasa_kg_ms_ha": [200.0, 260.0, 320.0]})
    assert ep.entrenar_modelo(emparejados, usar_clima=False, minimo_muestras=8) is None


def test_entrenar_modelo_con_datos_suficientes_elige_un_ganador():
    rng = np.random.default_rng(42)
    n = 20
    ndvi = rng.uniform(0.3, 0.7, n)
    # Relacion casi lineal con poco ruido: ambos algoritmos deberian poder
    # aprenderla, y el resultado debe traer metricas razonables.
    biomasa = 50 + 15 * (10 + 20 * ndvi) + rng.normal(0, 5, n)
    emparejados = pd.DataFrame({"NDVI_mean": ndvi, "SAVI_mean": ndvi / ep.SAVI_A_NDVI, "biomasa_kg_ms_ha": biomasa})

    paquete = ep.entrenar_modelo(emparejados, usar_clima=False, minimo_muestras=8)

    assert paquete is not None
    assert paquete["algoritmo"] in ("random_forest", "regresion_lineal")
    assert paquete["n_muestras_entrenamiento"] == n
    assert paquete["rmse"] < biomasa.std()  # mejor que solo predecir el promedio
    assert -1.0 <= paquete["r2"] <= 1.0

    # Metricas de ambos algoritmos, no solo el ganador.
    assert set(paquete["metricas_comparacion"]) == {"random_forest", "regresion_lineal"}
    assert paquete["metricas_comparacion"][paquete["algoritmo"]]["rmse"] == pytest.approx(paquete["rmse"])

    # Importancias: una fila por variable realmente usada (las que no
    # estaban en los datos se descartan), ordenadas de mayor a menor, y
    # que sumen 1 (estan normalizadas).
    assert {fila["variable"] for fila in paquete["importancias"]} == {"NDVI_mean", "SAVI_mean"}
    pesos = [fila["importancia"] for fila in paquete["importancias"]]
    assert pesos == sorted(pesos, reverse=True)
    assert sum(pesos) == pytest.approx(1.0, rel=1e-3)
