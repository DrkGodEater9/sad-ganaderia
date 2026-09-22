"""Prueba de integracion: corre entrenar_predecir.py como subproceso, tal
cual lo invoca backend/main.py, y verifica el Excel de salida. Cubre el
escenario de HOY (sin aforo todavia -> formula provisional) porque es
rapido y deterministico; el entrenamiento con Random Forest ya se prueba
por separado (mas rapido) en test_entrenar_predecir.py::test_entrenar_modelo_*.
"""

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "entrenar_predecir.py"


def _crear_geojson(ruta, nombres):
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"nombre": nombre},
                "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]]},
            }
            for nombre in nombres
        ],
    }
    ruta.write_text(json.dumps(geojson), encoding="utf-8")


def _crear_indices(ruta, filas):
    pd.DataFrame(filas).to_excel(ruta, sheet_name="Indices", index=False)


def test_cli_sin_aforo_usa_formula_provisional(tmp_path):
    geojson = tmp_path / "potreros.geojson"
    _crear_geojson(geojson, ["Potrero 1", "Potrero 2"])

    indices = tmp_path / "indices_historial.xlsx"
    _crear_indices(
        indices,
        [
            {"potrero": "Potrero 1", "fecha_escena_usada": "2026-09-10", "NDVI_mean": 0.45, "SAVI_mean": 0.25},
            {"potrero": "Potrero 2", "fecha_escena_usada": "2026-09-10", "NDVI_mean": 0.65, "SAVI_mean": 0.35},
        ],
    )

    salida = tmp_path / "potreros_estado.xlsx"
    resultado = subprocess.run(
        [
            sys.executable, str(SCRIPT),
            "--geojson", str(geojson),
            "--indices", str(indices),
            "--aforo", str(tmp_path / "aforo_campo.xlsx"),  # no existe todavia: es el escenario normal
            "--salida", str(salida),
            "--modelo-guardado", str(tmp_path / "modelo.joblib"),
            "--modo", "auto",
        ],
        capture_output=True,
        text=True,
    )

    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert salida.exists()

    potreros = pd.read_excel(salida, sheet_name="Potreros")
    assert set(potreros["nombre"]) == {"Potrero 1", "Potrero 2"}
    assert (potreros["fuente_prediccion"] == "formula_provisional").all()
    assert (potreros["biomasa_kg_ha"] > 0).all()

    modelo_info = pd.read_excel(salida, sheet_name="Modelo_Info").iloc[0]
    assert modelo_info["algoritmo"] == "formula_provisional"
    assert pd.isna(modelo_info["rmse"])


def test_cli_modo_predict_sin_modelo_falla_con_mensaje_claro(tmp_path):
    geojson = tmp_path / "potreros.geojson"
    _crear_geojson(geojson, ["Potrero 1"])
    indices = tmp_path / "indices_historial.xlsx"
    _crear_indices(indices, [{"potrero": "Potrero 1", "fecha_escena_usada": "2026-09-10", "NDVI_mean": 0.5}])

    resultado = subprocess.run(
        [
            sys.executable, str(SCRIPT),
            "--geojson", str(geojson),
            "--indices", str(indices),
            "--aforo", str(tmp_path / "aforo_campo.xlsx"),
            "--salida", str(tmp_path / "potreros_estado.xlsx"),
            "--modelo-guardado", str(tmp_path / "no_existe.joblib"),
            "--modo", "predict",
        ],
        capture_output=True,
        text=True,
    )

    assert resultado.returncode != 0
    assert "Traceback" not in resultado.stdout + resultado.stderr
    assert "predict" in (resultado.stdout + resultado.stderr).lower()


def test_cli_entrena_con_aforo_suficiente_y_escribe_importancias(tmp_path):
    nombres = [f"Potrero {i}" for i in range(10)]
    geojson = tmp_path / "potreros.geojson"
    _crear_geojson(geojson, nombres)

    indices = tmp_path / "indices_historial.xlsx"
    _crear_indices(
        indices,
        [
            {"potrero": n, "fecha_escena_usada": "2026-09-10", "NDVI_mean": 0.3 + 0.04 * i, "SAVI_mean": 0.2 + 0.02 * i}
            for i, n in enumerate(nombres)
        ],
    )

    aforo = tmp_path / "aforo_campo.xlsx"
    pd.DataFrame(
        {
            "potrero": nombres,
            "fecha": ["2026-09-11"] * len(nombres),
            "altura_cm_1": [10 + i for i in range(len(nombres))],
            "altura_cm_2": [10 + i for i in range(len(nombres))],
            "altura_cm_3": [10 + i for i in range(len(nombres))],
        }
    ).to_excel(aforo, sheet_name="Aforo", index=False)

    salida = tmp_path / "potreros_estado.xlsx"
    resultado = subprocess.run(
        [
            sys.executable, str(SCRIPT),
            "--geojson", str(geojson),
            "--indices", str(indices),
            "--aforo", str(aforo),
            "--salida", str(salida),
            "--modelo-guardado", str(tmp_path / "modelo.joblib"),
            "--minimo-muestras-entrenamiento", "8",
            "--modo", "train",
        ],
        capture_output=True,
        text=True,
    )

    assert resultado.returncode == 0, resultado.stdout + resultado.stderr

    potreros = pd.read_excel(salida, sheet_name="Potreros")
    assert (potreros["fuente_prediccion"] == "modelo_entrenado").all()

    modelo_info = pd.read_excel(salida, sheet_name="Modelo_Info").iloc[0]
    assert modelo_info["algoritmo"] in ("random_forest", "regresion_lineal")
    # Los datos sinteticos son una relacion perfectamente lineal (a proposito,
    # para que la prueba sea deterministica): regresion lineal puede llegar a
    # RMSE ~0, asi que solo se verifica que las dos metricas quedaron.
    assert modelo_info["rmse_random_forest"] >= 0
    assert modelo_info["rmse_regresion_lineal"] >= 0

    importancias = pd.read_excel(salida, sheet_name="Modelo_Importancia")
    assert len(importancias) > 0
    assert importancias["importancia"].sum() == pytest.approx(1.0, abs=0.01)
    assert list(importancias["importancia"]) == sorted(importancias["importancia"], reverse=True)


def test_cli_potrero_sin_indices_queda_sin_datos(tmp_path):
    geojson = tmp_path / "potreros.geojson"
    _crear_geojson(geojson, ["Potrero Con Datos", "Potrero Nuevo Sin Escanear"])
    indices = tmp_path / "indices_historial.xlsx"
    _crear_indices(indices, [{"potrero": "Potrero Con Datos", "fecha_escena_usada": "2026-09-10", "NDVI_mean": 0.5}])
    salida = tmp_path / "potreros_estado.xlsx"

    resultado = subprocess.run(
        [
            sys.executable, str(SCRIPT),
            "--geojson", str(geojson),
            "--indices", str(indices),
            "--aforo", str(tmp_path / "aforo_campo.xlsx"),
            "--salida", str(salida),
            "--modelo-guardado", str(tmp_path / "modelo.joblib"),
            "--modo", "auto",
        ],
        capture_output=True,
        text=True,
    )

    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    potreros = pd.read_excel(salida, sheet_name="Potreros").set_index("nombre")
    assert potreros.loc["Potrero Nuevo Sin Escanear", "estado"] == "sin_datos"
    assert potreros.loc["Potrero Con Datos", "estado"] in ("verde", "ambar", "rojo")
