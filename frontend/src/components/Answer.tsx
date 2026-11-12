import type { AskResponse } from '../lib/api'
import { type CitaRef, citaId as idDe, shortLabel, splitCitations } from '../lib/citations'

interface Props {
  respuesta: AskResponse
  activa: string | null // id del artículo abierto en el panel
  onCita: (cita: CitaRef) => void
}

/** Respuesta con cada cita convertida en un botón que abre el artículo. */
export function Answer({ respuesta, activa, onCita }: Props) {
  if (respuesta.sin_evidencia) {
    return (
      <div className="answer answer-abstain" role="note">
        <p className="abstain-title">Sin evidencia suficiente en el corpus</p>
        <p>{respuesta.respuesta}</p>
      </div>
    )
  }

  const segmentos = splitCitations(respuesta.respuesta)
  const fuentes = respuesta.citas.map<CitaRef>((c) => ({
    ley: c.ley,
    numero: c.numero,
    transitorio: c.id.includes('-T-'),
    etiqueta: c.etiqueta,
  }))

  return (
    <div className="answer">
      <p className="answer-text">
        {segmentos.map((s, i) =>
          s.type === 'text' ? (
            <span key={i}>{s.text}</span>
          ) : (
            <button
              key={i}
              type="button"
              className="cite"
              aria-pressed={activa === idDe(s.cita)}
              aria-label={`Abrir ${s.cita.etiqueta.slice(1, -1)}`}
              onClick={() => onCita(s.cita)}
            >
              {shortLabel(s.cita)}
            </button>
          ),
        )}
      </p>
      {fuentes.length > 0 && (
        <div className="sources">
          <span className="sources-label">Fuentes</span>
          {fuentes.map((c) => (
            <button
              key={idDe(c)}
              type="button"
              className="source"
              aria-pressed={activa === idDe(c)}
              onClick={() => onCita(c)}
            >
              <span className="source-law">{c.ley}</span>
              <span className="source-num">{c.transitorio ? `Transitorio ${c.numero}` : `Art. ${c.numero}`}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
