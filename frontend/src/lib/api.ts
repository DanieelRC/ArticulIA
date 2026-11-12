import { SSEParser } from './sse'

/** Base de la API: el proxy de Vite (dev) o nginx (Docker) redirigen /api a FastAPI. */
export const API_BASE: string = import.meta.env.VITE_API_URL ?? '/api'

export interface Law {
  clave: string
  nombre: string
  articulos: number
  fecha_ultima_reforma: string | null
  url: string
}

export interface Cita {
  id: string
  ley: string
  numero: string
  etiqueta: string
  url: string
}

export interface AskResponse {
  respuesta: string
  citas: Cita[]
  sin_evidencia: boolean
}

export interface Article {
  id: string
  ley: string
  ley_nombre: string
  numero: string
  tipo: 'articulo' | 'transitorio'
  derogado: boolean
  titulo: string | null
  capitulo: string | null
  seccion: string | null
  texto: string
  reformas: string[]
  fecha_ultima_reforma: string | null
  url: string
}

/** Paso del agente emitido por /ask/stream. */
export interface Paso {
  nodo: 'razonar' | 'herramientas' | 'generar' | 'verificar' | 'abstenerse'
  mensaje: string
  herramientas?: { nombre: string; args: Record<string, unknown> }[]
  articulos?: string[]
  problemas?: string[]
}

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function getJSON<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { signal })
  if (!res.ok) throw new ApiError(res.status, await errorDetail(res))
  return res.json() as Promise<T>
}

async function errorDetail(res: Response): Promise<string> {
  try {
    const body = await res.json()
    if (typeof body.detail === 'string') return body.detail
    if (Array.isArray(body.detail)) return body.detail.map((d: { msg: string }) => d.msg).join('; ')
  } catch {
    /* cuerpo no JSON */
  }
  return `Error ${res.status}`
}

export const getLaws = (signal?: AbortSignal) => getJSON<Law[]>('/laws', signal)

export const getArticle = (ley: string, numero: string, signal?: AbortSignal) =>
  getJSON<Article>(`/articles/${encodeURIComponent(ley)}/${encodeURIComponent(numero)}`, signal)

export interface StreamHandlers {
  onPaso: (paso: Paso) => void
  onRespuesta: (respuesta: AskResponse) => void
}

/** Llama a POST /ask/stream y reparte los eventos. Lanza ApiError si la API falla. */
export async function askStream(
  pregunta: string,
  leyes: string[],
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${API_BASE}/ask/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({ pregunta, leyes: leyes.length ? leyes : null }),
    signal,
  })
  if (!res.ok || !res.body) throw new ApiError(res.status, await errorDetail(res))

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
  const parser = new SSEParser()
  let terminado = false
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    for (const ev of parser.push(value)) {
      const data = JSON.parse(ev.data)
      if (ev.event === 'paso') handlers.onPaso(data as Paso)
      else if (ev.event === 'respuesta') {
        handlers.onRespuesta(data as AskResponse)
        terminado = true
      } else if (ev.event === 'error') throw new ApiError(500, data.detail ?? 'Error del agente')
    }
  }
  if (!terminado) throw new ApiError(500, 'La conexión se cerró antes de terminar la respuesta.')
}
