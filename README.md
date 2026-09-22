# SAD — Sistema de Apoyo a Decisiones

App web para fincas ganaderas, con cuatro vistas en un mismo sitio (React +
Vite):

1. **Dibujar potreros** — dibuja los potreros de cualquier finca sobre su
   contorno real y úsalos directamente en la app (o expórtalos como GeoJSON
   estándar, abrible en QGIS, Google Earth, Google Earth Engine, geojson.io, etc).
2. **Mis potreros** — ve el estado (verde/ámbar/rojo) de cada potrero,
   estimado a partir de índices de vegetación de satélite y del modelo de
   biomasa, con un botón para actualizar la recomendación del día.
3. **Registrar medición** — carga el aforo de campo (altura de pasto)
   desde el celular, para calibrar el modelo con datos reales de tu finca.
4. **Estadísticas** — qué tan bueno es el modelo entrenado (Random Forest
   vs. regresión lineal, error, variables que más pesan).

No está atada a ningún proyecto, país o sistema de coordenadas específico:
solo necesita el perímetro de la finca en latitud/longitud (lo puedes sacar
de Google Maps haciendo clic derecho sobre cada esquina y copiando las
coordenadas, o de Google Earth).

## Requisitos

- [Node.js](https://nodejs.org/) versión 18 o superior (trae npm incluido)
  — para esta app.
- [Python](https://www.python.org/) 3.10 o superior — para
  [`earth-engine/`](earth-engine/), [`modelo/`](modelo/) y
  [`backend/`](backend/), las piezas que alimentan las vistas "Mis
  potreros" y "Registrar medición".
- Una cuenta gratuita de Google Earth Engine y un proyecto de Google
  Cloud, si vas a usar el pipeline completo (no hace falta solo para
  dibujar potreros) — ver [`earth-engine/README.md`](earth-engine/README.md).

## Instalación y uso

```bash
# 1. Clona el repositorio (o entra a la carpeta si ya lo tienes)
git clone https://github.com/DrkGodEater9/sad-ganaderia.git
cd sad-ganaderia

# 2. Instala las dependencias (solo la primera vez)
npm install

# 3. Levanta el servidor de desarrollo
npm run dev
```

Esto te va a dar una dirección tipo `http://localhost:5173` — ábrela en tu
navegador. Vas a ver cuatro pestañas abajo: "Dibujar potreros", "Mis
potreros", "Registrar medición" y "Estadísticas".

La pestaña "Dibujar potreros" funciona sola, sin nada más que instalar
(salvo el botón "Usar estos potreros en la app", que sí necesita el
backend). Las otras tres necesitan el backend corriendo (ver "Puesta en
marcha del sistema completo" más abajo) — sin él, muestran un mensaje
claro pidiendo reintentar en vez de fallar en silencio.

## Cómo se usa (Dibujar potreros)

1. Pega el contorno de la finca (latitud, longitud de cada esquina, uno por
   línea) y dale a "Usar este contorno".
2. Haz clic dentro del contorno para ir marcando las esquinas de cada
   potrero. Cierra el polígono haciendo clic cerca del primer punto, o con
   el botón "Cerrar potrero".
3. Ponle nombre a cada potrero según lo vayas cerrando.
4. Cuando termines, dale a **"Usar estos potreros en la app"** — los deja
   listos para las pestañas "Mis potreros" y "Registrar medición" (necesita
   el backend corriendo, ver más abajo). "Descargar GeoJSON" también sigue
   ahí, por si quieres el archivo para abrirlo en QGIS, Google Earth
   Engine, etc.

## Estructura del proyecto

```
sad-ganaderia/
├── index.html
├── package.json
├── vite.config.js
├── eslint.config.js
├── README.md
├── DESIGN.md                  # sistema de diseño de las cuatro vistas
├── .env.example                # VITE_API_BASE_URL (URL del backend)
├── src/
│   ├── main.jsx                  # punto de entrada de React
│   ├── App.jsx                   # navegación entre las cuatro vistas
│   ├── index.css                 # sistema de diseño "Campo Claro"
│   ├── components/
│   │   ├── BoundaryInput.jsx     # "Dibujar potreros" paso 1: contorno de la finca
│   │   ├── MapCanvas.jsx         # "Dibujar potreros": lienzo interactivo (SVG)
│   │   ├── Toolbar.jsx           # "Dibujar potreros": deshacer/cancelar/cerrar
│   │   ├── PotreroTable.jsx      # "Dibujar potreros": tabla de potreros ya dibujados
│   │   ├── MisPotreros.jsx       # vista "Mis potreros"
│   │   ├── RegistrarMedicion.jsx # vista "Registrar medición"
│   │   ├── EstadisticasModelo.jsx # vista "Estadísticas"
│   │   ├── Iconos.jsx            # iconos SVG del semáforo, compartidos
│   │   └── ErrorBoundary.jsx     # red de seguridad ante errores inesperados
│   └── utils/
│       ├── geo.js                 # proyección lat/lon <-> metros locales, área
│       ├── parseBoundary.js       # parseo del texto pegado por el usuario
│       ├── parseBoundaryFile.js   # parseo de un contorno subido como KML/GeoJSON
│       ├── exportGeoJSON.js       # construcción y descarga del archivo GeoJSON (botón "Descargar GeoJSON")
│       ├── api.js                 # cliente HTTP hacia el backend (incluye guardar el GeoJSON en la app)
│       └── formato.js             # formateo de fechas compartido
├── earth-engine/               # ver "El resto del sistema"
├── modelo/                     # ver "El resto del sistema"
└── backend/                    # ver "El resto del sistema"
```

## El resto del sistema

Este repositorio también contiene las piezas en Python que alimentan las
vistas "Mis potreros", "Registrar medición" y "Estadísticas" (potreros →
índices satelitales → predicción), cada una documentada por separado:

- [`earth-engine/`](earth-engine/) — script en Python que toma el GeoJSON
  exportado por esta app y calcula NDVI, GNDVI, NDRE, SAVI y EVI por cada
  potrero usando imágenes Sentinel-2 de Google Earth Engine.
- [`modelo/`](modelo/) — script que entrena y corre el modelo de
  predicción de biomasa (compara Random Forest vs. regresión lineal,
  calibrado con aforo de campo real). Mientras no haya aforo suficiente
  usa una fórmula provisional basada en literatura, marcada como tal.
- [`backend/`](backend/) — API mínima (FastAPI) que orquesta las piezas
  de arriba como subprocesos y las expone a esta app.
- [`DESIGN.md`](DESIGN.md) — sistema de diseño de las cuatro vistas
  (paleta, tipografía, reglas de componentes).

`earth-engine/`, `modelo/` y `backend/` son proyectos Python separados
(no forman parte del build de Vite/React), cada uno con su propio
`README.md`.

## Puesta en marcha del sistema completo, paso a paso

Los pasos de arriba ("Instalación y uso") ya dejan corriendo la app. Si
además quieres que "Mis potreros" y "Registrar medición" funcionen de
verdad (no solo el mensaje de "backend no disponible"), sigue estos pasos
en orden la primera vez — cada uno enlaza al README de esa carpeta para
más detalle.

**1. Dibuja los potreros de tu finca.** Con la app corriendo (`npm run
dev`), en la pestaña "Dibujar potreros". Para guardarlos tienes dos
opciones:

- **"Usar estos potreros en la app"** — necesita el backend del paso 4 ya
  corriendo; los guarda directo donde `GEOJSON_PATH` espera, sin
  descargar ni copiar ningún archivo a mano. Si el backend todavía no
  está arriba, vuelve a este paso después de terminar el 4.
- **"Descargar GeoJSON"** — no necesita el backend: te guarda el archivo
  para copiarlo tú mismo a la raíz del repo como `potreros.geojson`.

**2. Configura Earth Engine** (una sola vez por computador):

```bash
cd earth-engine
pip install -r requirements.txt
python -c "import ee; ee.Authenticate()"   # abre el navegador, inicia sesion con Google
```

Sigue [`earth-engine/README.md`](earth-engine/README.md) si no tienes
todavía una cuenta gratuita ni un proyecto de Google Cloud — anota el ID
de ese proyecto, lo necesitas en el paso 4.

**3. Instala las dependencias del modelo.** No hace falta correrlo a
mano: lo invoca el backend automáticamente en cada predicción.

```bash
cd modelo
pip install -r requirements.txt
```

**4. Levanta el backend** (orquesta las dos piezas anteriores y expone la
API para esta app):

```bash
cd backend
pip install -r requirements.txt
copy .env.example .env      # PowerShell/Windows -- en Linux/Mac: cp .env.example .env
```

Edita `backend/.env` y completa al menos `EE_PROJECT` (el ID del paso 2)
y, si tu `potreros.geojson` no quedó en la raíz del repo, `GEOJSON_PATH`
con su ruta real. Luego:

```bash
uvicorn main:app --reload
```

Queda corriendo en `http://localhost:8000` (documentación interactiva en
`http://localhost:8000/docs`). Detalle completo de cada variable y
endpoint en [`backend/README.md`](backend/README.md).

**5. Listo.** Con `npm run dev` corriendo (paso "Instalación y uso") y el
backend arriba, entra a las pestañas "Mis potreros" o "Registrar
medición" — ya deberían funcionar (en estado "sin datos" la primera vez).
Dale a "Actualizar recomendaciones" para traer los índices de satélite de
hoy y calcular el estado de cada potrero.

Por defecto la app busca el backend en `http://localhost:8000`. Si corre
en otra dirección (por ejemplo, ya en producción), copia `.env.example` a
`.env` en la raíz del repo y cambia `VITE_API_BASE_URL` antes de
`npm run build`.

## Cómo funciona la proyección

El primer punto del contorno que pegues se usa como referencia. A partir de
ahí, todo se convierte a una cuadrícula plana en metros (proyección
equirectangular local), que es suficientemente precisa para el tamaño de
una finca. El archivo GeoJSON que descargas ya viene convertido de vuelta a
latitud/longitud estándar, así que es compatible con cualquier otro
programa.

## Calidad de código

```bash
npm run lint    # revisa src/
```

Cada pieza en Python tiene sus propias pruebas automatizadas (no
dependen de credenciales de Earth Engine ni tocan datos reales):

```bash
cd backend  && pip install -r requirements-dev.txt && pytest
cd modelo   && pip install -r requirements-dev.txt && pytest
```

`earth-engine/` no tiene pruebas automatizadas: su lógica central son
llamadas reales a la API de Earth Engine (mockearla bien vale menos que
verificarla a mano contra datos reales, que es como se probó).

## Publicar / compartir la aplicación

Antes de publicar, si el backend no va a correr en `http://localhost:8000`,
copia `.env.example` a `.env` en la raíz y cambia `VITE_API_BASE_URL` por
la URL real donde quede corriendo (ver [`backend/README.md`](backend/README.md)
para desplegar el backend por separado).

Para generar la versión de producción (archivos estáticos que puedes subir
a cualquier hosting: Vercel, Netlify, GitHub Pages, etc.):

```bash
npm run build
```

Esto genera una carpeta `dist/` con todo listo para desplegar.

## Próximos pasos posibles

- Añadir un campo de notas u otros datos por potrero para exportarlos
  junto con la geometría.
- Recolectar aforo de campo real (mínimo ~8 mediciones para que
  [`modelo/entrenar_predecir.py`](modelo/README.md) entrene de verdad en
  vez de usar la fórmula provisional) y, en cuanto se pesen unas 4-5
  muestras de pasto cortado, recalibrar `--calibracion-a`/
  `--calibracion-b` (altura → biomasa) con datos reales de la finca.
