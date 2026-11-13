import { useState } from 'react'
import type { PasoT } from '../lib/archivo'

const HERRAMIENTAS: Record<string, string> = {
  buscar_articulos: 'Buscar',
  obtener_articulo: 'Leer artículo',
  comparar: 'Comparar',
}

function detalle(paso: PasoT): string | null {
  if (paso.herramientas?.length) {
    return paso.herramientas
      .map((h) => {
        const nombre = HERRAMIENTAS[h.nombre] ?? h.nombre
        const args = Object.values(h.args).flat().filter(Boolean).join(' · ')
        return args ? `${nombre}: ${args}` : nombre
      })
      .join('\n')
  }
  if (paso.articulos?.length) return paso.articulos.join('  ')
  if (paso.problemas?.length) return paso.problemas.join('\n')
  return null
}

const seg = (ms: number) => `${(ms / 1000).toFixed(1)} s`

interface Props {
  pasos: PasoT[]
  activo: boolean
  ms?: number
}

/** Bitácora del trámite: qué hizo el agente y cuándo. Se pliega al terminar. */
export function Steps({ pasos, activo, ms }: Props) {
  const [abierto, setAbierto] = useState(false)
  if (!pasos.length && !activo) return null
  const ver = activo || abierto

  return (
    <div className="bitacora">
      {!activo && (
        <button
          type="button"
          className="bitacora-toggle"
          aria-expanded={abierto}
          onClick={() => setAbierto((v) => !v)}
        >
          {abierto ? 'Ocultar bitácora' : 'Ver bitácora'} · {pasos.length} pasos
          {ms ? ` en ${seg(ms)}` : ''}
        </button>
      )}
      {ver && (
        <ol className="bitacora-lista">
          {pasos.map((p, i) => {
            const d = detalle(p)
            const actual = activo && i === pasos.length - 1
            return (
              <li key={i} className={`asiento${actual ? ' asiento-actual' : ''}`}>
                <span className="asiento-hora">{seg(p.t)}</span>
                <span className="asiento-msg">{p.mensaje}</span>
                {d && <span className="asiento-detalle">{d}</span>}
              </li>
            )
          })}
          {activo && pasos.length === 0 && (
            <li className="asiento asiento-actual">
              <span className="asiento-hora">0.0 s</span>
              <span className="asiento-msg">Recibiendo la pregunta</span>
            </li>
          )}
        </ol>
      )}
    </div>
  )
}
