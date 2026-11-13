# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
- **Primario: reclutadores técnicos de IA** (CDMX). Llegan desde el CV de Daniel, tienen pocos minutos, prueban una pregunta y quieren ver cómo funciona el sistema y qué tan bien mide.
- **Secundario:** cualquier persona sin formación legal que quiere resolver una duda sobre leyes federales mexicanas.

## Product Purpose
ArticulIA responde preguntas sobre leyes federales mexicanas citando el artículo exacto en que se basa cada afirmación. Si el corpus no contiene evidencia, lo dice en lugar de inventar. Es un proyecto de portafolio; el éxito es que un reclutador entienda en una visita que el sistema cita, verifica y se mide.

## Positioning
Cada cita se comprueba contra los artículos que el agente realmente recuperó, y un verificador rechaza respuestas sin respaldo. La abstención es una función, no un fallo. Las métricas se publican como salgan, lleguen o no a la meta.

## Operating Context
- Corpus: seis leyes (CPEUM, LFT, CCF, LFPDPPP, LFDA, LFPC), texto vigente de la Cámara de Diputados, 5,089 artículos.
- Flujo: pregunta → búsqueda híbrida → redacción con citas `[LFT, art. 61]` → verificación → respuesta o abstención.
- El usuario abre una cita para leer el texto completo del artículo y puede ir al PDF oficial.
- Demo pública en un VPS, con tope de gasto diario y límite por IP: la interfaz debe explicar con claridad cuando se alcanza un límite.

## Capabilities and Constraints
- Respuesta transmitida en vivo (SSE: `paso`, `token`, `borrador_descartado`, `respuesta`, `error`).
- Filtro por ley. Sin preguntas de seguimiento: cada pregunta es independiente.
- Historial de conversaciones guardado solo en el navegador.
- Una consulta tarda varios segundos (búsqueda y verificación); el progreso debe ser visible y honesto.
- Idioma de la interfaz: español de México.
- No es asesoría legal; el aviso debe estar presente.

## Brand Commitments
- Nombre: **ArticulIA**. Autor: **Daniel Rodríguez Carreón**. Enlace al repositorio de GitHub (URL configurable).
- Voz: clara, directa, sin jerga legal innecesaria; honesta sobre lo que no sabe.

## Evidence on Hand
- Métricas reales de `eval/results/` sobre un dataset propio de 60 preguntas (se muestran con fecha, sin maquillar).
- Texto real de los artículos vía `GET /articles/{ley}/{numero}` y lista de leyes vía `GET /laws`.
- No hay testimonios, usuarios ni logotipos de terceros: no inventarlos.

## Product Principles
1. La cita es el producto: siempre visible, siempre comprobable con un clic.
2. Decir "no sé" con la misma dignidad que una respuesta.
3. Mostrar el proceso (buscar, redactar, verificar), no esconderlo.
4. Números reales antes que promesas.

## Accessibility & Inclusion
Contraste AA, navegación completa por teclado, foco visible, respeto a `prefers-reduced-motion`, texto en vivo anunciado sin saturar a lectores de pantalla.
