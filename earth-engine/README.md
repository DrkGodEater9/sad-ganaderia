# Earth Engine — indices de vegetacion por potrero

Esta carpeta es una pieza **aparte** del proyecto SAD: no forma
parte de la app React/Vite de `src/`, es un script de Python independiente
que toma el GeoJSON que descargas de SAD y calcula indices de
vegetacion (NDVI, GNDVI, NDRE, SAVI, EVI) por cada potrero usando imagenes
Sentinel-2 de Google Earth Engine. Reemplaza el flujo manual de copiar y
pegar scripts en el editor web de Earth Engine.

## 1. Cuenta de Earth Engine (gratis, sin tarjeta de credito)

1. Entra a https://code.earthengine.google.com/register y elige el modo
   **"Uso no comercial"** (unpaid / noncommercial) al registrarte, no el de
   uso comercial — asi no te va a pedir datos de tarjeta de credito.
2. Regístrate con tu cuenta de Google y espera la confirmacion (suele ser
   inmediata o toma pocos minutos).
3. Crea (o reutiliza) un proyecto de Google Cloud asociado a Earth Engine
   desde https://console.cloud.google.com/ — el nombre/ID de ese proyecto
   es el que le vas a pasar al script con `--proyecto` o con la variable de
   entorno `EE_PROJECT`.

## 2. Instalar dependencias

```bash
cd earth-engine
pip install -r requirements.txt
```

## 3. Autenticarse (solo la primera vez)

El script hace esto automaticamente si no encuentra credenciales guardadas,
pero tambien lo puedes correr a mano para verificar que quedo bien
configurado:

```bash
python -c "import ee; ee.Authenticate()"
```

Esto abre el navegador para iniciar sesion con tu cuenta de Google y
autorizar el acceso a Earth Engine. Las credenciales quedan guardadas en tu
computador, asi que no lo vuelve a pedir en las siguientes corridas.

## 4. Uso

```bash
python extraer_indices.py \
  --geojson ../potreros.geojson \
  --fecha 2026-09-20 \
  --proyecto mi-proyecto-gee
```

Esto busca, dentro de una ventana de +/-10 dias alrededor del 2026-09-20,
la escena Sentinel-2 mas cercana a esa fecha que deje indices utilizables,
calcula los indices por cada potrero del archivo `../potreros.geojson`, y
guarda el resultado en `indices_potreros.csv` (en la misma carpeta desde
donde corras el script).

### Parametros

| Parametro | Obligatorio | Default | Descripcion |
|---|---|---|---|
| `--geojson` | si | — | Ruta al GeoJSON exportado por SAD. |
| `--fecha` | si | — | Fecha objetivo `YYYY-MM-DD` (por ejemplo, la fecha de una jornada de aforo). |
| `--ventana-dias` | no | `10` | Dias antes/despues de `--fecha` para buscar la escena mas cercana sin nubes. |
| `--umbral-nubes` | no | `40` | Porcentaje maximo de `CLOUDY_PIXEL_PERCENTAGE` aceptado. |
| `--salida` | no | `indices_potreros.csv` | Ruta del archivo de salida — `.csv` o `.xlsx` segun la extension. |
| `--proyecto` | no* | — | ID del proyecto de Google Cloud para Earth Engine. |

\* `--proyecto` es obligatorio si no defines la variable de entorno
`EE_PROJECT` (por ejemplo `export EE_PROJECT=mi-proyecto-gee` en Linux/Mac,
o `$env:EE_PROJECT="mi-proyecto-gee"` en PowerShell).

Si no encuentra ninguna escena que cumpla las condiciones (nubosidad o
ventana de fechas muy estrictas), el script lo avisa por consola en vez de
fallar en silencio, y sugiere aumentar `--ventana-dias` o `--umbral-nubes`.

### Como elige la escena

`CLOUDY_PIXEL_PERCENTAGE` es el porcentaje de nubes del **tile completo**
de Sentinel-2 (110 x 110 km), no del area de tus potreros: una escena puede
pasar ese filtro y aun asi tener justo los potreros bajo una nube o su
sombra, y quedar sin un solo pixel valido despues del enmascarado por `SCL`.

Por eso el script no se queda con una sola escena: recorre las candidatas de
la ventana de la mas cercana a la mas lejana (hasta 25) y se queda, **para
cada potrero por separado**, con la primera que le haya dejado indices
utilizables. Potreros distintos pueden terminar con escenas de fechas
distintas — cada fila del resultado lleva su propia `fecha_escena_usada` y
`dias_diferencia_con_fecha_objetivo`. Es preferible un dato real de hace
unos dias que ningun dato porque ese dia habia una nube encima.

Un potrero que no consiguio indices en ninguna candidata queda con los
indices vacios (el modelo lo interpreta como `sin_datos`), y el script lo
avisa por consola.

## 5. Que calcula

Sobre la escena Sentinel-2 elegida, primero se enmascaran nubes, sombras y
agua usando la banda `SCL` (se conservan solo las clases 4 = vegetacion,
5 = suelo desnudo y 7 = no vegetado/cobertura baja), y despues se calculan:

- **NDVI** = `normalizedDifference(B8, B4)`
- **GNDVI** = `normalizedDifference(B8, B3)`
- **NDRE** = `normalizedDifference(B8, B5)`
- **SAVI** = `((NIR-RED)/(NIR+RED+0.5))*1.5`
- **EVI** = `2.5*((NIR-RED)/(NIR+6*RED-7.5*BLUE+1))`, limitado al rango `[-1, 1]`

Para cada potrero se calcula la media y la desviacion estandar de cada
indice (`reduceRegions`, escala de 10 m), y el CSV final queda con estas
columnas: `potrero`, `fecha_escena_usada`,
`dias_diferencia_con_fecha_objetivo`, y `_mean` / `_stdDev` de cada uno de
los 5 indices.

## Notas

- El nombre de cada potrero sale de la propiedad `nombre` de cada feature
  del GeoJSON (la que genera SAD al exportar) — el script no
  tiene hardcodeado ningun nombre de finca ni coordenada, sirve para
  cualquier GeoJSON con ese formato.
- Si la finca es muy grande y cae en dos tiles distintos de Sentinel-2,
  cada potrero se resuelve con la escena que le sirva (ver "Como elige la
  escena"), asi que no hace falta que un solo tile cubra toda la finca.
