/** Mismo formato que el backend (articulia.agent.state.CITA_RE): "[LFT, art. 61]". */
const CITA_RE = /\[([A-Z]+),\s*(art\.|transitorio)\s*([^\]]+?)\]/g

export interface CitaRef {
  ley: string
  numero: string
  transitorio: boolean
  etiqueta: string
}

export type Segment = { type: 'text'; text: string } | { type: 'cita'; cita: CitaRef }

/** Parte una respuesta en texto y citas para pintar cada cita como botón. */
export function splitCitations(texto: string): Segment[] {
  const out: Segment[] = []
  let last = 0
  for (const m of texto.matchAll(CITA_RE)) {
    const start = m.index ?? 0
    if (start > last) out.push({ type: 'text', text: texto.slice(last, start) })
    out.push({
      type: 'cita',
      cita: {
        ley: m[1],
        numero: m[3].trim(),
        transitorio: m[2] === 'transitorio',
        etiqueta: m[0],
      },
    })
    last = start + m[0].length
  }
  if (last < texto.length) out.push({ type: 'text', text: texto.slice(last) })
  return out
}

/** Etiqueta corta para un botón: "LFT 61", "CPEUM T. Primero". */
export function shortLabel(c: { ley: string; numero: string; transitorio?: boolean }): string {
  return c.transitorio ? `${c.ley} T. ${c.numero}` : `${c.ley} ${c.numero}`
}

/**
 * Convierte el texto de un artículo (con los saltos de línea del PDF) en párrafos:
 * un salto doble separa párrafos; un salto simple es solo el ancho de la página.
 */
export function toParagraphs(texto: string): string[] {
  return texto
    .split(/\n{2,}/)
    .map((p) => p.replace(/\s*\n\s*/g, ' ').trim())
    .filter(Boolean)
}

/** Id del artículo en la base, igual que en el backend: "LFT-61", "LFT-47_Bis", "CPEUM-T-Primero". */
export const citaId = (c: { ley: string; numero: string; transitorio?: boolean }): string =>
  `${c.transitorio ? `${c.ley}-T` : c.ley}-${c.numero.replace(/ /g, '_')}`

/** "Título TERCERO" (así viene en el PDF) -> "Título Tercero", sin tocar "Capítulo VIII". */
export const suavizar = (s: string) =>
  s.replace(/(?<![\p{L}])[A-ZÁÉÍÓÚÑ]{4,}(?![\p{L}])/gu, (w) =>
    /^[IVXLC]+$/.test(w) ? w : w[0] + w.slice(1).toLowerCase(),
  )
