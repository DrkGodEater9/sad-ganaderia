# Reporte técnico — SAD (Sistema de Apoyo a Decisiones) para manejo de potreros

Documento de referencia para redactar la metodología y resultados de un artículo académico.
Generado el 2026-09-21. Todos los datos, métricas y comportamientos descritos fueron
verificados leyendo el código fuente y ejecutando el sistema, no reportados de memoria.

---

## Nota previa sobre el alcance de este documento

**Importante para no atribuir mal la autoría en el artículo.** Este repositorio ya existía
antes de la sesión de trabajo que produjo este reporte. El historial de git muestra dos
commits previos (`fa9ddba` "Version inicial: SAD", `f2b80e8` "Renombrar el proyecto a
sad-ganaderia") que ya contenían las cinco piezas del sistema. En esta sesión **no se creó
ningún archivo fuente nuevo**: se modificaron 12 archivos existentes
(1331 líneas añadidas, 128 eliminadas).

A lo largo del documento se marca con **[MODIFICADO EN ESTA SESIÓN]** lo que cambió ahora,
y con **[PREEXISTENTE]** lo que ya estaba. Donde describo decisiones de diseño
preexistentes, las reporto tal como están implementadas, pero no puedo dar fe de la
justificación original de quien las tomó.

**Tres advertencias que afectan directamente lo que se puede afirmar en el artículo** y que
se detallan en las secciones 2.1, 3.2 y 5.6:

1. ~~SAVI y EVI están mal calculados~~ → **DEFECTO CORREGIDO** (sección 2.1.1). Se detectó que
   SAVI era numéricamente idéntico a 1.5 × NDVI y que EVI estaba saturado, por un problema de
   escala de reflectancia. Se corrigió, se regeneró todo el historial de índices y se
   reentrenó. **Los valores de SAVI y EVI de cualquier versión anterior de este documento o de
   los datos son inválidos.** Los actuales son correctos.
2. **No existe** el flujo de recalibración con pares altura-peso que asume la pregunta 3.
   Los coeficientes siguen siendo los provisionales y desde la app no hay forma de cambiarlos.
3. **No existe partición train/test** como asume la pregunta 5. La validación es k-fold
   cruzada sobre el total de la muestra.

**La limitación de fondo sigue siendo el tamaño muestral (n = 8)**, y esa no se corrige con
código. Ver sección 5.7.

---

## 1. Arquitectura general

El sistema son cinco piezas que se comunican por **archivos** (GeoJSON y Excel), no por base
de datos. Esa es la decisión estructural central: no hay motor de base de datos en ninguna
parte; el productor puede abrir cualquier archivo intermedio en Excel, revisarlo y corregirlo
a mano.

### 1.1 Las piezas

| Pieza | Ubicación | Qué hace |
|---|---|---|
| App de dibujo de potreros | `src/` (vista "Dibujar potreros") | Interfaz de canvas para dibujar polígonos de potreros sobre un lienzo, calcular su área y exportarlos como GeoJSON. |
| Script de Earth Engine | `earth-engine/extraer_indices.py` | Consulta Google Earth Engine, busca escena Sentinel-2 utilizable y calcula 5 índices de vegetación por potrero. CLI independiente. |
| Script del modelo | `modelo/entrenar_predecir.py` | Empareja aforo de campo con índices satelitales, entrena y compara dos algoritmos, predice biomasa y clasifica el semáforo. CLI independiente. |
| Backend | `backend/main.py` | API FastAPI. Capa fina de orquestación: invoca los dos scripts anteriores como subprocesos y lee/escribe los mismos archivos Excel que ellos. |
| App del productor | `src/` (vistas "Mis potreros", "Registrar medición", "Estadísticas") | Interfaz móvil para ver el estado de los potreros, registrar mediciones de altura de pasto y consultar las estadísticas del modelo. |

Las cinco piezas viven en un solo repositorio pero son **deliberadamente desacoplables**: los
dos scripts de Python corren solos desde la línea de comandos sin el backend, y el backend
no reimplementa su lógica — los llama con `subprocess.run()` usando `sys.executable`.

### 1.2 Flujo de datos completo

```
  [Dibujar potreros]  ──► POST /api/geojson ──►  potreros.geojson  (raíz del repo)
                                                        │
                                                        ▼
  [Registrar medición] ──► POST /api/potreros/{n}/aforo ──► backend/data/aforo_campo.xlsx
                                                        │
  "Actualizar recomendaciones"                          │
        │                                               │
        ▼                                               │
  POST /api/predecir                                    │
        │                                               │
        ├─1─► subprocess: earth-engine/extraer_indices.py
        │         └─► backend/data/_indices_temp.xlsx (archivo de paso)
        │                    └─► se ANEXA a backend/data/indices_historial.xlsx
        │                        (este archivo solo crece, nunca se sobrescribe)
        │                                               │
        └─2─► subprocess: modelo/entrenar_predecir.py ◄─┘
                  │  lee: potreros.geojson, indices_historial.xlsx,
                  │       aforo_campo.xlsx, clima_nasa_power.csv (opcional)
                  │
                  ├─► backend/data/modelo_entrenado.joblib  (modelo serializado)
                  └─► backend/data/potreros_estado.xlsx     (SOBRESCRITO completo)
                            │   hojas: Potreros, Finca, Modelo_Info,
                            │          Modelo_Importancia, Modelo_Validacion
                            ▼
              GET /api/potreros ──► [Mis potreros] y [Estadísticas]
```

`potreros_estado.xlsx` es la **fuente de verdad** que lee la app: el backend nunca recalcula
la biomasa, solo sirve lo que el script del modelo dejó escrito allí.

### 1.3 Cambios de diseño respecto a lo pedido originalmente

No tengo acceso al enunciado original del proyecto, así que no puedo comparar contra él.
Lo que sí puedo documentar son las desviaciones respecto a lo que **se pidió en esta sesión**:

- **Se pidió** "ampliar la ventana de días hasta encontrar datos". **Se hizo otra cosa**:
  ampliar la ventana no resolvía el problema, porque el algoritmo elegía siempre la escena
  más cercana en fecha que pasara el filtro de nubes, y esa (la de hoy, a 0 días) ganaba
  sin importar cuán ancha fuera la ventana. Se rediseñó la selección de escena (sección 2.3).
  La ventana también se amplió, pero fue secundario.
- **Se pidió** generar datos de entrenamiento asumiendo que "las fechas y predicciones son
  muy similares todos los años". **No se hizo**: fabricar registros de aforo para fechas sin
  medición real habría inventado la variable objetivo del modelo. En su lugar se trajeron los
  índices satelitales **reales** de las fechas en que sí hubo medición (sección 5.7).

---

## 2. Extracción de índices de vegetación

Archivo: `earth-engine/extraer_indices.py`. Colección:
`COPERNICUS/S2_SR_HARMONIZED` (Sentinel-2 Surface Reflectance, armonizada).

### 2.1 Fórmulas implementadas — código exacto

Código actual, ya con la corrección de escala de la sección 2.1.1:

```python
INDICES = ["NDVI", "GNDVI", "NDRE", "SAVI", "EVI"]
CLASES_SCL_VALIDAS = [4, 5, 7]
ESCALA_REFLECTANCIA = 10000

def enmascarar_y_calcular_indices(imagen):
    scl = imagen.select("SCL")
    mascara_valida = scl.eq(CLASES_SCL_VALIDAS[0])
    for clase in CLASES_SCL_VALIDAS[1:]:
        mascara_valida = mascara_valida.Or(scl.eq(clase))
    imagen = imagen.updateMask(mascara_valida)

    # S2_SR_HARMONIZED entrega reflectancia entera escalada x10000.
    reflectancia = imagen.divide(ESCALA_REFLECTANCIA)

    ndvi  = reflectancia.normalizedDifference(["B8", "B4"]).rename("NDVI")
    gndvi = reflectancia.normalizedDifference(["B8", "B3"]).rename("GNDVI")
    ndre  = reflectancia.normalizedDifference(["B8", "B5"]).rename("NDRE")

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
```

En notación matemática, con las bandas de Sentinel-2
(B2 = azul 490 nm, B3 = verde 560 nm, B4 = rojo 665 nm, B5 = borde rojo 705 nm, B8 = NIR 842 nm):

- **NDVI** = (B8 − B4) / (B8 + B4)
- **GNDVI** = (B8 − B3) / (B8 + B3)
- **NDRE** = (B8 − B5) / (B8 + B5)
- **SAVI** = 1.5 × (B8 − B4) / (B8 + B4 + 0.5)   ← con L = 0.5
- **EVI** = 2.5 × (B8 − B4) / (B8 + 6·B4 − 7.5·B2 + 1), recortado a [−1, 1]

### 2.1.1 Defecto de escala en SAVI y EVI — DETECTADO Y CORREGIDO

Esta subsección documenta un error real que estuvo presente en todos los datos generados
hasta el 2026-09-21 a las 23:45 aproximadamente. **Se corrigió, se regeneró el historial
completo y se reentrenó.** Se deja documentado porque es material de la sección de
limitaciones/control de calidad y porque invalida cualquier cifra de SAVI o EVI anterior.

#### El error

`COPERNICUS/S2_SR_HARMONIZED` entrega la reflectancia **escalada por 10000** (valores enteros
típicos de 1000–4000), no en el rango 0–1. NDVI, GNDVI y NDRE usan `normalizedDifference()`,
que es un cociente y por tanto **invariante a la escala**: esos tres siempre estuvieron
correctos y **sus valores no cambiaron con la corrección**.

Pero SAVI y EVI tienen **constantes aditivas** (el L = 0.5 de SAVI y el +1 de EVI) que solo
significan algo con reflectancia en [0, 1]. Frente a valores de orden 10³ quedaban anuladas:

- **SAVI** degeneraba en 1.5 × (NIR−RED)/(NIR+RED) = **exactamente 1.5 × NDVI**. El ajuste de
  suelo L = 0.5 —lo único que distingue SAVI de NDVI— quedaba sin efecto.
- **EVI** perdía el término de estabilización +1 y su denominador
  (NIR + 6·RED − 7.5·BLUE) se acercaba a cero o se volvía negativo, produciendo valores
  extremos que el `.clamp(-1, 1)` recortaba contra el tope.

#### La corrección

Una línea: dividir la imagen enmascarada por 10000 antes de evaluar las expresiones
(`reflectancia = imagen.divide(ESCALA_REFLECTANCIA)`), y evaluar los cinco índices sobre esa
imagen escalada. Tras corregir, se **borró y regeneró el historial completo** (8 consultas a
Earth Engine: las 7 fechas de aforo más la de hoy) y se reentrenó el modelo.

#### Verificación empírica antes y después

| Comprobación | Antes (110 filas con datos) | Después (80 filas) |
|---|---|---|
| Cociente SAVI_mean / NDVI_mean | **1.499671 – 1.499848** (constante) | **0.4698 – 0.7467** (varía) |
| EVI_mean, rango | −0.7225 a 1.0 | **0.1287 – 0.4324** (media 0.3251) |
| Filas con EVI_mean ≥ 0.99 | **71 de 110 (64.5 %)** | **0 de 80** |

Los valores actuales de EVI (0.13–0.43) son físicamente plausibles para pastura tropical; los
anteriores, pegados a 1.0, no lo eran. SAVI ya no es una réplica de NDVI.

#### Efecto sobre el análisis

El cambio **mejoró sustancialmente los modelos que usan SAVI o EVI** y dejó intactos los que
no (porque NDVI no cambió):

| Subconjunto (regresión lineal) | R² antes | R² después |
|---|---|---|
| Todo (12 variables) | −0.649 | **+0.225** |
| Solo índices (10 variables) | +0.190 | **+0.368** |
| NDVI + NDVI_sd + lluvia (3) | +0.424 | +0.424 (no usa SAVI/EVI) |

Y cambió el orden de importancia de los índices: **EVI_mean pasó de ser el peor predictor
satelital (r = −0.147) al mejor (r = +0.407)** — ver la tabla de correlaciones en 5.6.

La constante `SAVI_A_NDVI` de `modelo/entrenar_predecir.py` se actualizó de 1.8 a **1.69**,
que es el cociente NDVI/SAVI medido sobre las 80 filas del historial corregido
(n = 80, rango 1.339–2.129, media 1.693, mediana 1.708). Ya no es un número sin respaldo,
pero **sigue siendo una aproximación local de esta finca**, no una constante universal:
depende del nivel de reflectancia. En la práctica es una ruta poco frecuente, porque NDVI y
SAVI salen de la misma imagen enmascarada y casi siempre se anulan juntos.

### 2.1.2 Nota sobre resolución espacial

`reduceRegions()` se ejecuta con `scale=10` (10 m). B2, B3, B4 y B8 son nativamente de 10 m,
pero **B5 (borde rojo) es de 20 m** y Earth Engine la remuestrea a 10 m. NDRE, por tanto,
se calcula sobre una banda remuestreada. No es un error, pero conviene declararlo en la
metodología.

### 2.2 Máscara de nubes y agua

Se usa la banda **SCL** (Scene Classification Layer) de Sentinel-2 Level-2A. Se **conservan
únicamente tres clases**:

| Clase SCL | Significado | ¿Se conserva? |
|---|---|---|
| 4 | Vegetación | ✅ sí |
| 5 | Suelo desnudo | ✅ sí |
| 7 | No vegetado / nubes de baja probabilidad | ✅ sí |
| 0,1,2,3,6,8,9,10,11 | Sin datos, saturado, sombra, sombra de nube, **agua**, nube media/alta, cirros, nieve | ❌ excluidas |

Todo píxel fuera de {4, 5, 7} se enmascara con `updateMask()`. Esto excluye explícitamente
agua (clase 6), sombras (2 y 3), nubes (8, 9, 10) y nieve/hielo (11).

Es una máscara **estricta**: conservar solo 3 de 12 clases. Esa severidad es la causa directa
de que escenas que pasan el filtro grueso de nubosidad queden sin un solo píxel válido sobre
los potreros (ver 2.3).

### 2.3 Lógica de selección de escena y emparejamiento **[MODIFICADO EN ESTA SESIÓN]**

#### Comportamiento anterior (el que estaba antes de esta sesión)

Se filtraba la colección por rango de fechas, intersección con el área y
`CLOUDY_PIXEL_PERCENTAGE < umbral`; se ordenaba por cercanía temporal y **se tomaba la
primera** (`coleccion.first()`). Si esa escena resultaba no tener píxeles válidos sobre los
potreros después del enmascarado SCL, todos los índices salían nulos y no había reintento.

**Por qué fallaba:** `CLOUDY_PIXEL_PERCENTAGE` es el porcentaje de nubes del **tile completo
de Sentinel-2 (110 × 110 km)**, no del área de la finca. Una escena puede tener 30 % de nubes
a nivel de tile y aun así tener los potreros —que ocupan unas pocas hectáreas— justo debajo de
una nube o su sombra.

#### Comportamiento actual

```
1. Construir la colección candidata:
     COPERNICUS/S2_SR_HARMONIZED
       .filterDate(fecha − ventana_dias, fecha + ventana_dias + 1)
       .filterBounds(geometría unión de todos los potreros)
       .filter(CLOUDY_PIXEL_PERCENTAGE < umbral_nubes)
       .map(anotar cada imagen con dias_diferencia = |fecha_escena − fecha_objetivo|)
       .sort("dias_diferencia")          # ascendente: la más cercana primero
       .limit(MAX_ESCENAS_CANDIDATAS)    # tope de 25

2. Si la colección está vacía  ->  error explicativo + sys.exit(1),
   sugiriendo aumentar --ventana-dias o --umbral-nubes.

3. Recorrer las candidatas en orden de cercanía temporal. Para cada una:
     a. aplicar máscara SCL y calcular los 5 índices
     b. reduceRegions() sobre TODOS los potreros de una sola llamada (scale=10)
     c. para cada potrero aún pendiente:
          si NDVI_mean o SAVI_mean no es nulo -> se le asigna esta escena
                                                 y sale de "pendientes"
          si ambos son nulos                  -> sigue pendiente, se probará
                                                 con la siguiente escena
     d. si ya no quedan pendientes -> cortar el bucle

4. Si ningún potrero consiguió índices en ninguna candidata ->
   error explicativo + sys.exit(1).

5. Los potreros que quedaron pendientes al agotar las candidatas se escriben
   con índices vacíos y la fecha de la escena más cercana. El modelo los
   interpreta como "sin_datos".
```

**Consecuencia metodológica importante:** distintos potreros pueden quedar emparejados con
**escenas de fechas distintas** en la misma corrida. Cada fila del resultado lleva su propia
`fecha_escena_usada` y `dias_diferencia_con_fecha_objetivo`. El criterio de diseño fue que un
dato real de hace unos días es preferible a ningún dato. Esto debe declararse en la
metodología: la "fecha de observación" no es única por corrida.

#### Parámetros y sus valores

| Parámetro | Default del script | Valor efectivo en esta finca | Dónde se configura |
|---|---|---|---|
| `--ventana-dias` | 10 | **45** | `EE_VENTANA_DIAS` en `backend/.env` |
| `--umbral-nubes` | 40 | **85** | `EE_UMBRAL_NUBES` en `backend/.env` |
| `MAX_ESCENAS_CANDIDATAS` | 25 | 25 | constante en el código, no configurable |

Los valores 45/85 son considerablemente más permisivos que los defaults; se subieron porque
con 10/40 y con 15/60 no se encontraba ninguna escena utilizable (ver 2.4). Un umbral de
nubes de 85 % a nivel de tile es laxo y **debe declararse explícitamente en el artículo**: lo
que garantiza la calidad del dato no es ese filtro sino la máscara SCL por píxel.

### 2.4 Ejecuciones reales contra la API de Earth Engine

**Sí, el script se ejecutó contra la API real de Google Earth Engine en múltiples ocasiones
durante esta sesión.** Proyecto de Google Cloud: `evident-hexagon-483917-k9`. No son
resultados simulados.

**Finca de estudio:** 10 potreros. Centroide 4.6158 °N, −72.14302 °W (departamento del Meta,
Llanos Orientales, Colombia). Bounding box: lon −72.17564 a −72.13048, lat 4.58213 a 4.62763.

#### Cronología de ejecuciones

| # | Parámetros | Resultado |
|---|---|---|
| 1 | ventana 10 d, nubes < 40 % | **Fallo.** Ninguna escena entre 2026-09-11 y 2026-10-02 cumplía las condiciones. |
| 2 | ventana 15 d, nubes < 60 % | **Fallo.** Ninguna escena entre 2026-09-06 y 2026-10-07. |
| 3 | ventana 45 d, nubes < 85 % (código anterior) | **Éxito parcial y engañoso.** Encontró la escena del 2026-09-21 (0 días de diferencia) y devolvió HTTP 200, pero **los 5 índices salieron nulos para los 10 potreros**: la escena pasó el filtro de tile pero los potreros estaban bajo nube/sombra. Los 10 potreros quedaron en `sin_datos`. |
| 4 | ventana 45 d, nubes < 85 % (código nuevo, con reintento) | **Éxito.** Descartó dos escenas del 2026-09-21 por falta de píxeles válidos y se quedó con la del **2026-09-16** (4 días de diferencia), que dio índices utilizables para **los 10 potreros**. |

#### Resultado de la ejecución #4 (escena 2026-09-16) — valores ya corregidos

Estos son los valores tras la corrección de escala de 2.1.1. **Son los que se deben usar**;
los de cualquier versión anterior están mal en SAVI y EVI.

| Potrero | NDVI_mean | SAVI_mean | EVI_mean | GNDVI_mean | NDRE_mean |
|---|---|---|---|---|---|
| Potrero_1 | 0.5508 | 0.2906 | 0.2939 | 0.5479 | 0.2753 |
| Potrero_2 | 0.5381 | 0.3484 | 0.3990 | 0.5031 | 0.3216 |
| Potrero_3 | 0.4678 | 0.3167 | 0.4044 | 0.4331 | 0.2819 |
| Potrero_4 | 0.5988 | 0.3655 | 0.3871 | 0.5621 | 0.3357 |
| Potrero_5 | 0.3453 | 0.2578 | 0.3867 | 0.3263 | 0.2031 |
| Potrero_6 | 0.5724 | 0.2931 | 0.2996 | 0.5535 | 0.2975 |
| Potrero_7 | 0.5181 | 0.3127 | 0.3194 | 0.5304 | 0.2854 |
| Potrero_8 | 0.5527 | 0.3241 | 0.3213 | 0.5702 | 0.3111 |
| Potrero_9 | 0.4465 | 0.2827 | 0.3134 | 0.4579 | 0.2373 |
| Potrero_10 | 0.4730 | 0.2877 | 0.3025 | 0.5010 | 0.2416 |

Los rangos (NDVI 0.35–0.60, SAVI 0.26–0.37, EVI 0.29–0.40) son todos plausibles para pastura
tropical.

#### Backfill histórico

Se ejecutó un **backfill** de las 7 fechas históricas en que hubo aforo de campo, con ventana
15 d (ajustada para que coincida con la ventana de emparejamiento del modelo) y nubes < 85 %.
**Las 7 tuvieron éxito, los 10 potreros en cada una.** El backfill se corrió dos veces: una
antes de la corrección de 2.1.1 y otra después, regenerando el historial desde cero.

| Fecha de aforo objetivo | Escena Sentinel-2 encontrada | Δ días |
|---|---|---|
| 2025-01-02 | 2024-12-25 | 8 |
| 2025-01-03 | 2025-01-09 | 6 |
| 2025-02-03 | 2025-02-03 | **0** |
| 2025-02-12 | 2025-02-13 | 1 |
| 2025-05-16 | 2025-05-11 | 5 |
| 2025-07-08 | 2025-07-13 y 2025-07-18 | 5 / 10 |
| 2026-01-05 | 2026-01-09 | 4 |

Todas dentro de la ventana de emparejamiento de 15 días del modelo.

**Estado del historial tras la regeneración:** `indices_historial.xlsx` quedó con **80 filas**
(8 consultas × 10 potreros), **todas con índices utilizables** — ya no hay filas nulas, porque
la regeneración partió de cero y la lógica de reintento por potrero de 2.3 resolvió los 10 en
cada fecha. Cubre **9 fechas de escena distintas**: 2024-12-25, 2025-01-09, 2025-02-03,
2025-02-13, 2025-05-11, 2025-07-13, 2025-07-18, 2026-01-09 y 2026-09-16.

> **Nota sobre duplicados.** El archivo está diseñado para solo crecer, así que cada corrida
> de `/api/predecir` añade 10 filas aunque sea el mismo día y la misma escena. Tras una
> corrida posterior de verificación el archivo pasó a 90 filas, con la escena del 2026-09-16
> repetida. No afecta a los resultados (el modelo toma la fila más reciente por potrero, y las
> duplicadas son idénticas), pero conviene saberlo al contar filas y es un detalle a limpiar
> si el historial se publica como dataset.

**Errores encontrados y no resueltos:** ninguno pendiente en la ejecución de EE. Se observa un
`DeprecationWarning` de `datetime.utcfromtimestamp()` (deprecado en Python 3.12+), que no
afecta el resultado pero conviene corregir.

---

## 3. Conversión altura → biomasa

### 3.1 Fórmula y coeficientes actuales

```python
CALIBRACION_A = 50.0
CALIBRACION_B = 15.0

# en cargar_aforo():
df["altura_cm_promedio"] = df[["altura_cm_1","altura_cm_2","altura_cm_3"]].mean(axis=1, skipna=True)
df["biomasa_kg_ms_ha"]   = calibracion_a + calibracion_b * df["altura_cm_promedio"]
```

**biomasa (kg MS/ha) = 50 + 15 × altura_promedio (cm)**

**Siguen siendo los coeficientes provisionales (a = 50, b = 15). No se cambiaron.** Están
documentados en el propio código como "constantes PROVISIONALES (un punto de partida
razonable, no una calibración local)".

Notas metodológicas relevantes:

- Cada registro de aforo son **tres medidas de altura** que se promedian a un solo valor
  (`skipna=True`). Se tratan como submuestras del mismo potrero, no como tres observaciones
  independientes — que es lo correcto, pero conviene declararlo.
- Se descartan filas con fecha inválida, altura nula o altura ≤ 0.
- **Implicación estadística:** como la transformación altura→biomasa es **lineal**, el R² del
  modelo es **idéntico** se exprese el objetivo en cm de altura o en kg MS/ha. Los coeficientes
  a y b solo reescalan el RMSE y el MAE. Es decir: **el R² reportado no depende en absoluto de
  que la calibración sea provisional**; el RMSE en kg/ha sí, y por tanto ese número concreto no
  es defendible hasta calibrar con pesadas reales.

### 3.2 ⚠ El flujo de recalibración con pares altura-peso NO EXISTE

La pregunta asume un flujo que no está implementado. Fue verificado con búsqueda exhaustiva
en `modelo/`, `backend/` y `src/`. Lo que existe y lo que no:

| Elemento | Estado |
|---|---|
| Pantalla o endpoint para subir pares altura-peso | ❌ **No existe** |
| Archivo/hoja donde almacenarlos | ❌ **No existe** |
| Cálculo automático (regresión) de a y b a partir de pesadas | ❌ **No existe** |
| Argumentos CLI `--calibracion-a` / `--calibracion-b` | ✅ Existen |
| ¿El backend los pasa al script? | ❌ **No.** Ver lista de argumentos abajo |
| Edición de las constantes en el código fuente | ✅ Posible (líneas 44–45) |
| Los valores usados quedan registrados en la salida | ✅ Sí, en la hoja `Modelo_Info` y visibles en la pantalla de Estadísticas |

Los argumentos que el backend **sí** pasa al script del modelo son exactamente:

```python
argumentos_modelo = [
    sys.executable, str(MODELO_SCRIPT),
    "--geojson", ..., "--indices", ..., "--aforo", ..., "--salida", ...,
    "--modelo-guardado", ...,
    "--umbral-rojo", str(UMBRAL_ROJO),
    "--umbral-ambar", str(UMBRAL_AMBAR),
    "--modo", "auto",
]
if MODELO_VARIABLES: argumentos_modelo += ["--variables", MODELO_VARIABLES]
if CLIMA_PATH:       argumentos_modelo += ["--clima", str(CLIMA_PATH)]
```

`--calibracion-a` y `--calibracion-b` **no aparecen**. Por lo tanto, **desde la aplicación
los coeficientes están fijos en 50 y 15 y no hay manera de cambiarlos** sin editar el código
o invocar el script a mano desde la terminal.

**Qué pasaría con las predicciones guardadas si se recalibrara** (respondiendo la pregunta en
hipotético, ya que el flujo no existe): `potreros_estado.xlsx` se **sobrescribe completo** en
cada corrida del script, y el objetivo de entrenamiento se recalcula desde cero a partir de
las alturas crudas guardadas en `aforo_campo.xlsx`. O sea: cambiar a y b y volver a correr
regenera todo consistentemente; **no quedan predicciones viejas mezcladas con coeficientes
nuevos**. Pero el `.joblib` guardado sí quedaría obsoleto — y como el modo `auto` solo
reentrena si cambió el aforo o el conjunto de variables (sección 5.5), **un cambio solo en
a/b NO dispararía reentrenamiento automático**. Habría que forzar `--modo train`. Esto es un
defecto latente del diseño actual si alguna vez se implementa la recalibración.

---

## 4. El estimador provisional (sin aforo real)

### 4.1 Fórmula exacta

```python
FORMULA_BASE = 100.0
FORMULA_K = 2.5
FORMULA_BIOMASA_MAXIMA = 4000.0
SAVI_A_NDVI = 1.69   # cociente NDVI/SAVI medido en esta finca (ver 2.1.1)

def biomasa_formula_provisional(fila):
    ndvi = fila.get("NDVI_mean")
    if ndvi is None or pd.isna(ndvi):
        savi = fila.get("SAVI_mean")
        if savi is None or pd.isna(savi):
            return None
        ndvi = float(savi) * SAVI_A_NDVI
    ndvi = float(np.clip(float(ndvi), 0.0, 1.0))
    return float(min(FORMULA_BASE * np.exp(FORMULA_K * ndvi), FORMULA_BIOMASA_MAXIMA))
```

**biomasa (kg MS/ha) = mín( 100 × e^(2.5 × NDVI) , 4000 )**, con NDVI recortado a [0, 1].

Valores que produce:

| NDVI | Biomasa estimada |
|---|---|
| 0.30 | ≈ 212 kg MS/ha |
| 0.45 | ≈ 308 kg MS/ha |
| 0.65 | ≈ 508 kg MS/ha |
| 0.80 | ≈ 739 kg MS/ha |

**Procedencia y honestidad de la cita.** El código documenta esta fórmula como *"una
aproximación tomada del TIPO de relación exponencial que reportan los estudios de pastos
tropicales (p. ej. *Urochloa humidicola* en la Altillanura colombiana), con constantes
redondeadas para que quede claro que NO es una calibración local de esta finca"*.

**Advertencia para el artículo:** las constantes 100 y 2.5 están **redondeadas
deliberadamente** y **no provienen de una publicación concreta citable**. El comentario del
código no referencia un DOI ni un estudio específico. Si esta fórmula va al artículo, hay que
o bien localizar y citar la fuente real de una relación NDVI–biomasa para *Urochloa*, o bien
presentarla explícitamente como heurística de arranque sin pretensión bibliográfica. **No se
debe citar como "según la literatura" sin respaldo verificable.**

El tope de 4000 kg MS/ha es un límite de cordura, no un valor derivado. El fallback vía SAVI
usa la constante `SAVI_A_NDVI = 1.69`, ya corregida y medida sobre los datos de esta finca
(ver 2.1.1); en la práctica es una ruta que casi nunca se ejecuta.

### 4.2 Distinción visual entre predicción provisional y calibrada

El campo `fuente_prediccion` de cada potrero toma uno de dos valores:
`"modelo_entrenado"` o `"formula_provisional"`. La app lo refleja en tres lugares:

**a) Insignia junto al nombre del potrero** (`src/components/MisPotreros.jsx`). Cuando
`fuente_prediccion === "formula_provisional"`:

```jsx
<span className="insignia-aproximado">Estimado</span>
```

Texto exacto: **"Estimado"**. Estilo: píldora de borde punteado (`1.5px dashed`), 11 px, color
de texto suave, `border-radius: 999px`. Es deliberadamente discreta y de borde punteado para
leerse como "provisional".

**b) Aviso dentro de la tarjeta del potrero.** Texto exacto:

> *"Estimación aproximada, todavía no calibrada con mediciones de campo. Ve a "Registrar
> medición" para mejorarla."*

En cursiva, 13 px, color de texto suave.

**c) Nota en el encabezado cuando SÍ está calibrado.** Solo aparece si
`modelo.algoritmo !== "formula_provisional"`:

> *"Modelo calibrado con tus mediciones de campo (Random Forest, 8 mediciones)."*

En negrita, color de marca oscuro.

Adicionalmente, la pantalla de Estadísticas muestra un bloque completo explicando que no hay
modelo entrenado mientras se use la fórmula provisional.

**Limitación de la señalización:** la distinción es **por potrero** y binaria. No se comunica
en la interfaz la *incertidumbre* de una predicción calibrada (no se muestra intervalo de
confianza ni el RMSE junto a cada valor de biomasa). Un potrero con `"modelo_entrenado"` se ve
exactamente igual de confiable que otro, aunque el modelo global tenga un R² de 0.42.

---

## 5. Entrenamiento del modelo

### 5.1 Hiperparámetros exactos

**RandomForestRegressor** (los defaults de sklearn están deliberadamente sobreescritos):

```python
RF_HIPERPARAMETROS = {
    "n_estimators": 300,
    "max_depth": 4,
    "min_samples_leaf": 2,
    "min_samples_split": 4,
    "max_features": "sqrt",
    "random_state": 42,
    "n_jobs": -1,
}
```

Justificación documentada en el código: con un dataset diminuto, un bosque sin límite de
profundidad y hojas de una sola muestra memorizaría el ruido de las mediciones de altura.
Árboles cortos y hojas de ≥2 muestras fuerzan a promediar; 300 árboles compensan la varianza.

**LinearRegression**: se instancia como `LinearRegression()`, **sin argumentos** — es decir,
mínimos cuadrados ordinarios con los defaults de scikit-learn (`fit_intercept=True`,
`copy_X=True`, `positive=False`). Sin regularización, sin estandarización previa de las
variables.

> Observación: con n = 8 y hasta 12 predictores, una regresión OLS sin regularización está
> matemáticamente indeterminada o casi. Una Ridge/Lasso sería más apropiada. No está
> implementado.

### 5.2 ⚠ No hay partición train/test — la validación es k-fold

La pregunta asume una partición train/test con proporción y semilla. **Eso no existe en este
código.** El esquema real es **validación cruzada k-fold sobre el 100 % de la muestra**:

```python
k = max(2, min(5, len(y) // 2))

def validar_cruzado(modelo, X, y, k):
    predicciones = np.zeros(len(y), dtype=float)
    for idx_train, idx_test in KFold(n_splits=k, shuffle=True, random_state=42).split(X):
        modelo.fit(X[idx_train], y[idx_train])
        predicciones[idx_test] = modelo.predict(X[idx_test])
    ...
```

- **k adaptativo**: `k = max(2, min(5, n // 2))`. Con n = 8 → **k = 4**. Con n ≥ 10 → k = 5.
- **Semilla**: `random_state=42`, con `shuffle=True`.
- Las métricas se calculan sobre las **predicciones fuera de pliegue agrupadas**, no
  promediando el R² de cada pliegue. Razón documentada: con pliegues de 2–3 muestras, un R²
  por pliegue no significa nada.
- **No existe un conjunto de prueba retenido (hold-out).** Todas las métricas reportadas son
  de validación cruzada. Esto debe declararse así en el artículo.

**Imputación de faltantes**: las columnas completamente vacías se descartan; las parcialmente
vacías se rellenan con la **mediana de entrenamiento**, que se guarda en el `.joblib` para
reutilizarse en predicción.

### 5.3 Criterio de selección del modelo ganador

```python
ganador = min(metricas, key=lambda nombre: metricas[nombre]["rmse"])
```

**Gana el algoritmo con menor RMSE fuera de pliegue.** Es un criterio único; R², MAE y sesgo
se calculan y reportan pero **no participan en la decisión**. El ganador se reentrena después
sobre **todas** las muestras disponibles y ese es el modelo que se serializa.

### 5.4 Métricas calculadas **[AMPLIADO EN ESTA SESIÓN]**

Antes se calculaban solo RMSE y R². Ahora, para ambos algoritmos:

```python
residuos = predicciones - y
metricas = {
    "rmse":      sqrt(mean_squared_error(y, predicciones)),
    "r2":        r2_score(y, predicciones),
    "mae":       mean(abs(residuos)),
    "sesgo":     mean(residuos),               # positivo = sobreestima
    "nrmse_pct": rmse / mean(y) * 100,
}
```

Además se persisten descriptivas de la muestra (`biomasa_media`, `biomasa_desv` con ddof=1,
`biomasa_min`, `biomasa_max`) y una tabla **observado vs. predicho fuera de pliegue** punto
por punto (`potrero`, `fecha_aforo`, `observado`, `predicho`, `residuo`) en la nueva hoja
`Modelo_Validacion`.

**Importancia de variables**: en Random Forest es `feature_importances_` (ya normalizado);
en regresión lineal se aproxima con el **valor absoluto de los coeficientes normalizado para
sumar 1**. Esta segunda no es una medida de importancia estadísticamente rigurosa — las
variables no están estandarizadas, así que la magnitud del coeficiente depende de la escala de
cada variable. **No presentar las importancias de la regresión lineal como si fueran
comparables a las del Random Forest.**

### 5.5 Persistencia del modelo y comportamiento sin modelo

**Dónde se guarda:** `joblib.dump(paquete, ruta_modelo)` en
`backend/data/modelo_entrenado.joblib`. El "paquete" serializado contiene: el estimador
entrenado, la lista de columnas usadas, las medianas de imputación, todas las métricas, los
metadatos, la tabla observado-vs-predicho y la "huella" del aforo (`n_filas_aforo`,
`ultima_fecha_aforo`) para decidir si hay que reentrenar.

**Tres modos de ejecución** (`--modo`):

| Modo | Comportamiento |
|---|---|
| `auto` (el que usa el backend) | Reentrena si cambió el aforo **o** si cambió el conjunto de variables de entrada; si no, reutiliza el `.joblib`. |
| `train` | Fuerza reentrenamiento siempre. |
| `predict` | Nunca entrena. Si no hay `.joblib`, **falla con `sys.exit(1)`** y un mensaje explicativo. |

**Qué pasa si se pide predicción antes de que exista un modelo** (el caso normal al arrancar):

1. Si hay menos de `--minimo-muestras-entrenamiento` (**default 8**) puntos emparejados, **no
   se entrena** y se usa la fórmula provisional de la sección 4 para todos los potreros,
   marcándolos `fuente_prediccion = "formula_provisional"`.
2. Si un potrero no tiene ninguna fila en el historial de índices, o ninguna con NDVI/SAVI
   utilizable, queda en `estado = "sin_datos"` con biomasa vacía — **no rompe la corrida**.
3. Si ya existía un modelo entrenado y hoy no se pudo reentrenar, se sigue usando el viejo en
   lugar de caer a la fórmula.
4. En `--modo predict` sin `.joblib`, el script aborta con error.

**[CORREGIDO EN ESTA SESIÓN]** Dos defectos encontrados y arreglados:

- *Predicción con escena inservible*: el modelo tomaba la fila **más reciente** del historial
  por potrero, aunque estuviera vacía. Tras la corrida fallida del 2026-09-21 (índices nulos),
  esas filas vacías tapaban las buenas del 2026-09-16 y todos los potreros quedaban en
  `sin_datos`. Ahora se toma la fila más reciente **que tenga NDVI o SAVI utilizable**.
- *No reentrenaba al cambiar la configuración*: `--modo auto` solo miraba si había aforo nuevo.
  Al cambiar `--variables` o `--clima`, seguía prediciendo con el modelo viejo **y mostrando
  las métricas de esa otra corrida**. Ahora compara también la lista de columnas.

### 5.6 Resultados de entrenamiento — DATOS REALES

**Los datos son reales, no inventados.** El aforo son 8 mediciones de campo del productor;
los índices son de Sentinel-2 vía Earth Engine; el clima es de la API pública de NASA POWER.

#### Los datos

**Aforo de campo (`aforo_campo.xlsx`), 8 registros en 7 fechas, 6 potreros distintos:**

| Potrero | Fecha | h1 (cm) | h2 (cm) | h3 (cm) | Promedio | Biomasa (50+15h) |
|---|---|---|---|---|---|---|
| Potrero_7 | 2025-02-03 | 15.1 | 12.6 | 14.5 | 14.07 | 261.0 |
| Potrero_5 | 2025-02-12 | 10.2 | 9.6 | 12.0 | 10.60 | 209.0 |
| Potrero_2 | 2026-01-05 | 3.1 | 4.7 | 6.2 | 4.67 | 120.0 |
| Potrero_1 | 2025-07-08 | 20.4 | 5.9 | 30.0 | 18.77 | 331.5 |
| Potrero_6 | 2025-05-16 | 10.1 | 32.3 | 15.5 | 19.30 | 339.5 |
| Potrero_6 | 2025-01-03 | 20.0 | 25.0 | 13.2 | 19.40 | 341.0 |
| Potrero_4 | 2025-01-02 | 27.9 | 20.0 | 30.7 | 26.20 | 443.0 |
| Potrero_5 | 2025-01-02 | 15.0 | 14.4 | 20.5 | 16.63 | 299.5 |

Descriptivas del objetivo: media **293.06**, desv. estándar **97.47** (ddof=1), rango
**120–443** kg MS/ha.

> **Ruido de medición a declarar:** tres registros tienen dispersión interna muy alta entre
> sus tres submuestras — Potrero_1 (20.4 / 5.9 / 30.0), Potrero_6 del 2025-05-16
> (10.1 / 32.3 / 15.5) y Potrero_6 del 2025-01-03 (20.0 / 25.0 / 13.2). En esos casos la
> desviación entre submuestras es del orden de la propia media, lo que sugiere heterogeneidad
> fuerte dentro del potrero o inconsistencia en el protocolo de medición. Es una fuente de
> error irreducible que conviene mencionar en las limitaciones.

**Clima:** NASA POWER, punto 4.6158 / −72.14302, parámetros `T2M` y `PRECTOTCORR`, diario del
2024-11-20 al 2026-09-21 (**671 días válidos**). Los últimos 4 días vienen como −999 (dato
faltante por latencia de la fuente) y el parser los ignora. Se derivan `precip_30d_mm`
(suma de los 30 días previos a la fecha de la **escena**, no del aforo) y `temp_media_c`
(promedio de esos mismos 30 días).

**Emparejamiento:** los 8 puntos de aforo emparejaron con escena satelital dentro de la
ventana de 15 días. **n = 8**, exactamente el mínimo exigido.

#### Correlación bivariada de cada variable con la biomasa observada (n = 8)

Con los índices ya corregidos (sección 2.1.1):

| Variable | r de Pearson | r² |
|---|---|---|
| **precip_30d_mm** | **0.589** | **0.347** |
| *dias_diferencia* | *0.577* | *0.333* |
| **EVI_mean** | **0.407** | **0.165** |
| SAVI_mean | 0.372 | 0.138 |
| SAVI_stdDev | −0.366 | 0.134 |
| EVI_stdDev | −0.350 | 0.123 |
| NDVI_stdDev | −0.315 | 0.099 |
| NDVI_mean | 0.302 | 0.091 |
| NDRE_stdDev | −0.243 | 0.059 |
| temp_media_c | 0.168 | 0.028 |
| NDRE_mean | 0.156 | 0.024 |
| GNDVI_stdDev | −0.146 | 0.021 |
| GNDVI_mean | 0.063 | 0.004 |

Tres lecturas: (a) **la precipitación acumulada de 30 días sigue siendo el mejor predictor
individual**, por encima de cualquier índice satelital — agronómicamente coherente en pastura
tropical; (b) **EVI_mean es ahora el mejor índice satelital** (r = 0.407), cuando antes de la
corrección de escala era el peor (r = −0.147); (c) SAVI y NDVI ya tienen correlaciones
distintas (0.372 vs 0.302), confirmando que dejaron de ser colineales.

*`dias_diferencia` aparece como diagnóstico pero **no es una variable del modelo**. Su
correlación alta (0.577) es casi con certeza espuria con n = 8 y conviene no interpretarla.*

**Comparación con los valores previos a la corrección**, por si se citó alguno:
EVI_mean pasó de −0.147 a **+0.407**; SAVI_mean de 0.302 (idéntico a NDVI) a **0.372**;
EVI_stdDev de +0.236 a **−0.350**; SAVI_stdDev de −0.315 a **−0.366**. NDVI, GNDVI, NDRE,
lluvia y temperatura no cambiaron.

#### Barrido de subconjuntos de variables (n = 8, k = 4)

Con los índices ya corregidos. Los subconjuntos que no usan SAVI ni EVI dan exactamente lo
mismo que antes de la corrección (NDVI es un cociente y no cambió); se marca con ▲ los que sí
cambiaron.

| Subconjunto | Algoritmo | RMSE | R² | MAE | |
|---|---|---|---|---|---|
| Todo (12 vars) | random_forest | 109.7 | −0.447 | 77.2 | ▲ |
| Todo (12 vars) | regresion_lineal | 80.3 | 0.225 | 62.8 | ▲ (antes −0.649) |
| Solo índices (10) | random_forest | 115.7 | −0.610 | 83.8 | ▲ |
| Solo índices (10) | regresion_lineal | 72.5 | 0.368 | 61.7 | ▲ (antes 0.190) |
| NDVI + lluvia (2) | random_forest | 99.3 | −0.186 | 73.3 | |
| NDVI + lluvia (2) | regresion_lineal | 119.1 | −0.705 | 84.8 | |
| NDVI + lluvia + temp (3) | random_forest | 101.0 | −0.227 | 78.2 | |
| NDVI + lluvia + temp (3) | regresion_lineal | 147.8 | **−1.628** | 121.5 | |
| Solo NDVI (1) | random_forest | 117.7 | −0.666 | 92.0 | |
| Solo NDVI (1) | regresion_lineal | 134.6 | −1.180 | 97.7 | |
| Solo lluvia (1) | random_forest | 81.0 | 0.211 | 56.8 | |
| Solo lluvia (1) | regresion_lineal | 87.3 | 0.083 | 64.2 | |
| **NDVI + NDVI_sd + lluvia (3)** | **regresion_lineal** | **69.2** | **0.424** | **54.3** | |
| NDVI + NDVI_sd + lluvia (3) | random_forest | 104.0 | −0.301 | 75.7 | |

La corrección de escala mejoró mucho los modelos con muchas variables (el de 12 pasó de
R² −0.649 a +0.225 con regresión lineal) pero **no cambió cuál gana**: el subconjunto de 3
variables sigue siendo el mejor con R² = 0.424.

> **Se evitó deliberadamente ampliar la búsqueda.** Con SAVI y EVI ya válidos sería tentador
> probar subconjuntos nuevos (EVI + lluvia, etc.), pero **cada comparación adicional sobre los
> mismos 8 puntos agrava el sesgo de selección** descrito en 5.7. Se dejó el barrido tal como
> estaba definido antes de la corrección.

#### Configuración final y resultado actual del sistema

Variables: `NDVI_mean, NDVI_stdDev, precip_30d_mm` (configurado en `MODELO_VARIABLES`).

| Métrica | Ganador (regresión lineal) | Random Forest |
|---|---|---|
| **RMSE** | **69.20** kg MS/ha | 104.01 |
| **nRMSE** | **23.61 %** | — |
| **MAE** | **54.30** kg MS/ha | 75.73 |
| **Sesgo** | **−8.53** kg MS/ha | — |
| **R²** | **0.424** | −0.3013 |
| n / variables / k | 8 / 3 / 4 | |

**Importancia de variables** (regresión lineal, |coef| normalizado — con la salvedad de 5.4):
`NDVI_stdDev` 0.566, `NDVI_mean` 0.434, `precip_30d_mm` 0.0002.

> Que `precip_30d_mm` reciba importancia ≈ 0 en la regresión lineal pese a ser la variable con
> mayor correlación bivariada es **exactamente el artefacto de escala** advertido en 5.4: la
> precipitación está en mm (valores de 38 a 576) y el NDVI en [0,1], así que su coeficiente es
> numéricamente diminuto sin que eso signifique que no aporta.

**Observado vs. predicho fuera de pliegue** del modelo en producción (regresión lineal,
3 variables). La tabla se regenera en cada entrenamiento y vive en la hoja `Modelo_Validacion`:

| Potrero | Fecha | Observado | Predicho | Residuo |
|---|---|---|---|---|
| Potrero_7 | 2025-02-03 | 261.0 | 221.9 | −39.1 |
| Potrero_5 | 2025-02-12 | 209.0 | 211.8 | +2.8 |
| Potrero_2 | 2026-01-05 | 120.0 | 198.4 | +78.4 |
| Potrero_1 | 2025-07-08 | 331.5 | 357.6 | +26.1 |
| Potrero_6 | 2025-05-16 | 339.5 | 267.9 | −71.6 |
| Potrero_6 | 2025-01-03 | 341.0 | 346.1 | +5.1 |
| Potrero_4 | 2025-01-02 | 443.0 | 302.3 | **−140.7** |
| Potrero_5 | 2025-01-02 | 299.5 | 370.3 | +70.8 |

El patrón sigue siendo de **regresión a la media**: sobreestima el valor más bajo (120 → 198)
y subestima el más alto (443 → 302). El residuo mayor (−140.7) es el del Potrero_4, que es
además la observación más alta de la muestra.

#### Predicción actual de los 10 potreros (escena 2026-09-16, modelo de 3 variables)

| Potrero | Estado | Biomasa (kg/ha) |
|---|---|---|
| Potrero_1 | ámbar | 395.4 |
| Potrero_2 | ámbar | 308.5 |
| Potrero_3 | rojo | 263.6 |
| Potrero_4 | ámbar | 396.6 |
| Potrero_5 | rojo | 174.5 |
| Potrero_6 | ámbar | 429.9 |
| Potrero_7 | ámbar | 404.1 |
| Potrero_8 | ámbar | 439.9 |
| Potrero_9 | ámbar | 358.0 |
| Potrero_10 | ámbar | 376.4 |

Los 10 con `fuente_prediccion = "modelo_entrenado"`.

### 5.7 ⚠ Tres advertencias estadísticas que NO deben omitirse en el artículo

**1. El R² = 0.424 está optimistamente sesgado por selección.** Ese subconjunto de variables se
eligió **después** de comparar 7 subconjuntos × 2 algoritmos sobre los **mismos 8 puntos** de
validación. Eso es selección de modelo sobre el conjunto de validación, y el resultado
reportado ya no es una estimación insesgada del error de generalización. Para un número
defendible hay que (a) fijar el subconjunto *a priori* por literatura y reportar ese, o
(b) validar el subconjunto elegido contra mediciones nuevas no usadas en la selección.
El modelo justificable *a priori* (NDVI + precipitación, ambos con respaldo agronómico) da
**R² = −0.186**, no 0.424.

**2. Las métricas son extremadamente inestables.** El R² recorre el rango **−1.72 a +0.42**
según qué variables y qué algoritmo se usen, sobre los mismos datos. Con n = 8 y hasta 12
predictores hay más parámetros que observaciones. Esa inestabilidad es en sí misma un
resultado reportable — y es más honesto presentarla que elegir el mejor número.

**3. n = 8 es el mínimo absoluto que el propio sistema acepta**, y un tamaño insuficiente para
una calibración publicable. Además los 8 puntos cubren solo 6 de los 10 potreros y están
concentrados en enero-febrero (5 de 8). No hay cobertura balanceada de épocas seca y lluviosa.

**Recomendación de encuadre:** presentar el trabajo como **prueba de concepto / piloto de un
sistema integrado** (dibujo de potreros → Earth Engine → aforo → modelo → semáforo), con
validación preliminar n = 8 y limitaciones explícitas. Eso es defendible. Presentar
R² = 0.424 como "calibración validada de la finca" no lo es.

---

## 6. Umbrales de decisión

```python
def clasificar_estado(biomasa, umbral_rojo, umbral_ambar):
    if biomasa is None:       return "sin_datos"
    if biomasa < umbral_rojo: return "rojo"
    if biomasa < umbral_ambar:return "ambar"
    return "verde"
```

| Estado | Condición | Valor efectivo |
|---|---|---|
| 🔴 rojo | biomasa < umbral_rojo | < 300 kg MS/ha |
| 🟡 ámbar | umbral_rojo ≤ biomasa < umbral_ambar | 300 – 500 kg MS/ha |
| 🟢 verde | biomasa ≥ umbral_ambar | ≥ 500 kg MS/ha |
| ⚪ sin_datos | biomasa no calculable | — |

**Son configurables, no fijos**, en tres niveles: argumentos CLI `--umbral-rojo` /
`--umbral-ambar` (defaults 300 / 500); variables de entorno `UMBRAL_ROJO` / `UMBRAL_AMBAR` en
`backend/.env` (que el backend sí pasa al script); y quedan registrados en la hoja
`Modelo_Info` y visibles en la pantalla de Estadísticas. Hay validación: el script aborta si
`umbral_rojo > umbral_ambar`.

Los valores actuales son los defaults (300 / 500). **No están derivados de datos de esta
finca**; el README los describe como "un punto de partida razonable, ajústalos con el criterio
del productor". Para el artículo: o se justifican con literatura de carga animal para
*Urochloa* en la Altillanura, o se declaran como parámetro operativo definido por el usuario.

Con el modelo actual, ningún potrero alcanza el verde (el máximo predicho es 439.9).

---

## 7. La app y el backend

### 7.1 Endpoints del backend

Base: `http://localhost:8000`. FastAPI con CORS configurable (`CORS_ORIGINS`, hoy `*`).

| # | Método | Ruta | Recibe | Devuelve |
|---|---|---|---|---|
| 1 | `GET` | `/api/potreros` | — | Estado completo: `finca`, `actualizado`, `modelo` (todas las métricas + `importancias` + `validacion`), `potreros[]` con `nombre`, `estado`, `biomasa_kg_ha`, `fecha`, `fuente_prediccion`. |
| 2 | `POST` | `/api/geojson` | FeatureCollection completo | Guarda el GeoJSON y **reinicia** el estado de todos los potreros a `sin_datos`. Devuelve igual que #1. 400 si ningún feature tiene `nombre`. |
| 3 | `DELETE` | `/api/potreros/{nombre}` | — | Borra el potrero del GeoJSON y del estado. **No borra** su aforo ni sus índices históricos. Devuelve igual que #1. 404 si no existe. |
| 4 | `POST` | `/api/potreros/{nombre}/aforo` | `{altura_cm_1, altura_cm_2, altura_cm_3, fecha?}` | Añade una medición. `fecha` opcional (default: hoy). Devuelve `{mensaje, potrero, fecha}`. 400 si altura fuera de (0, 200] o fecha mal formada; 404 si el potrero no existe. |
| 5 | `GET` | `/api/aforo` **[NUEVO]** | — | `{aforo: [{id, potrero, fecha, altura_cm_1..3}]}`, ordenado de más reciente a más antiguo. |
| 6 | `PUT` | `/api/aforo/{id}` **[NUEVO]** | `{potrero, fecha, altura_cm_1..3}` (todos obligatorios) | Actualiza esa medición. Mismas validaciones que #4. 404 si el `id` no existe. |
| 7 | `DELETE` | `/api/aforo/{id}` **[NUEVO]** | — | Borra esa medición. 404 si el `id` no existe. |
| 8 | `POST` | `/api/predecir` | — | Corre Earth Engine → anexa al historial → corre el modelo → devuelve igual que #1. 400 sin GeoJSON o sin `EE_PROJECT`; 501 si falta el script del modelo; 502 si falla cualquiera de los subprocesos, con las últimas 8 líneas de su salida. |

Los endpoints 5–7 se añadieron en esta sesión. Requirieron introducir una columna **`id`**
(UUID hex de 32 caracteres) en `aforo_campo.xlsx`. Los archivos previos sin esa columna se
migran automáticamente al leerlos por primera vez: se asignan UUIDs y se reescribe el archivo
una sola vez, conservando todas las filas y valores. **Verificado sobre los datos reales**: las
4 filas preexistentes conservaron sus valores exactos y solo se añadió la columna al final.

El script del modelo ignora la columna `id` (lee por nombre de columna), así que no afecta al
entrenamiento.

### 7.2 Vistas de la app

Cuatro vistas con navegación inferior fija (`src/App.jsx`). Diseño **mobile-first**
declarado ("Campo Claro", ver `DESIGN.md`): pensado para ~360–400 px, botones de mínimo 56 px
de alto, sin modo oscuro a propósito para legibilidad bajo sol directo. Tipografía Atkinson
Hyperlegible.

**1. "Dibujar potreros"** — Canvas para dibujar polígonos. Toolbar, tabla de potreros con
nombre, nº de vértices y área aproximada en hectáreas, botón de eliminar con confirmación
en línea. Permite cargar un lindero de referencia desde archivo o texto pegado. Exporta
GeoJSON y lo envía al backend.

**2. "Mis potreros"** — Saludo con el nombre de la finca y fecha de última actualización;
nota de modelo calibrado cuando aplica. Fila de chips con el conteo por estado
(Bien / Regular / Bajo / Sin datos). Botón "Actualizar recomendaciones" que dispara
`POST /api/predecir` con indicador de progreso. Lista de tarjetas por potrero, con borde de
color según el semáforo, icono + etiqueta de estado, biomasa estimada, fecha del dato, y la
insignia "Estimado" y el aviso descritos en 4.2. En pantallas ≥700 px la lista pasa a dos
columnas.

**3. "Registrar medición"** — Formulario con selector de potrero, fecha (default hoy) y las
tres medidas de altura en cm (`type="number"`, `inputMode="decimal"`, rango 0–200). Validación
en cliente antes de enviar.
**[AÑADIDO EN ESTA SESIÓN]** Debajo, sección **"Historial de mediciones"**: lista de tarjetas
con potrero, fecha formateada en español y las tres alturas, cada una con acciones **Editar**
y **Eliminar**. "Editar" carga el registro en el mismo formulario de arriba (el título cambia
a "Editar medición", el botón a "Guardar cambios" y aparece "Cancelar edición"), en lugar de
duplicar el formulario. "Eliminar" pide confirmación en línea (Sí, borrar / Cancelar). El
historial se recarga tras cada alta, edición o borrado.

**4. "Estadísticas"** — **[MUY AMPLIADA EN ESTA SESIÓN]**. Mientras no hay modelo entrenado,
muestra un texto explicando que se usa la fórmula provisional y qué hacer para entrenar.
Con modelo entrenado muestra, en este orden:
- Chips: algoritmo ganador, RMSE, R², nº de mediciones.
- **Aviso metodológico automático** (recuadro ámbar) si R² < 0.5 o n < 30, advirtiendo que
  las métricas son inestables y que sirve como prueba de concepto, no como calibración
  definitiva. *(Añadido deliberadamente para que la propia interfaz no invite a sobreinterpretar.)*
- Tabla de métricas de validación: RMSE, nRMSE %, MAE, sesgo, R², n, nº de variables, cada
  una con una glosa en lenguaje llano.
- Tabla de descriptivas de la muestra (media ± desv., rango).
- **Gráfico de dispersión observado vs. predicho** en SVG, con la diagonal 1:1 punteada,
  escalas iguales en ambos ejes, puntos de 6 px de radio con anillo de 2 px, accesible por
  teclado y con lectura al pasar el cursor; debajo, la tabla completa de los puntos con sus
  residuos.
- Gráfico de barras comparando RMSE de Random Forest vs. regresión lineal, con insignia
  "Ganador", más tabla comparativa con RMSE, R², MAE y sesgo de ambos.
- Gráfico de barras de importancia de variables.
- Bloque "Cómo se calibró": fecha de entrenamiento, k, si usó clima, la fórmula
  altura→biomasa con sus coeficientes y los umbrales del semáforo.

La paleta de los gráficos (`#2a78d6` Random Forest, `#4a3aa7` regresión lineal) fue validada
con el verificador de accesibilidad cromática: pasa banda de luminosidad, piso de croma,
separación para daltonismo (ΔE 13.0 deuteranopía, 17.4 tritanopía), piso de visión normal
(ΔE 16.3) y contraste ≥3:1 contra el fondo. Es deliberadamente distinta del semáforo
verde/ámbar/rojo para que el color no confunda "algoritmo" con "estado del potrero".

### 7.3 Pruebas realizadas — qué se verificó y qué no

**Suites automatizadas (todas en verde):**

| Suite | Resultado |
|---|---|
| `backend/tests/test_main.py` | **28 pasan** (19 preexistentes + 9 añadidos para los endpoints de aforo) |
| `modelo/tests/` | **21 pasan** |
| `npx eslint src` | limpio |
| `npm run build` (Vite) | compila, 181 kB JS / 11.9 kB CSS |

Los tests añadidos cubren: listado vacío, orden por fecha e unicidad de `id`, migración de
archivos antiguos sin columna `id` con persistencia del UUID, edición completa, 404 en
edición y borrado de `id` inexistente, validación de altura y de potrero en la edición,
borrado efectivo, y que `/api/predecir` pase `--ventana-dias` y `--umbral-nubes` al script.

**Ejecución real front + backend juntos: sí.** El backend corrió con datos reales de la finca
y el usuario usó la interfaz en el navegador durante la sesión.

**Bugs encontrados y corregidos durante esa ejecución:**

1. **`/api/aforo` devolvía 404.** Causa: había un proceso uvicorn viejo en el puerto 8000
   arrancado en otra sesión, sin `--reload`, sirviendo código anterior. Se reinició.
2. **`--reload` de uvicorn aplicó solo una de dos ediciones.** El servidor quedó con una
   versión mixta (constantes nuevas, llamada al subproceso vieja) y seguía usando 10 días /
   40 % de nubes. Detectado porque el mensaje de error del script seguía citando los valores
   viejos. Se resolvió con reinicio completo. *(Es un problema conocido de watchfiles en
   Windows con guardados muy seguidos; conviene reiniciar en vez de confiar en el reload.)*
3. **`CLIMA_PATH` no tenía efecto.** El `.env` tenía dos líneas `CLIMA_PATH=`: la plantilla
   original vacía y la nueva con la ruta. El parser usa `os.environ.setdefault()`, así que
   ganaba la primera (vacía) y el modelo entrenaba sin clima. Se eliminó la duplicada.
4. **Ruta relativa frágil.** `CLIMA_PATH` relativo se resolvía contra el directorio desde el
   que se lanzara uvicorn. Ahora se resuelve contra `backend/`.
5. Los dos defectos del modelo descritos en 5.5 (escena inservible y no reentrenar al cambiar
   configuración).
6. **El escalado de SAVI y EVI** (sección 2.1.1). Detectado al revisar el código para este
   reporte, no por un síntoma visible: el sistema funcionaba y devolvía números de aspecto
   razonable. Se corrigió, se regeneró el historial completo desde Earth Engine y se
   reentrenó. Es el defecto de mayor impacto científico de los encontrados.

**Qué NO se verificó visualmente:** la pantalla de **"Estadísticas" rediseñada** (tablas,
gráfico de dispersión, aviso metodológico) **no fue inspeccionada en un navegador**. Se
verificó que la API devuelve todos los campos, que ESLint pasa y que Vite compila, pero
**nadie ha mirado el resultado renderizado**. El gráfico de dispersión en SVG, en particular,
podría tener problemas de superposición de etiquetas o de geometría que ninguna de esas
comprobaciones detecta. La vista de "Registrar medición" con el historial **sí** fue
confirmada visualmente por el usuario.

---

## 8. Estado actual y pendientes

### 8.1 Terminado y probado

- **Extracción de índices contra Earth Engine real**: funciona, con selección de escena por
  reintento y resolución por potrero, y con las cinco fórmulas ya correctas. Probado en ~20
  corridas reales (4 diagnósticas + 7 del primer backfill + 8 de la regeneración posterior a
  la corrección de SAVI/EVI), todas exitosas tras los arreglos.
- **Historial de índices**: 80 filas tras la regeneración, **todas con índices utilizables**,
  9 fechas de escena entre 2024-12-25 y 2026-09-16 (90 filas tras una corrida extra de
  verificación, con duplicados inocuos).
- **CRUD completo de mediciones de aforo** (alta, listado, edición, borrado) por API y por
  interfaz, con migración automática de archivos antiguos. Cubierto por 9 tests y confirmado
  visualmente.
- **Entrenamiento y validación cruzada**: funciona de punta a punta, produce el `.joblib`,
  todas las métricas y las tres hojas de salida. 21 tests en verde.
- **Predicción y semáforo** para los 10 potreros con datos reales.
- **Descarga e integración de clima NASA POWER**: 671 días reales incorporados al modelo.
- **Orquestación del backend**: los 8 endpoints responden; 28 tests en verde.
- **Configurabilidad**: ventana de días, umbral de nubes, variables del modelo, umbrales del
  semáforo y ruta de clima, todos por variable de entorno sin tocar código.

### 8.2 Construido pero NO probado (o probado insuficientemente)

- **Pantalla de Estadísticas rediseñada**: nunca vista renderizada. Riesgo concreto en el
  gráfico SVG de dispersión.
- **Vista "Dibujar potreros"**: no se tocó ni se probó en esta sesión. Su estado se reporta
  por lectura de código.
- **Endpoints `POST /api/geojson` y `DELETE /api/potreros/{nombre}`**: cubiertos por tests
  unitarios, pero no ejercitados contra los datos reales de la finca en esta sesión.
- **Modo `--modo predict`** del script del modelo: hay test de que falla correctamente sin
  `.joblib`, pero no se ejercitó la ruta de éxito.
- **La migración de `id`** se probó con 4 filas. No se ha probado con un archivo grande ni con
  filas editadas a mano en Excel que rompan el formato.
- **Comportamiento con varios usuarios simultáneos**: no existe bloqueo de archivos. Dos
  escrituras concurrentes sobre el mismo `.xlsx` pueden corromperlo o perder datos. No probado
  y probablemente roto.

### 8.3 Pendiente — lo que falta por hacer

**Crítico para la validez científica** — ninguno de estos se resuelve con código:

1. **Aumentar n**. Con 8 puntos no hay calibración publicable. Una ronda de aforo sobre los 10
   potreros aporta 10 puntos; tres rondas llevarían a ~38. Falta además cobertura de época
   lluviosa (hoy 5 de 8 puntos son de enero-febrero). **Requiere trabajo de campo.**
2. **Validar el subconjunto de variables con datos nuevos**, para eliminar el sesgo de
   selección del R² = 0.424 (sección 5.7). **Requiere mediciones no usadas en la selección.**
3. **Calibrar de verdad la conversión altura→biomasa** con pares altura-peso de pasto cortado
   y secado. Hoy a = 50 y b = 15 son un punto de partida sin respaldo empírico. Sin esto, el
   RMSE en kg MS/ha no tiene anclaje físico (aunque el R² sí es válido, ver 3.1).
   **Requiere balanza y horno de secado.**
4. **Respaldar o retirar la fórmula provisional** (sección 4.1): hoy se presenta como "de
   literatura" sin referencia verificable. **Requiere búsqueda bibliográfica.**

*(El escalado de SAVI y EVI estaba en esta lista y ya se corrigió — ver 2.1.1.)*

**Funcionalidad ausente** — estos sí se resuelven con código:

5. **Flujo de recalibración altura-peso** (sección 3.2): no existe nada. Requiere pantalla de
   captura, almacenamiento, ajuste por regresión de a y b, y forzar reentrenamiento al cambiar.
6. **El backend no pasa `--calibracion-a/-b`**: aunque se implemente lo anterior, hay que
   añadirlos a la invocación.
7. **`/api/predecir` siempre consulta la fecha de hoy.** No hay forma desde la app de pedir
   los índices de una fecha pasada. Por eso el backfill hubo que hacerlo con un script ad hoc,
   dos veces. Cualquier medición registrada con fecha retroactiva quedará sin índices
   satelitales salvo que alguien corra el script a mano. **Es un vacío de diseño que va a
   reaparecer cada vez que se carguen mediciones viejas.**
8. **No se expone la incertidumbre por potrero** en la interfaz (sección 4.2).
9. **No hay regularización** (Ridge/Lasso) pese a que el régimen n < p la pide (sección 5.1).
10. **Sin bloqueo de concurrencia** en los Excel.
11. **El historial acumula filas duplicadas** si se corre `/api/predecir` varias veces el mismo
    día con la misma escena (ver nota en 2.4). Inofensivo para el modelo, sucio para publicar
    el historial como dataset.

**Menor:**

12. `datetime.utcfromtimestamp()` deprecado en `extraer_indices.py`.
13. El parser de `.env` usa `setdefault`, así que una clave duplicada se resuelve por la
    primera aparición de forma silenciosa — ya causó el bug #3 de la sección 7.3.
14. `MAX_ESCENAS_CANDIDATAS = 25` no es configurable.
15. ESLint analiza `.venv/` y reporta 32 errores en JavaScript vendorizado de paquetes de
    Python. Ruido preexistente; convendría excluir esa carpeta.

### 8.4 Resumen honesto en una frase

**Lo que funciona de punta a punta hoy:** dibujar potreros → obtener índices Sentinel-2
reales y correctamente calculados, con manejo robusto de nubes → registrar y editar aforo de
campo → incorporar clima real → entrenar y validar un modelo → mostrar semáforo y estadísticas
completas.
**Lo que todavía no es publicable como calibración:** el modelo mismo, por n = 8, por sesgo de
selección en la elección de variables y por una conversión altura→biomasa sin anclaje
empírico. Los tres son limitaciones de **datos**, no de software: ya no queda ningún defecto
de código conocido que afecte la validez de los índices.

---

## 9. Estructura de archivos

Archivos **modificados en esta sesión** marcados con `*`. No se creó ningún archivo fuente
nuevo; los archivos de datos no están versionados (`.gitignore`).

```
sad-ganaderia/
├── DESIGN.md                        Sistema de diseño "Campo Claro": paleta, tipografía,
│                                    criterios mobile-first para uso en campo.
├── README.md                        Documentación general del proyecto.
├── REPORTE_TECNICO.md               Este documento.
├── .env.example                     Plantilla frontend: VITE_API_BASE_URL.
├── potreros.geojson                 (no versionado) 10 potreros de la finca de estudio.
│
├── earth-engine/
│   ├── extraer_indices.py *         Script CLI de Earth Engine. Carga el GeoJSON, busca
│   │                                escenas candidatas Sentinel-2, aplica máscara SCL,
│   │                                calcula los 5 índices y los reduce por potrero.
│   │                                MODIFICADO: (a) selección de escena con reintento por
│   │                                potrero (buscar_escenas_candidatas +
│   │                                recolectar_indices_por_potrero), reemplazando la
│   │                                selección de escena única; (b) corrección del escalado
│   │                                de reflectancia que invalidaba SAVI y EVI.
│   ├── README.md *                  MODIFICADO: nueva sección "Cómo elige la escena".
│   └── requirements.txt             earthengine-api, pandas, openpyxl.
│
├── modelo/
│   ├── entrenar_predecir.py *       Script CLI del modelo. Empareja aforo con índices,
│   │                                entrena RF vs. regresión lineal con k-fold, elige
│   │                                ganador por RMSE, predice y clasifica el semáforo.
│   │                                MODIFICADO: métricas MAE/sesgo/nRMSE + descriptivas,
│   │                                tabla observado-vs-predicho, hoja Modelo_Validacion,
│   │                                opción --variables, uso de la última escena *utilizable*,
│   │                                y reentrenamiento al cambiar configuración.
│   ├── README.md *                  MODIFICADO: contrato de --variables, métricas nuevas
│   │                                y hoja Modelo_Validacion.
│   ├── requirements.txt             scikit-learn, pandas, numpy, joblib, openpyxl.
│   └── tests/
│       ├── test_entrenar_predecir.py    Unitarios: fórmula provisional, calibración,
│       │                                parseo NASA POWER, emparejamiento, comparación
│       │                                de algoritmos.
│       └── test_integracion_cli.py      Integración: corridas completas del script como
│                                        subproceso (sin aforo, modo predict sin modelo,
│                                        potrero sin consulta satelital).
│
├── backend/
│   ├── main.py *                    API FastAPI, 8 endpoints. Orquesta los dos scripts
│   │                                como subprocesos y lee/escribe los Excel.
│   │                                MODIFICADO: endpoints GET/PUT/DELETE de aforo, columna
│   │                                id con migración, EE_VENTANA_DIAS/EE_UMBRAL_NUBES,
│   │                                MODELO_VARIABLES, CLIMA_PATH relativo a backend/,
│   │                                lectura de la hoja Modelo_Validacion.
│   ├── README.md *                  MODIFICADO: documentación de los endpoints y variables
│   │                                de entorno nuevos.
│   ├── .env.example *               MODIFICADO: EE_VENTANA_DIAS, EE_UMBRAL_NUBES,
│   │                                MODELO_VARIABLES.
│   ├── .env                         (no versionado) Configuración real de esta finca.
│   ├── requirements.txt             fastapi, uvicorn, openpyxl.
│   ├── requirements-dev.txt         pytest, httpx.
│   ├── tests/test_main.py *         MODIFICADO: +9 tests para el CRUD de aforo y para los
│   │                                parámetros de Earth Engine.
│   └── data/                        (no versionado) Datos de la finca.
│       ├── aforo_campo.xlsx             Hoja "Aforo": 8 mediciones + columna id.
│       ├── indices_historial.xlsx       Hoja "Indices": regenerado tras corregir SAVI/EVI.
│       │                                80 filas (8 fechas x 10 potreros), todas utilizables;
│       │                                90 tras una corrida extra. Solo crece.
│       ├── potreros_estado.xlsx         Hojas Potreros, Finca, Modelo_Info,
│       │                                Modelo_Importancia, Modelo_Validacion.
│       ├── modelo_entrenado.joblib      Modelo serializado + métricas + medianas.
│       └── clima_nasa_power.csv         671 días de T2M y PRECTOTCORR (NASA POWER).
│
├── src/
│   ├── App.jsx                      Navegación entre las 4 vistas, estado del dibujo de
│   │                                potreros, guardado de GeoJSON.
│   ├── main.jsx                     Punto de entrada de React.
│   ├── index.css *                  Sistema de diseño completo. MODIFICADO: estilos del
│   │                                historial de aforo, tablas de métricas, gráfico de
│   │                                dispersión SVG y aviso metodológico.
│   ├── components/
│   │   ├── MapCanvas.jsx            Canvas de dibujo de polígonos.
│   │   ├── Toolbar.jsx              Controles del dibujo.
│   │   ├── PotreroTable.jsx         Tabla de potreros dibujados con borrado confirmado.
│   │   ├── BoundaryInput.jsx        Carga de lindero de referencia (archivo o texto).
│   │   ├── MisPotreros.jsx          Vista del productor: chips de resumen, botón de
│   │   │                            actualizar, tarjetas por potrero con semáforo e
│   │   │                            insignia "Estimado".
│   │   ├── RegistrarMedicion.jsx *  Formulario de aforo. MODIFICADO: historial completo
│   │   │                            con editar y eliminar, y modo edición en el propio
│   │   │                            formulario.
│   │   ├── EstadisticasModelo.jsx * Estadísticas del modelo. MODIFICADO: tablas de
│   │   │                            métricas y descriptivas, gráfico de dispersión
│   │   │                            observado-vs-predicho, tabla comparativa de
│   │   │                            algoritmos y aviso metodológico automático.
│   │   ├── Iconos.jsx               Iconos de estado del semáforo.
│   │   └── ErrorBoundary.jsx        Captura de errores de React.
│   └── utils/
│       ├── api.js *                 Cliente HTTP. MODIFICADO: obtenerHistorialAforo,
│       │                            editarAforo, borrarAforo.
│       ├── geo.js                   Cálculos geométricos (área, conversiones).
│       ├── exportGeoJSON.js         Serialización a GeoJSON.
│       ├── parseBoundary.js         Parseo de coordenadas pegadas como texto.
│       ├── parseBoundaryFile.js     Parseo de archivos de lindero.
│       └── formato.js               Formateo de fechas en español (es-CO).
│
├── package.json                     Scripts: dev, build, preview, lint.
├── vite.config.js                   Configuración de Vite.
├── eslint.config.js                 Configuración de ESLint.
└── index.html                       HTML raíz.
```

**Resumen del diff de esta sesión:** 12 archivos modificados, 1331 líneas añadidas, 128
eliminadas. Ningún archivo fuente creado. Nada commiteado todavía: todos los cambios están en
el árbol de trabajo.

---

## Apéndice: configuración efectiva actual (`backend/.env`)

```
EE_PROJECT=evident-hexagon-483917-k9
GEOJSON_PATH=                                    (vacío → potreros.geojson en la raíz)
FINCA_NOMBRE=Mi finca
CORS_ORIGINS=*
CLIMA_PATH=data/clima_nasa_power.csv
UMBRAL_ROJO=300
UMBRAL_AMBAR=500
EE_VENTANA_DIAS=45
EE_UMBRAL_NUBES=85
MODELO_VARIABLES=NDVI_mean,NDVI_stdDev,precip_30d_mm
```

Parámetros no expuestos como configuración, fijos en el código:
`ESCALA_REFLECTANCIA=10000`, `MAX_ESCENAS_CANDIDATAS=25`, `CLASES_SCL_VALIDAS=[4,5,7]`,
`CALIBRACION_A=50`, `CALIBRACION_B=15`, `FORMULA_BASE=100`, `FORMULA_K=2.5`,
`FORMULA_BIOMASA_MAXIMA=4000`, `SAVI_A_NDVI=1.69`, `RF_HIPERPARAMETROS`,
`minimo_muestras_entrenamiento=8` (CLI, pero el backend no lo pasa),
`ventana_emparejamiento_dias=15` (CLI, pero el backend no lo pasa),
`scale=10` en `reduceRegions`, `random_state=42` en KFold y en Random Forest.

---

## Registro de cambios de este documento

- **2026-09-21, versión inicial.** Generado tras la sesión de trabajo.
- **2026-09-21, revisión tras corregir SAVI/EVI.** Se detectó, durante la redacción de este
  mismo reporte, el defecto de escala de reflectancia de la sección 2.1.1. Se corrigió el
  código, se regeneró el historial completo de índices desde Earth Engine y se reentrenó el
  modelo. Se actualizaron: las fórmulas de 2.1, la sección 2.1.1 completa, los valores de
  índices de 2.4, el conteo del historial, la constante `SAVI_A_NDVI` de 4.1, la tabla de
  correlaciones y el barrido de subconjuntos de 5.6, la tabla observado-vs-predicho, y las
  listas de bugs y pendientes de 7.3 y 8.3.
  **Las métricas del modelo en producción (RMSE 69.2, R² 0.424) no cambiaron**, porque el
  subconjunto de variables en uso no incluye SAVI ni EVI.
