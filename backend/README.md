# Backend — SAD

API minima (FastAPI) que conecta la app ([`src/`](../src/), vistas "Mis
potreros" y "Registrar medicion") con las piezas de Python que ya existen
en el repo: el GeoJSON de potreros, el script de indices de Earth Engine
([`earth-engine/`](../earth-engine/)) y el script de modelo de prediccion
de biomasa ([`modelo/`](../modelo/)). Es una capa fina de orquestacion: no
reimplementa la logica de esos scripts, los invoca como subprocesos y
lee/escribe los mismos archivos Excel que ellos usan.

## 1. Requisitos previos

- Python 3.10+.
- Ya haber configurado la autenticacion de Earth Engine (ver
  [`earth-engine/README.md`](../earth-engine/README.md) — cuenta,
  proyecto de Google Cloud, `ee.Authenticate()`). El backend no vuelve a
  pedir login: usa las credenciales que ya quedaron guardadas en tu
  usuario al correr ese paso.
- Un `potreros.geojson` exportado desde SAD, en la raiz del
  repo (o en la ruta que definas en `GEOJSON_PATH`).

## 2. Instalar dependencias

El backend en si solo necesita FastAPI y uvicorn, pero como llama al
script de Earth Engine como subproceso **con el mismo interprete de
Python**, ese interprete tambien necesita las dependencias de
`earth-engine/`. Instala ambos requirements en el mismo entorno:

```bash
cd backend
pip install -r requirements.txt
pip install -r ../earth-engine/requirements.txt
```

## 3. Configurar variables de entorno

```bash
copy .env.example .env    # en PowerShell / Windows
# cp .env.example .env    # en Linux/Mac
```

Edita `.env` y completa al menos `EE_PROJECT` (el ID de tu proyecto de
Google Cloud para Earth Engine). El resto tiene valores por defecto
razonables para desarrollo local:

- `CLIMA_PATH` (opcional): ruta a un archivo de clima diario en formato
  NASA POWER (descargable gratis en
  https://power.larc.nasa.gov/data-access-viewer/ para las coordenadas de
  tu finca). Sin esto, el modelo entrena y predice solo con los indices
  de satelite.
- `UMBRAL_ROJO` / `UMBRAL_AMBAR` (default `300`/`500`): umbrales del
  semaforo en kg de materia seca por hectarea. Ajustalos con el criterio
  del productor de la finca.

## 4. Levantar el servidor

```bash
uvicorn main:app --reload
```

Por defecto queda en `http://localhost:8000`. La documentacion
interactiva (generada automaticamente por FastAPI) queda en
`http://localhost:8000/docs`.

## Endpoints

### `POST /api/geojson`

Cuerpo: el GeoJSON completo (`FeatureCollection`) que arma la pestaña
"Dibujar potreros" (`Usar estos potreros en la app`). Lo guarda en
`GEOJSON_PATH` y **reinicia** `potreros_estado.xlsx` con los potreros de
ese GeoJSON, todos en `"sin_datos"` (el estado viejo no se conserva:
cambio la geometria, los indices satelitales anteriores ya no aplican
necesariamente). Devuelve el mismo formato que `GET /api/potreros`.

### `DELETE /api/potreros/{nombre}`

Borra ese potrero del GeoJSON (`GEOJSON_PATH`) y de `potreros_estado.xlsx`
-- para que un potrero borrado en la pestaña "Dibujar potreros" desaparezca
tambien de "Mis potreros", "Registrar medicion" y "Estadisticas", no solo
del dibujo. El aforo y el historial de indices de ese potrero NO se
borran (quedan como historial). 404 si no existe. Devuelve el mismo
formato que `GET /api/potreros`.

### `GET /api/potreros`

Devuelve el ultimo estado conocido de cada potrero (leido de
`data/potreros_estado.xlsx`, que este mismo backend mantiene). Si es la
primera vez que se corre, genera ese archivo a partir del GeoJSON con
todos los potreros en estado `"sin_datos"`.

Formato de respuesta:

```json
{
  "finca": "Mi finca",
  "actualizado": "2026-09-21T10:00:00",
  "modelo": {
    "algoritmo": "random_forest",
    "rmse": 85.3,
    "r2": 0.81,
    "n_muestras_entrenamiento": 14,
    "entrenado_el": "2026-09-20T18:00:00"
  },
  "potreros": [
    {
      "nombre": "Potrero 1",
      "estado": "verde",
      "biomasa_kg_ha": 620.4,
      "fecha": "2026-09-18",
      "fuente_prediccion": "modelo_entrenado"
    }
  ]
}
```

`modelo` es `null` mientras no se haya corrido ninguna prediccion todavia.
`fuente_prediccion` de cada potrero es `"modelo_entrenado"` cuando ya hay
suficiente aforo real para haber entrenado, o `"formula_provisional"`
cuando la estimacion viene de una formula basada en literatura (sin
calibrar con datos de campo) — la app del productor debe mostrar esa
diferencia de forma visible.

### `POST /api/potreros/{nombre}/aforo`

Cuerpo (JSON):

```json
{
  "altura_cm_1": 12.5,
  "altura_cm_2": 14.0,
  "altura_cm_3": 13.2,
  "fecha": "2026-09-21"
}
```

`fecha` es opcional (por defecto, hoy). Valida que las tres alturas sean
numeros entre 0 y 200 cm. Agrega la fila a
`data/aforo_campo.xlsx` — el mismo archivo que va a consumir
`modelo/entrenar_predecir.py` cuando se implemente. Es un Excel normal:
lo puedes abrir para revisarlo o corregir algo a mano cuando quieras (el
backend lee las columnas por nombre de encabezado, no por posicion).

### `POST /api/predecir`

Sin cuerpo. En orden:

1. Corre `earth-engine/extraer_indices.py` para la fecha de hoy y todos
   los potreros del GeoJSON, y agrega el resultado (una fila por potrero)
   a `data/indices_historial.xlsx` — este archivo solo CRECE, nunca se
   sobreescribe, porque el modelo necesita el historial completo para
   poder cruzar cada medicion de aforo con el indice de satelite de esa
   misma fecha.
2. Corre `modelo/entrenar_predecir.py` para actualizar
   `data/potreros_estado.xlsx` (reentrena si hay aforo nuevo desde la
   ultima vez, si no predice con el modelo ya guardado; si todavia no hay
   aforo suficiente, usa una formula provisional — ver
   [`modelo/README.md`](../modelo/README.md) para el detalle completo).
3. Si todo sale bien, devuelve la lista de potreros actualizada (mismo
   formato que `GET /api/potreros`).

Si `modelo/entrenar_predecir.py` todavia no existe en el repo, este paso
responde con un error 501 explicando eso — el paso 1 (indices reales de
Earth Engine) corre igual y queda guardado.

Puede tardar varios segundos (llamada real a Earth Engine): el frontend
debe mostrar un estado de "procesando" mientras espera la respuesta.

Si algo falla (sin escena de satelite sin nubes, proyecto de Earth Engine
mal configurado, etc.) responde con un error HTTP con un mensaje en
español explicando que paso y que hacer, no un error generico.

## Datos que genera (`backend/data/`)

Esta carpeta se crea sola la primera vez que se usa la API. No hay ninguna
base de datos: todo queda en archivos Excel normales, que puedes abrir,
revisar o corregir a mano en cualquier momento. No se suben al
repositorio (ver `.gitignore`) porque son datos propios de cada finca:

- `potreros_estado.xlsx` — hoja "Potreros" (nombre, estado, biomasa,
  fecha, fuente de la prediccion), hoja "Finca" (nombre de la finca,
  fecha de la ultima actualizacion) y hoja "Modelo_Info" (que algoritmo
  se uso, que tan bueno es, cuando se entreno). Es la fuente de verdad
  que lee `GET /api/potreros`.
- `aforo_campo.xlsx` — hoja "Aforo" con el historial de mediciones de
  campo.
- `indices_historial.xlsx` — historial acumulado de indices de satelite
  (una fila por potrero cada vez que se corre `/api/predecir`), lo usa
  `modelo/entrenar_predecir.py` para entrenar.
- `modelo_entrenado.joblib` — el modelo ya entrenado (Random Forest o
  regresion lineal, el que haya ganado), para no tener que reentrenar en
  cada prediccion.

Si editas `potreros_estado.xlsx` o `aforo_campo.xlsx` a mano, respeta los
nombres de las columnas del encabezado (el backend los busca por nombre,
no por posicion) — puedes reordenar columnas o agregar otras de tu propia
cosecha sin problema, esas simplemente se ignoran.

## CORS

Configurable con `CORS_ORIGINS` en `.env` (lista separada por coma, o
`*` para cualquier origen). En desarrollo, `*` es suficiente para que la
app del productor (corriendo en otro puerto) pueda llamar a esta API.

## Pruebas

```bash
pip install -r requirements-dev.txt
pytest
```

No necesitan credenciales de Earth Engine ni conexion a internet: usan
un GeoJSON y una carpeta de datos temporales por prueba (nunca tocan
`backend/data/` real), y prueban la validacion de `POST /api/predecir`
solo hasta donde no hace falta invocar Earth Engine de verdad.
