import { type FormEvent, useCallback, useEffect, useRef, useState } from 'react'
import { Answer } from './components/Answer'
import { ArticlePanel } from './components/ArticlePanel'
import { LawFilter } from './components/LawFilter'
import { Steps } from './components/Steps'
import { type AskResponse, type Law, type Paso, askStream, getLaws } from './lib/api'
import { type CitaRef, citaId } from './lib/citations'

interface Turno {
  id: number
  pregunta: string
  leyes: string[]
  pasos: Paso[]
  respuesta?: AskResponse
  error?: string
  estado: 'pensando' | 'listo' | 'error'
}

const EJEMPLOS = [
  '¿Cuántos días de vacaciones me tocan en mi primer año de trabajo?',
  '¿Cuál es la jornada máxima de trabajo a la semana?',
  '¿Qué puedo hacer si un producto que compré sale defectuoso?',
  '¿Cuánto tiempo duran los derechos de autor después de la muerte del autor?',
]

const MAX = 1000

export default function App() {
  const [laws, setLaws] = useState<Law[]>([])
  const [leyes, setLeyes] = useState<string[]>([])
  const [pregunta, setPregunta] = useState('')
  const [turnos, setTurnos] = useState<Turno[]>([])
  const [cita, setCita] = useState<CitaRef | null>(null)
  const finRef = useRef<HTMLDivElement>(null)
  const ctrlRef = useRef<AbortController | null>(null)

  useEffect(() => {
    const ctrl = new AbortController()
    getLaws(ctrl.signal).then(setLaws).catch(() => setLaws([]))
    return () => ctrl.abort()
  }, [])

  useEffect(() => {
    finRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'end' })
  }, [turnos])

  const ocupado = turnos.at(-1)?.estado === 'pensando'

  const actualizar = (id: number, cambio: (t: Turno) => Turno) =>
    setTurnos((ts) => ts.map((t) => (t.id === id ? cambio(t) : t)))

  async function preguntar(texto: string) {
    const q = texto.trim()
    if (q.length < 3 || ocupado) return
    const id = Date.now()
    setTurnos((ts) => [...ts, { id, pregunta: q, leyes, pasos: [], estado: 'pensando' }])
    setPregunta('')
    ctrlRef.current = new AbortController()
    try {
      await askStream(
        q,
        leyes,
        {
          onPaso: (paso) => actualizar(id, (t) => ({ ...t, pasos: [...t.pasos, paso] })),
          onRespuesta: (respuesta) => actualizar(id, (t) => ({ ...t, respuesta, estado: 'listo' })),
        },
        ctrlRef.current.signal,
      )
    } catch (e) {
      const err = e as Error
      if (err.name === 'AbortError') return
      actualizar(id, (t) => ({ ...t, estado: 'error', error: err.message }))
    }
  }

  const enviar = (e: FormEvent) => {
    e.preventDefault()
    void preguntar(pregunta)
  }

  const cerrar = useCallback(() => setCita(null), [])
  const activa = cita ? citaId(cita) : null

  return (
    <div className={`layout${cita ? ' with-panel' : ''}`}>
      <main className="chat">
        <header className="topbar">
          <div className="brand">
            <span className="brand-mark" aria-hidden>§</span>
            <div>
              <h1>ArticulIA</h1>
              <p>Leyes federales mexicanas, con el artículo exacto.</p>
            </div>
          </div>
          <LawFilter laws={laws} selected={leyes} onChange={setLeyes} disabled={ocupado} />
        </header>

        <section className="conversation" aria-label="Conversación">
          {turnos.length === 0 && (
            <div className="empty">
              <p className="empty-lead">
                Pregunta en tus palabras. Cada respuesta cita el artículo en que se basa; si el
                corpus no lo cubre, te lo digo.
              </p>
              <ul className="examples">
                {EJEMPLOS.map((ej) => (
                  <li key={ej}>
                    <button type="button" onClick={() => void preguntar(ej)}>
                      {ej}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {turnos.map((t) => (
            <article key={t.id} className="turn">
              <p className="question">
                {t.pregunta}
                {t.leyes.length > 0 && <span className="question-laws">{t.leyes.join(' · ')}</span>}
              </p>
              <Steps pasos={t.pasos} activo={t.estado === 'pensando'} />
              {t.respuesta && <Answer respuesta={t.respuesta} activa={activa} onCita={setCita} />}
              {t.estado === 'error' && (
                <p className="answer answer-error" role="alert">
                  {t.error}
                </p>
              )}
            </article>
          ))}
          <div ref={finRef} />
        </section>

        <form className="composer" onSubmit={enviar}>
          <label htmlFor="pregunta" className="sr-only">
            Tu pregunta
          </label>
          <textarea
            id="pregunta"
            value={pregunta}
            maxLength={MAX}
            rows={1}
            placeholder="Escribe tu pregunta sobre leyes federales…"
            onChange={(e) => setPregunta(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                void preguntar(pregunta)
              }
            }}
          />
          <button type="submit" disabled={ocupado || pregunta.trim().length < 3}>
            {ocupado ? 'Buscando…' : 'Preguntar'}
          </button>
          <p className="disclaimer">
            Información de leyes federales vigentes. No sustituye asesoría legal.
          </p>
        </form>
      </main>

      {cita && <ArticlePanel key={activa} cita={cita} onClose={cerrar} />}
    </div>
  )
}
