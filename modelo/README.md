# Modelo de predicción de biomasa

Script que entrena (cuando hay con qué) y corre el modelo de biomasa
forrajera por potrero: compara Random Forest contra regresión lineal,
usando como entradas los índices de vegetación de Sentinel-2
([`earth-engine/`](../earth-engine/)) y clima (NASA POWER), calibrado con
aforo de campo (altura de pasto medida a mano). Mientras no haya aforo
real suficiente para entrenar, usa una fórmula provisional basada en
literatura — nunca inventa un modelo "entrenado" con datos que no existen.

Todos los datos viven en Excel dentro de `backend/data/` (no hay base de
datos — ver [`backend/README.md`](../backend/README.md)). El backend ya
está enchufado para invocar este script tal cual este contrato lo
describe.

## Las variables de entrada (X)

Por cada punto potrero + fecha:

- `NDVI_mean`, `NDVI_stdDev`, `GNDVI_mean`, `GNDVI_stdDev`, `NDRE_mean`,
  `NDRE_stdDev`, `SAVI_mean`, `SAVI_stdDev`, `EVI_mean`, `EVI_stdDev` —
  de Sentinel-2, ya calculados por `earth-engine/extraer_indices.py`.
- `precip_30d_mm` — precipitación acumulada de los 30 días previos.
- `temp_media_c` — temperatura media de esos mismos 30 días.

Las dos últimas son opcionales: si no se pasa `--clima`, el modelo
entrena y predice solo con los índices de satélite.

## La variable objetivo (Y)

Biomasa forrajera disponible, en **kg de materia seca por hectárea (kg
MS/ha)**. No se mide directamente: en campo se mide la ALTURA del pasto
(3 medidas por punto, promediadas) y se convierte con una calibración
lineal:

```
biomasa_kg_ms_ha = CALIBRACION_A + CALIBRACION_B * altura_cm_promedio
```

`CALIBRACION_A` y `CALIBRACION_B` son constantes provisionales
(`50` y `15` por defecto) documentadas como tales en el código — un punto
de partida razonable, no una calibración real. En cuanto se pesen aunque
sea 4-5 muestras de pasto cortado, se recalibran (por CLI con
`--calibracion-a`/`--calibracion-b`, o cambiando las constantes en el
archivo).

## Cómo se entrena (cuando hay aforo suficiente)

1. Por cada fila de aforo, se busca en el historial de índices
   (`--indices`) la fila del **mismo potrero** cuya fecha de escena esté
   más cerca de la fecha del aforo, dentro de una ventana máxima
   (`--ventana-emparejamiento-dias`, default 15 días). Sin match cercano,
   ese punto de aforo se descarta (se avisa por consola).
2. Si hay menos de `--minimo-muestras-entrenamiento` (default 8) puntos
   emparejados, **no se entrena** — se usa la fórmula provisional para
   todos los potreros y se explica por qué en la consola. Entrenar con
   menos datos que eso produciría un modelo sobreajustado y poco
   confiable.
3. Con suficientes puntos, se comparan Random Forest y regresión lineal
   con validación cruzada (k-fold), evaluando RMSE y R². Gana el que
   tenga menor RMSE promedio. Ese algoritmo se reentrena con todos los
   puntos disponibles y se guarda en disco (`--modelo-guardado`, formato
   `joblib`) junto con sus métricas y metadatos.

## Cómo se predice (siempre, para todos los potreros)

Para cada potrero del GeoJSON, se toman sus índices de satélite más
recientes del historial:

- Si hay un modelo entrenado disponible: se usa para predecir. Se marca
  `fuente_prediccion = "modelo_entrenado"`.
- Si no (todavía no hay aforo suficiente): se usa una fórmula provisional
  basada en el tipo de relación NDVI-biomasa reportada en literatura de
  pastos tropicales (documentada con comentarios en el código, con la
  fórmula exacta y sus constantes). Se marca
  `fuente_prediccion = "formula_provisional"`.

La app del productor debe mostrar esa fuente de forma visible — una
predicción con fórmula provisional **no debe verse igual** ni con la
misma confianza que una ya calibrada con aforo real.

## Semáforo verde/ámbar/rojo

Con la biomasa estimada, umbrales configurables (no hardcodeados):

- `biomasa < --umbral-rojo` (default 300 kg MS/ha) → `"rojo"`.
- entre `--umbral-rojo` y `--umbral-ambar` (default 500) → `"ambar"`.
- `biomasa >= --umbral-ambar` → `"verde"`.

## Uso

```bash
python entrenar_predecir.py \
  --geojson <ruta al GeoJSON de potreros> \
  --indices <ruta a backend/data/indices_historial.xlsx> \
  --aforo <ruta a backend/data/aforo_campo.xlsx> \
  --salida <ruta a backend/data/potreros_estado.xlsx> \
  [--modelo-guardado <ruta al .joblib, default: junto a --salida>] \
  [--clima <ruta a CSV/XLSX de clima NASA POWER, opcional>] \
  [--umbral-rojo 300] [--umbral-ambar 500] \
  [--calibracion-a 50] [--calibracion-b 15] \
  [--minimo-muestras-entrenamiento 8] [--ventana-emparejamiento-dias 15] \
  [--variables NDVI_mean,NDVI_stdDev,precip_30d_mm] \
  [--modo auto|train|predict]
```

`--variables` limita las variables de entrada (por defecto se usan las 12:
10 índices + 2 de clima). **Con pocas mediciones esto importa mucho**: con
menos muestras que variables el modelo sobreajusta y el R² se vuelve
negativo. Con las 8 mediciones de la finca de prueba, las 12 variables dan
R² = −0.43; `NDVI_mean,NDVI_stdDev,precip_30d_mm` da R² = 0.42. Ojo al
reportarlo: elegir el subconjunto mirando cuál valida mejor sobre los mismos
puntos sesga la métrica hacia arriba — para un resultado defendible hay que
fijar el subconjunto *a priori* (por literatura) o validarlo con datos
nuevos.

`--modo auto` (default): reentrena solo si hay aforo más nuevo que el
último entrenamiento guardado; si no, predice con el modelo ya guardado.
`--modo train` fuerza un reentrenamiento. `--modo predict` nunca entrena
(falla con un mensaje claro si todavía no hay ningún modelo guardado).

El backend (`backend/main.py`, función `predecir()`) ya invoca el script
exactamente así — con estos nombres de argumento — así que no hace falta
tocar el backend cuando este script cambie, mientras se respete este
contrato.

## Formato de los archivos

### `--indices` (`backend/data/indices_historial.xlsx`)

Hoja **"Indices"**, una fila por cada vez que se consultó el satélite
para un potrero (el backend la va acumulando, nunca la sobreescribe):

`potrero, fecha_escena_usada, dias_diferencia_con_fecha_objetivo, NDVI_mean, NDVI_stdDev, GNDVI_mean, GNDVI_stdDev, NDRE_mean, NDRE_stdDev, SAVI_mean, SAVI_stdDev, EVI_mean, EVI_stdDev, fecha_consulta`

### `--aforo` (`backend/data/aforo_campo.xlsx`)

Hoja **"Aforo"**: `potrero, fecha, altura_cm_1, altura_cm_2, altura_cm_3`.
El backend le agrega ademas una columna `id` (para poder editar/borrar
mediciones desde `PUT`/`DELETE /api/aforo/{id}`) que este script ignora
por completo -- lee las columnas por nombre y solo le importan las cinco
de arriba.

### `--clima` (opcional)

Formato NASA POWER (`.csv` o `.xlsx`, se puede descargar gratis en
https://power.larc.nasa.gov/data-access-viewer/ para las coordenadas de
la finca): columnas `YEAR, DOY, T2M, PRECTOTCORR`. Si es `.csv`, puede
venir con el bloque de cabecera que agrega NASA POWER
(`-BEGIN HEADER-` ... `-END HEADER-`) — el script debe ignorarlo. El
valor `-999` significa dato faltante.

### `--salida` (`backend/data/potreros_estado.xlsx`)

El script **sobreescribe** este archivo completo con tres hojas:

**"Potreros"** — una fila por cada potrero del GeoJSON (todos, incluso
los que nunca se han medido en campo):

| columna | contenido |
|---|---|
| `nombre` | nombre del potrero |
| `estado` | `"verde"`, `"ambar"`, `"rojo"` o `"sin_datos"` (si nunca se pudo calcular nada) |
| `biomasa_kg_ha` | biomasa estimada, o vacío |
| `fecha` | fecha de la escena de satélite usada para esa estimación |
| `fuente_prediccion` | `"modelo_entrenado"`, `"formula_provisional"`, o vacío |

**"Finca"** — una fila: `finca` (se conserva el nombre que ya tuviera el
archivo anterior, si existía), `actualizado` (fecha/hora de esta corrida).

**"Modelo_Info"** — una fila con metadatos de transparencia:

- Identificación: `algoritmo` (`"random_forest"`, `"regresion_lineal"` o
  `"formula_provisional"`), `entrenado_el`, `n_muestras_entrenamiento`,
  `n_variables_entrada`, `k_validacion`, `usa_clima`.
- Métricas del ganador, todas sobre las predicciones **fuera de pliegue**:
  `rmse`, `r2`, `mae`, `sesgo` (error medio: positivo = sobreestima),
  `nrmse_pct` (RMSE como % de la biomasa media, para comparar contra
  estudios de otras fincas donde la escala de kg/ha cambia).
- Descriptivas de la muestra: `biomasa_media`, `biomasa_desv`,
  `biomasa_min`, `biomasa_max` — sin el rango y la dispersión, un RMSE en
  kg/ha no se puede interpretar.
- Métricas de **ambos** algoritmos, para la tabla comparativa:
  `rmse_random_forest`, `r2_random_forest`, `mae_random_forest`,
  `sesgo_random_forest` y sus equivalentes `_regresion_lineal`.
- Parámetros usados: `calibracion_a`, `calibracion_b`, `umbral_rojo`,
  `umbral_ambar`.

**"Modelo_Validacion"** — una fila por punto de entrenamiento con su
predicción fuera de pliegue: `potrero`, `fecha_aforo`, `observado`,
`predicho`, `residuo`. Es la tabla con la que la app arma el gráfico de
dispersión observado vs. predicho (la figura estándar para reportar un
modelo de estimación de biomasa).

El backend lee estas hojas por nombre de columna (no por posición), así
que se puede abrir el Excel y corregir algo a mano sin romper nada.

## Metodología (detalles de implementación)

**Random Forest.** Los hiperparámetros están fijados a propósito en un
rango conservador (`n_estimators=300`, `max_depth=4`, `min_samples_leaf=2`,
`min_samples_split=4`, `max_features="sqrt"`, `random_state=42`), no en
los defaults de sklearn: con el tamaño de dataset que va a haber en la
práctica (el mínimo del contrato son 8 muestras, y realistamente serán
unas pocas decenas), un bosque sin límite de profundidad y con hojas de
una sola muestra memoriza el ruido de las mediciones de altura en vez de
aprender la relación índice-biomasa. Árboles cortos y hojas de al menos 2
muestras fuerzan a promediar; muchos árboles compensan la varianza que
eso introduce. La comparación contra la regresión lineal se hace con
k-fold (`k = max(2, min(5, n//2))`, o sea k=4 con 8 muestras y k=5 de 10
en adelante) y las métricas RMSE/R² se calculan sobre las predicciones
**fuera de pliegue juntas**, no promediando el R² de cada pliegue: con
pliegues de 2-3 muestras un R² por pliegue no significa nada. Gana el de
menor RMSE, se reentrena con todos los puntos y se guarda en el `.joblib`
junto con las columnas usadas, las medianas de entrenamiento (para
imputar un índice que venga nulo por nubes, o el clima si una corrida se
hace sin `--clima`) y los metadatos que se publican en "Modelo_Info".

**Fórmula provisional.** Mientras no hay modelo entrenado se usa
`biomasa_kg_ms_ha = 100 * exp(2.5 * NDVI)`, con tope de cordura en 4000
kg MS/ha (si falta NDVI en la escena pero hay SAVI, se aproxima
`NDVI ≈ 1.8 * SAVI`). Es una aproximación del **tipo** de relación
exponencial NDVI-biomasa que reporta la literatura de pastos tropicales
(p. ej. *Urochloa humidicola* en la Altillanura colombiana), con
constantes redondeadas justamente para que quede claro que **no** es una
calibración local de esta finca: da ~212 kg/ha con NDVI 0.30, ~308 con
0.45, ~508 con 0.65 y ~739 con 0.80, o sea una escala coherente con la
conversión provisional altura→biomasa (`50 + 15 * altura_cm`) y con los
umbrales default del semáforo. Sirve para ordenar potreros de peor a
mejor, no para decisiones finas de carga animal, y se debe reemplazar por
el modelo entrenado apenas haya aforo real.

**Emparejamiento por fecha.** Cada fila de aforo se cruza con la fila del
historial de índices del **mismo potrero** (comparación por nombre exacto,
sin espacios sobrantes) cuya `fecha_escena_usada` esté más cerca en valor
absoluto de la fecha del aforo; si esa diferencia supera
`--ventana-emparejamiento-dias` el punto se descarta y se avisa por
consola con el potrero, la fecha y los días de diferencia. Las variables
de clima de ese punto se calculan sobre la fecha de la **escena** (no la
del aforo): `precip_30d_mm` es la suma de `PRECTOTCORR` y `temp_media_c`
el promedio de `T2M` de los 30 días previos incluyendo ese día, ignorando
los `-999` de NASA POWER. Para predecir se usa la escena más reciente de
cada potrero **que tenga NDVI o SAVI utilizables**: la fila más reciente
puede venir vacía porque ese día el potrero estaba bajo una nube, y ahí es
preferible el último dato real (de hace unos días) antes que quedarse sin
estimación. Un potrero sin ninguna fila en el historial, o sin ninguna con
índices utilizables, queda en `sin_datos` en vez de romper la corrida.

## Pruebas

```bash
pip install -r requirements-dev.txt
pytest
```

Cubren la fórmula provisional, la calibración altura→biomasa, el parseo
de clima NASA POWER (incluyendo el bloque de cabecera y los `-999`), el
emparejamiento aforo↔índices por fecha/ventana, la comparación Random
Forest vs. regresión lineal, y tres corridas completas del script como
subproceso (igual a como lo invoca el backend): sin aforo, modo `predict`
sin modelo guardado, y un potrero sin ninguna consulta satelital todavía.
