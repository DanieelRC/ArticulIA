import { useState } from 'react'
import type { Paso } from '../lib/api'

const HERRAMIENTAS: Record<string, string> = {
  buscar_articulos: 'Buscar',
  obtener_articulo: 'Leer artículo',
  comparar: 'Comparar',
}

function detalle(paso: Paso): string | null {
  if (paso.herramientas?.length) {
    return paso.herramientas
      .map((h) => {
        const nombre = HERRAMIENTAS[h.nombre] ?? h.nombre
        const args = Object.values(h.args).flat().filter(Boolean).join(' · ')
        return args ? `${nombre}: ${args}` : nombre
      })
      .join('\n')
  }
  if (paso.articulos?.length) return paso.articulos.join(', ')
  if (paso.problemas?.length) return paso.problemas.join('\n')
  return null
}

interface Props {
  pasos: Paso[]
  activo: boolean
}

/** Línea de tiempo de lo que hace el agente. Se pliega cuando llega la respuesta. */
export function Steps({ pasos, activo }: Props) {
  const [abierto, setAbierto] = useState(false)
  if (!pasos.length && !activo) return null

  const visibles = activo || abierto ? pasos : []
  return (
    <div className="steps">
      {!activo && (
        <button
          type="button"
          className="steps-toggle"
          aria-expanded={abierto}
          onClick={() => setAbierto((v) => !v)}
        >
          {abierto ? 'Ocultar' : 'Ver'} cómo se encontró ({pasos.length} pasos)
        </button>
      )}
      {(activo || abierto) && (
        <ol className="steps-list" aria-live="polite">
          {visibles.map((p, i) => {
            const d = detalle(p)
            const actual = activo && i === pasos.length - 1
            return (
              <li key={i} className={`step step-${p.nodo}${actual ? ' step-current' : ''}`}>
                <span className="step-dot" aria-hidden />
                <span className="step-msg">{p.mensaje}</span>
                {d && <span className="step-detail">{d}</span>}
              </li>
            )
          })}
          {activo && pasos.length === 0 && (
            <li className="step step-current">
              <span className="step-dot" aria-hidden />
              <span className="step-msg">Leyendo la pregunta</span>
            </li>
          )}
        </ol>
      )}
    </div>
  )
}
