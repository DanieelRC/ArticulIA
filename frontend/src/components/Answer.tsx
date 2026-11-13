import { useState } from 'react'
import type { Turno } from '../lib/archivo'
import { type CitaRef, citaId, shortLabel, splitCitations } from '../lib/citations'
import { Icono, Sello } from './ui'

interface Props {
  turno: Turno
  activa: string | null // id del artículo abierto en el panel
  onCita: (cita: CitaRef) => void
  onReintentar: () => void
}

const hoy = (ms: number) =>
  new Date(ms).toLocaleDateString('es-MX', { day: '2-digit', month: 'short', year: 'numeric' })

/** Mensaje y sello según el tipo de fallo; los límites no son «errores» del usuario. */
function fallo(turno: Turno): { sello: string; texto: string; reintentar: boolean } {
  if (turno.status === 429)
    return {
      sello: 'Ventanilla cerrada',
      texto: turno.error ?? 'Se alcanzó el límite de consultas. Intenta más tarde.',
      reintentar: false,
    }
  if (turno.status === 503)
    return {
      sello: 'Sin servicio',
      texto: turno.error ?? 'El servicio está ocupado. Intenta de nuevo en un momento.',
      reintentar: true,
    }
  return {
    sello: 'No se pudo tramitar',
    texto: turno.error ?? 'Ocurrió un error al generar la respuesta.',
    reintentar: true,
  }
}

/** Hoja de respuesta: texto en vivo, citas como pestañas y sello al cotejar. */
export function Answer({ turno, activa, onCita, onReintentar }: Props) {
  const [copiado, setCopiado] = useState(false)
  const { respuesta, estado } = turno

  if (estado === 'error') {
    const f = fallo(turno)
    return (
      <div className="hoja hoja-fallo" role="alert">
        <Sello titulo={f.sello} tinta="negro" />
        <p>{f.texto}</p>
        {f.reintentar && (
          <button type="button" className="btn btn-linea" onClick={onReintentar}>
            <Icono n="reintentar" /> Volver a preguntar
          </button>
        )}
      </div>
    )
  }

  if (estado === 'detenido' && !respuesta) {
    return (
      <div className="hoja hoja-fallo">
        <Sello titulo="Trámite detenido" tinta="negro" />
        <p>Detuviste esta consulta antes de que terminara.</p>
        <button type="button" className="btn btn-linea" onClick={onReintentar}>
          <Icono n="reintentar" /> Volver a preguntar
        </button>
      </div>
    )
  }

  if (respuesta?.sin_evidencia) {
    return (
      <div className="hoja hoja-abstencion" role="note">
        <Sello titulo="Sin evidencia" linea="en el corpus" tinta="azul" golpe />
        <p className="hoja-texto">{respuesta.respuesta}</p>
        <p className="hoja-nota">
          ArticulIA prefiere no responder antes que citar un artículo que no respalda la afirmación.
        </p>
      </div>
    )
  }

  const texto = respuesta?.respuesta ?? turno.texto
  if (!texto) return null
  const verificada = Boolean(respuesta)
  const segmentos = splitCitations(texto)
  const fuentes = (respuesta?.citas ?? []).map<CitaRef>((c) => ({
    ley: c.ley,
    numero: c.numero,
    transitorio: c.id.includes('-T-'),
    etiqueta: c.etiqueta,
  }))

  const copiar = async () => {
    try {
      await navigator.clipboard.writeText(texto)
      setCopiado(true)
      setTimeout(() => setCopiado(false), 1800)
    } catch {
      /* sin permiso de portapapeles */
    }
  }

  return (
    <div className={`hoja hoja-respuesta${verificada ? ' hoja-cotejada' : ' hoja-borrador'}`}>
      {verificada ? (
        <Sello
          titulo="Cotejado"
          linea={`${fuentes.length} ${fuentes.length === 1 ? 'cita' : 'citas'} · ${hoy(turno.inicio)}`}
          golpe
          className="sello-esquina"
        />
      ) : (
        <p className="hoja-estado" role="status">
          Borrador sin cotejar · las citas se verifican al terminar
        </p>
      )}

      <p className="hoja-texto" aria-live={verificada ? undefined : 'off'}>
        {segmentos.map((s, i) =>
          s.type === 'text' ? (
            <span key={i}>{s.text}</span>
          ) : (
            <button
              key={i}
              type="button"
              className="cita"
              aria-pressed={activa === citaId(s.cita)}
              aria-label={`Abrir ${s.cita.etiqueta.slice(1, -1)}`}
              onClick={() => onCita(s.cita)}
            >
              {shortLabel(s.cita)}
            </button>
          ),
        )}
        {!verificada && <span className="cursor" aria-hidden="true" />}
      </p>

      {verificada && (
        <div className="hoja-pie">
          <div className="fuentes">
            <span className="rotulo">Fundamento</span>
            {fuentes.map((c) => (
              <button
                key={citaId(c)}
                type="button"
                className="fuente"
                aria-pressed={activa === citaId(c)}
                onClick={() => onCita(c)}
              >
                <b>{c.ley}</b> {c.transitorio ? `transitorio ${c.numero}` : `art. ${c.numero}`}
              </button>
            ))}
          </div>
          <button type="button" className="btn btn-fantasma" onClick={copiar}>
            <Icono n={copiado ? 'listo' : 'copiar'} /> {copiado ? 'Copiada' : 'Copiar respuesta'}
          </button>
        </div>
      )}
    </div>
  )
}
