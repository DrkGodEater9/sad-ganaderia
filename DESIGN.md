# Sistema de diseño — SAD

Referencia de colores, tipografía y componentes de la única app frontend
del proyecto (`src/`, React + Vite): tiene cuatro vistas — dibujar
potreros, "Mis potreros", "Registrar medición" y "Estadísticas" — y las
cuatro comparten este mismo sistema visual.

Audiencia: productores ganaderos, muchos de edad avanzada, poco manejo de
tecnología, usando el celular parados en el potrero bajo sol directo. Todo
el diseño parte de ahí: letra grande, alto contraste, sin adornos que no
aporten, nada de modo oscuro (para no depender de la configuración del
teléfono y porque bajo sol directo el fondo claro se lee mejor).

## Concepto — "Campo Claro"

Fondo claro con un dejo verde muy tenue (evoca pasto/campo abierto sin
caer en el cliché de fondo crema + serif), superficies blancas para las
tarjetas de contenido, y un azul profundo como color de marca —
deliberadamente **distinto** del verde/ámbar/rojo del semáforo de estado,
para que el color de marca nunca se confunda con un estado del potrero.

## Colores

```css
/* Base */
--color-fondo:        #F4F7EF;  /* fondo general, verde muy tenue */
--color-fondo-alto:    #EAF0E2;  /* secciones/franjas dentro del fondo */
--color-superficie:    #FFFFFF;  /* tarjetas, formularios */
--color-texto:         #263129;  /* texto principal, verde-gris muy oscuro (no negro puro) */
--color-texto-suave:   #5B6B5E;  /* texto secundario */
--color-borde:         #D9E0D2;  /* bordes sutiles */

/* Marca (nunca se usa para estados) */
--color-marca:         #2C5F82;
--color-marca-oscuro:  #1F4763;  /* hover/presionado */
--color-marca-tenue:   #E4EEF5;  /* fondos tenues relacionados a marca */

/* Semáforo de estado (solo para esto) */
--color-verde:         #2F8F4E;
--color-verde-tenue:   #E4F4E8;
--color-ambar:         #C98A1F;
--color-ambar-tenue:   #FBF0DD;
--color-rojo:          #C1483C;
--color-rojo-tenue:    #FBE7E4;
--color-neutro:        #7C7F78;  /* "sin datos todavía" */
--color-neutro-tenue:  #EEEFEA;
```

## Tipografía

Una sola familia en toda la app: **Atkinson Hyperlegible** (Google Fonts,
gratuita). Se eligió a propósito porque fue diseñada por el Braille
Institute específicamente para maximizar la legibilidad de personas
mayores y con baja visión — separa muy bien caracteres que se confunden
(I / l / 1, O / 0), que es justo el público de esta app. Nada de serif
(evita el cliché "fondo crema + serif") ni monoespaciada para datos.

```css
--fuente: "Atkinson Hyperlegible", -apple-system, "Segoe UI", Roboto, Arial, sans-serif;
```

- Texto normal: 400, ~17–18px base (nunca menos de 16px).
- Títulos y botones: 700.
- Números importantes (biomasa, alturas): mismo tipo de letra, en 700, con
  `font-variant-numeric: tabular-nums` para que alineen — sin usar fuente
  monoespaciada.

## Formas y componentes

- Radios: 16px en tarjetas, 12px en botones/campos. Esquinas suaves pero
  no "burbuja".
- Sin sombras grises genéricas: las tarjetas se diferencian por color de
  borde/fondo tenue según su estado, no por `box-shadow`. Además una
  interfaz plana se lee mejor bajo sol directo.
- Botones: texto en verbo directo ("Guardar medición", "Actualizar
  recomendaciones", "Ver detalle", "Volver a la lista"). Nunca versalitas,
  punto medio, guion largo ni flechas. Alto mínimo 56px, radio 12px, texto
  700 ~17px.
- Estados (verde/ámbar/rojo) solo se usan en el semáforo de potreros — no
  como color de botón de marca ni de navegación.

## Aplicado en

- [`src/index.css`](src/index.css) — las cuatro vistas de la app.
