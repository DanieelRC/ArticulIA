import { useEffect, useRef, useState } from 'react'
import { type Article, getArticle } from '../lib/api'
import { type CitaRef, suavizar, toParagraphs } from '../lib/citations'
import { Icono, Sello } from './ui'

interface Props {
  cita: CitaRef
  onClose: () => void
  /** Navegar al artículo vecino dentro de la misma ley. */
  onIr: (cita: CitaRef) => void
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

/** Copia del artículo citado: texto completo, ubicación, reformas y fuente oficial. */
export function ArticlePanel({ cita, onClose, onIr }: Props) {
  const [estado, setEstado] = useState<Estado>({ tipo: 'cargando' })
  const [copiado, setCopiado] = useState(false)
  const cerrarRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    // El padre monta un panel nuevo por cita (key), así que el estado inicial ya es «cargando».
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
  const rotulo = cita.transitorio ? 'Transitorio' : 'Artículo'
  const n = /^\d+$/.test(cita.numero) && !cita.transitorio ? Number(cita.numero) : null
  const vecino = (d: number): CitaRef => ({
    ley: cita.ley,
    numero: String((n ?? 0) + d),
    transitorio: false,
    etiqueta: `[${cita.ley}, art. ${(n ?? 0) + d}]`,
  })

  const copiar = async () => {
    try {
      await navigator.clipboard.writeText(cita.etiqueta)
      setCopiado(true)
      setTimeout(() => setCopiado(false), 1800)
    } catch {
      /* sin permiso de portapapeles */
    }
  }

  return (
    <aside className="copia" aria-label={`${cita.ley}, ${rotulo} ${cita.numero}`}>
      <header className="copia-cabeza">
        <div className="copia-id">
          <p className="copia-ley">{art?.ley_nombre ?? cita.ley}</p>
          <h2 className="copia-num">
            <span>{rotulo}</span> {cita.numero}
          </h2>
          {art && (art.titulo || art.capitulo) && (
            <p className="copia-donde">
              {suavizar([art.titulo, art.capitulo, art.seccion].filter(Boolean).join(' · '))}
            </p>
          )}
        </div>
        <button
          ref={cerrarRef}
          type="button"
          className="btn-icono"
          onClick={onClose}
          aria-label="Cerrar artículo"
        >
          <Icono n="cerrar" size={20} />
        </button>
      </header>

      <div className="copia-cuerpo">
        {estado.tipo === 'cargando' && <p className="copia-estado">Trayendo el artículo…</p>}
        {estado.tipo === 'error' && (
          <p className="copia-estado copia-error" role="alert">
            No se pudo traer el artículo: {estado.mensaje}
          </p>
        )}
        {art && (
          <>
            {art.derogado && <Sello titulo="Derogado" tinta="negro" />}
            <div className="texto-legal">
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

      <footer className="copia-pie">
        {n !== null && (
          <div className="copia-nav">
            <button type="button" className="btn btn-fantasma" disabled={n <= 1} onClick={() => onIr(vecino(-1))}>
              <Icono n="anterior" /> Art. {n - 1}
            </button>
            <button type="button" className="btn btn-fantasma" onClick={() => onIr(vecino(1))}>
              Art. {n + 1} <Icono n="siguiente" />
            </button>
          </div>
        )}
        <div className="copia-acciones">
          <button type="button" className="btn btn-fantasma" onClick={copiar}>
            <Icono n={copiado ? 'listo' : 'copiar'} /> {copiado ? 'Cita copiada' : 'Copiar cita'}
          </button>
          {art && (
            <a className="btn btn-fantasma" href={art.url} target="_blank" rel="noreferrer">
              PDF oficial <Icono n="externo" />
            </a>
          )}
        </div>
        {art?.fecha_ultima_reforma && (
          <p className="copia-vigencia">
            Texto vigente. Última reforma de la ley: {fecha(art.fecha_ultima_reforma)}.
          </p>
        )}
      </footer>
    </aside>
  )
}
