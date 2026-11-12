import { useEffect, useRef, useState } from 'react'
import { type Article, getArticle } from '../lib/api'
import { type CitaRef, suavizar, toParagraphs } from '../lib/citations'

interface Props {
  cita: CitaRef
  onClose: () => void
}

type Estado =
  | { tipo: 'cargando' }
  | { tipo: 'listo'; articulo: Article }
  | { tipo: 'error'; mensaje: string }

const fecha = (iso: string | null) =>
  iso
    ? new Date(`${iso}T12:00:00`).toLocaleDateString('es-MX', {
        day: 'numeric',
        month: 'long',
        year: 'numeric',
      })
    : null

/** Panel lateral con el texto completo del artículo citado. */
export function ArticlePanel({ cita, onClose }: Props) {
  const [estado, setEstado] = useState<Estado>({ tipo: 'cargando' })
  const cerrarRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    // App monta un panel nuevo por cita (key), así que el estado inicial ya es "cargando".
    const ctrl = new AbortController()
    getArticle(cita.ley, cita.numero, ctrl.signal)
      .then((articulo) => setEstado({ tipo: 'listo', articulo }))
      .catch((e: Error) => {
        if (e.name !== 'AbortError') setEstado({ tipo: 'error', mensaje: e.message })
      })
    return () => ctrl.abort()
  }, [cita.ley, cita.numero])

  useEffect(() => {
    cerrarRef.current?.focus()
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [cita, onClose])

  const art = estado.tipo === 'listo' ? estado.articulo : null
  const titulo = cita.transitorio ? `Transitorio ${cita.numero}` : `Artículo ${cita.numero}`

  return (
    <aside className="panel" aria-label={`${cita.ley}, ${titulo}`}>
      <header className="panel-head">
        <div>
          <p className="panel-law">{art?.ley_nombre ?? cita.ley}</p>
          <h2 className="panel-title">{titulo}</h2>
          {art && (art.titulo || art.capitulo) && (
            <p className="panel-where">
              {suavizar([art.titulo, art.capitulo, art.seccion].filter(Boolean).join(' · '))}
            </p>
          )}
        </div>
        <button ref={cerrarRef} type="button" className="panel-close" onClick={onClose} aria-label="Cerrar artículo">
          ×
        </button>
      </header>

      <div className="panel-body">
        {estado.tipo === 'cargando' && <p className="panel-status">Cargando artículo…</p>}
        {estado.tipo === 'error' && (
          <p className="panel-status panel-error" role="alert">
            No se pudo cargar el artículo: {estado.mensaje}
          </p>
        )}
        {art && (
          <>
            {art.derogado && <p className="badge-derogado">Artículo derogado</p>}
            <div className="legal-text">
              {toParagraphs(art.texto).map((p, i) => (
                <p key={i}>{p}</p>
              ))}
            </div>
            {art.reformas.length > 0 && (
              <details className="reformas">
                <summary>Historial de reformas ({art.reformas.length})</summary>
                <ul>
                  {art.reformas.map((r, i) => (
                    <li key={i}>{r}</li>
                  ))}
                </ul>
              </details>
            )}
          </>
        )}
      </div>

      {art && (
        <footer className="panel-foot">
          {art.fecha_ultima_reforma && (
            <span>Texto vigente · última reforma de la ley: {fecha(art.fecha_ultima_reforma)}</span>
          )}
          <a href={art.url} target="_blank" rel="noreferrer">
            PDF oficial (Cámara de Diputados) ↗
          </a>
        </footer>
      )}
    </aside>
  )
}
