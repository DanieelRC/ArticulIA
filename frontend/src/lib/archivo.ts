import type { AskResponse, Paso } from './api'

/** Paso con el momento en que llegó (ms desde que se envió la pregunta). */
export type PasoT = Paso & { t: number }

export interface Turno {
  folio: number
  pregunta: string
  leyes: string[]
  pasos: PasoT[]
  /** Texto parcial mientras el modelo escribe. */
  texto: string
  respuesta?: AskResponse
  estado: 'pensando' | 'listo' | 'error' | 'detenido'
  error?: string
  status?: number
  /** Veces que el verificador rechazó un borrador. */
  descartes: number
  inicio: number
  ms?: number
}

/** Un expediente agrupa las preguntas de una sesión; cada pregunta es un folio. */
export interface Expediente {
  id: string
  titulo: string
  creado: number
  turnos: Turno[]
}

export interface Archivo {
  folio: number // último folio usado
  expedientes: Expediente[]
}

const KEY = 'articulia.archivo.v1'
const MAX_EXPEDIENTES = 30

export const archivoVacio = (): Archivo => ({ folio: 0, expedientes: [] })

/** Lee el archivo del navegador. Nunca lanza: sin almacenamiento, empieza vacío. */
export function cargarArchivo(): Archivo {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return archivoVacio()
    const a = JSON.parse(raw) as Archivo
    if (typeof a.folio !== 'number' || !Array.isArray(a.expedientes)) return archivoVacio()
    // Una pregunta que quedó a medias al cerrar la pestaña ya no está en curso.
    for (const e of a.expedientes)
      for (const t of e.turnos) if (t.estado === 'pensando') t.estado = 'detenido'
    return a
  } catch {
    return archivoVacio()
  }
}

/** Guarda el archivo; si no cabe, descarta los expedientes más viejos y reintenta. */
export function guardarArchivo(a: Archivo): void {
  let expedientes = a.expedientes.filter((e) => e.turnos.length > 0).slice(0, MAX_EXPEDIENTES)
  while (true) {
    try {
      localStorage.setItem(KEY, JSON.stringify({ folio: a.folio, expedientes }))
      return
    } catch {
      if (expedientes.length <= 1) return // sin espacio o sin permiso: se trabaja sin guardar
      expedientes = expedientes.slice(0, -1)
    }
  }
}

export const folioTxt = (n: number) => String(n).padStart(4, '0')

export const nuevoId = () => `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
