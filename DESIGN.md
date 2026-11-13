# Diseño · «Expediente sellado»

Sistema visual de ArticulIA. Describe lo que está construido en `frontend/src/index.css`.

## Idea
Cada respuesta es un folio de un trámite. Solo recibe el sello rojo «COTEJADO» cuando sus citas
pasan la verificación. La abstención recibe su propio sello azul, con la misma dignidad.

## Color
| Rol | Token | Valor |
| --- | --- | --- |
| Tinta de sello: campos completos (portada, archivo), citas, botón principal | `--tinta` | `#2a1a6e` |
| Papel seguridad: fondo de trabajo, con guilloché tenue | `--papel` | `#ddebe0` |
| Papel bond: hojas de respuesta, ventanilla, copia del artículo | `--bond` | `#f7faf6` |
| Copia amarilla: acento de acción, hoja de muestra, cabecera del artículo, selección | `--copia` | `#ffe14d` |
| Sello rojo: «Cotejado», folios | `--sello` / `--sello-texto` | `#d42a22` / `#b01f18` |
| Sello azul: abstención | `--azul` | `#1d4e9e` |
| Texto | `--carbon` | `#15131c` |
| Texto secundario (teñido de la tinta, nunca gris neutro) | `--gris-tinta` | `#4a4470` |

Solo modo claro: el uso es de oficina, de día. El violeta ocupa regiones enteras, no acentos.

## Tipografía
- **Archivo Variable** (autoalojada, eje de ancho 62–125 %). Titulares: ancho 62–66 %, peso 900,
  mayúsculas, tope 6rem. Rótulos: ancho 75 %, peso 700, mayúsculas con tracking 0.1em. Texto: ancho 100 %.
- **Literata Variable** (autoalojada) solo para el texto legal del artículo.
- Números de folio y de artículo: Archivo ancho 62 %, peso 900, cifras tabulares.

## Estructura
- Sin tarjetas: la estructura la dan renglones (2px carbón arriba, 1px `--renglon` entre filas),
  folios y perforaciones de la hoja. Radio 2px en controles; las hojas no tienen radio.
- La **cita** es la pieza más pesada del texto: bloque de tinta, condensada 800. En borrador va
  solo con contorno; se entinta al cotejar.
- **Sello** (`Sello` en `components/ui.tsx`): doble marco, inclinación -4°, borde irregular por
  filtro SVG `#tinta`, `mix-blend-mode: multiply`. Tintas: rojo, azul, violeta, negro.
- Iconos propios (`Icono`), un trazo de 1.75, esquinas rectas.

## Movimiento
Una sola pieza autoral: el golpe del sello (escala 2.1 → 1, 380 ms, desaceleración exponencial,
sin rebote). El resto son transiciones cortas de 140–320 ms con `--salida`. Con
`prefers-reduced-motion` todo queda instantáneo.

## Superficies
- **Portada** (`/`): campo de tinta con titular y hoja amarilla de muestra; trámite en tres
  sellos; libro de registro del corpus; constancia de evaluación con dictamen por métrica; cierre en tinta.
- **Consulta** (`/consulta`): archivo en tinta a la izquierda, mesa de papel seguridad al centro,
  ventanilla abajo, copia del artículo a la derecha (pantalla completa bajo 900px).

## No hacer
Tarjetas con sombra suave, degradados, modo oscuro, gris neutro para texto secundario, emoji como
iconos, monoespaciada decorativa, rebotes.
