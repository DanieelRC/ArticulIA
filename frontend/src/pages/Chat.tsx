import { type FormEvent, useCallback, useEffect, useRef, useState } from 'react'
import { Answer } from '../components/Answer'
import { ArticlePanel } from '../components/ArticlePanel'
import { LawFilter } from '../components/LawFilter'
import { Steps } from '../components/Steps'
import { Icono, Marca } from '../components/ui'
import { ApiError, type Law, askStream, getLaws } from '../lib/api'
import {
  type Archivo,
  type Expediente,
  type Turno,
  cargarArchivo,
  folioTxt,
  guardarArchivo,
  nuevoId,
} from '../lib/archivo'
import { type CitaRef, citaId } from '../lib/citations'
import { EJEMPLOS, MAX_PREGUNTA } from '../lib/constantes'

interface Props {
  go: (to: string) => void
  /** Pregunta que viene de la portada; se envía al entrar. */
  inicial: string | null
  onInicialUsada: () => void
}

const fechaCorta = (ms: number) =>
  new Date(ms).toLocaleDateString('es-MX', { day: 'numeric', month: 'short' })

export default function Chat({ go, inicial, onInicialUsada }: Props) {
  const [archivo, setArchivo] = useState<Archivo>(cargarArchivo)
  const [actualId, setActualId] = useState<string | null>(null)
  const [laws, setLaws] = useState<Law[]>([])
  const [leyes, setLeyes] = useState<string[]>([])
  const [pregunta, setPregunta] = useState('')
  const [cita, setCita] = useState<CitaRef | null>(null)
  const [archivoAbierto, setArchivoAbierto] = useState(false)
  const ctrlRef = useRef<AbortController | null>(null)
  const folioRef = useRef(archivo.folio)
  const finRef = useRef<HTMLDivElement>(null)
  const cajaRef = useRef<HTMLTextAreaElement>(null)

  const actual = archivo.expedientes.find((e) => e.id === actualId) ?? null
  const turnos = actual?.turnos ?? []
  const ultimoTexto = turnos.at(-1)?.texto
  const ultimoEstado = turnos.at(-1)?.estado
  const ocupado = ultimoEstado === 'pensando'

  useEffect(() => {
    const ctrl = new AbortController()
    getLaws(ctrl.signal)
      .then(setLaws)
      .catch(() => setLaws([]))
    return () => ctrl.abort()
  }, [])

  useEffect(() => guardarArchivo(archivo), [archivo])

  useEffect(() => {
    finRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'end' })
  }, [turnos.length, ultimoTexto, ultimoEstado])

  const editarTurno = useCallback((expId: string, folio: number, f: (t: Turno) => Turno) => {
    setArchivo((a) => ({
      ...a,
      expedientes: a.expedientes.map((e) =>
        e.id === expId ? { ...e, turnos: e.turnos.map((t) => (t.folio === folio ? f(t) : t)) } : e,
      ),
    }))
  }, [])

  const preguntar = useCallback(
    async (texto: string, leyesSel: string[] = leyes) => {
      const q = texto.trim()
      if (q.length < 3 || ocupado) return
      const inicio = Date.now()
      const expId = actualId ?? nuevoId()
      // El folio se toma de una referencia para conocerlo antes de que React actualice el estado.
      const folio = folioRef.current + 1
      folioRef.current = folio
      setArchivo((a) => {
        const turno: Turno = {
          folio,
          pregunta: q,
          leyes: leyesSel,
          pasos: [],
          texto: '',
          estado: 'pensando',
          descartes: 0,
          inicio,
        }
        const existe = a.expedientes.some((e) => e.id === expId)
        const nuevo: Expediente = { id: expId, titulo: q, creado: inicio, turnos: [turno] }
        return {
          folio,
          expedientes: existe
            ? a.expedientes.map((e) => (e.id === expId ? { ...e, turnos: [...e.turnos, turno] } : e))
            : [nuevo, ...a.expedientes],
        }
      })
      setActualId(expId)
      setPregunta('')
      const ctrl = new AbortController()
      ctrlRef.current = ctrl
      const editar = (f: (t: Turno) => Turno) => editarTurno(expId, folio, f)
      try {
        await askStream(
          q,
          leyesSel,
          {
            onPaso: (p) =>
              editar((t) => ({ ...t, pasos: [...t.pasos, { ...p, t: Date.now() - inicio }] })),
            onToken: (s) => editar((t) => ({ ...t, texto: t.texto + s })),
            onDescartado: () => editar((t) => ({ ...t, texto: '', descartes: t.descartes + 1 })),
            onRespuesta: (respuesta) =>
              editar((t) => ({ ...t, respuesta, estado: 'listo', ms: Date.now() - inicio })),
          },
          ctrl.signal,
        )
      } catch (e) {
        const err = e as Error
        if (err.name === 'AbortError') {
          editar((t) => ({ ...t, estado: 'detenido', ms: Date.now() - inicio }))
          return
        }
        editar((t) => ({
          ...t,
          estado: 'error',
          error: err.message,
          status: err instanceof ApiError ? err.status : undefined,
          ms: Date.now() - inicio,
        }))
      }
    },
    [actualId, editarTurno, leyes, ocupado],
  )

  // Pregunta que llega desde la portada.
  const enviadaRef = useRef(false)
  useEffect(() => {
    if (inicial && !enviadaRef.current) {
      enviadaRef.current = true
      onInicialUsada()
      void preguntar(inicial)
    }
  }, [inicial, onInicialUsada, preguntar])

  const enviar = (e: FormEvent) => {
    e.preventDefault()
    void preguntar(pregunta)
  }

  const nuevoExpediente = () => {
    ctrlRef.current?.abort()
    setActualId(null)
    setCita(null)
    setArchivoAbierto(false)
    cajaRef.current?.focus()
  }

  const abrir = (id: string) => {
    ctrlRef.current?.abort()
    setActualId(id)
    setCita(null)
    setArchivoAbierto(false)
  }

  const borrar = (id: string) => {
    setArchivo((a) => ({ ...a, expedientes: a.expedientes.filter((e) => e.id !== id) }))
    if (id === actualId) setActualId(null)
  }

  const cerrarCita = useCallback(() => setCita(null), [])
  const activa = cita ? citaId(cita) : null
  const restantes = MAX_PREGUNTA - pregunta.length

  return (
    <div className={`mesa${cita ? ' con-copia' : ''}${archivoAbierto ? ' archivo-abierto' : ''}`}>
      <nav className="archivo" aria-label="Archivo de consultas">
        <div className="archivo-cabeza">
          <Marca onClick={() => go('/')} />
          <button
            type="button"
            className="btn-icono solo-movil"
            onClick={() => setArchivoAbierto(false)}
            aria-label="Cerrar archivo"
          >
            <Icono n="cerrar" size={20} />
          </button>
        </div>
        <button type="button" className="btn btn-tinta archivo-nuevo" onClick={nuevoExpediente}>
          <Icono n="mas" /> Nueva consulta
        </button>
        <p className="rotulo archivo-rotulo">Archivo</p>
        {archivo.expedientes.length === 0 ? (
          <p className="archivo-vacio">
            Tus consultas se guardan aquí, solo en este navegador.
          </p>
        ) : (
          <ul className="archivo-lista">
            {archivo.expedientes.map((e) => (
              <li key={e.id} className={e.id === actualId ? 'es-actual' : undefined}>
                <button
                  type="button"
                  className="archivo-item"
                  onClick={() => abrir(e.id)}
                  aria-current={e.id === actualId ? 'true' : undefined}
                >
                  <span className="archivo-folio">{folioTxt(e.turnos[0]?.folio ?? 0)}</span>
                  <span className="archivo-titulo">{e.titulo}</span>
                  <span className="archivo-fecha">
                    {fechaCorta(e.creado)}
                    {e.turnos.length > 1 ? ` · ${e.turnos.length} folios` : ''}
                  </span>
                </button>
                <button
                  type="button"
                  className="btn-icono archivo-borrar"
                  onClick={() => borrar(e.id)}
                  aria-label={`Borrar consulta: ${e.titulo}`}
                >
                  <Icono n="borrar" size={16} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </nav>
      {archivoAbierto && (
        <button
          type="button"
          className="velo"
          aria-label="Cerrar archivo"
          onClick={() => setArchivoAbierto(false)}
        />
      )}

      <main className="escritorio">
        <header className="barra">
          <button
            type="button"
            className="btn-icono solo-movil"
            onClick={() => setArchivoAbierto(true)}
            aria-label="Abrir archivo de consultas"
          >
            <Icono n="archivo" size={20} />
          </button>
          <span className="barra-marca solo-movil">
            <Marca onClick={() => go('/')} />
          </span>
          <LawFilter laws={laws} selected={leyes} onChange={setLeyes} disabled={ocupado} />
        </header>

        <section className="tramite" aria-label="Consulta">
          {turnos.length === 0 && (
            <div className="vacio">
              <h1>¿Qué necesitas saber?</h1>
              <p>
                Pregunta con tus palabras. Cada afirmación llevará el artículo que la respalda y,
                si las seis leyes del corpus no lo cubren, te lo diré.
              </p>
              <ul className="ejemplos">
                {EJEMPLOS.map((ej) => (
                  <li key={ej}>
                    <button type="button" onClick={() => void preguntar(ej)}>
                      <span>{ej}</span>
                      <Icono n="flecha" />
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {turnos.map((t) => (
            <article key={t.folio} className="turno">
              <header className="turno-cabeza">
                <span className="folio">
                  Folio <b>{folioTxt(t.folio)}</b>
                </span>
                {t.leyes.length > 0 && <span className="turno-leyes">{t.leyes.join(' · ')}</span>}
              </header>
              <h2 className="pregunta">{t.pregunta}</h2>
              <Steps pasos={t.pasos} activo={t.estado === 'pensando'} ms={t.ms} />
              {t.estado === 'pensando' && t.descartes > 0 && !t.texto && (
                <p className="aviso-descartado" role="status">
                  El verificador rechazó el borrador. Buscando mejor fundamento…
                </p>
              )}
              <Answer
                turno={t}
                activa={activa}
                onCita={setCita}
                onReintentar={() => void preguntar(t.pregunta, t.leyes)}
              />
            </article>
          ))}
          <div ref={finRef} />
        </section>

        <form className="ventanilla" onSubmit={enviar}>
          <label htmlFor="pregunta" className="rotulo">
            Pregunta
          </label>
          <div className="ventanilla-fila">
            <textarea
              id="pregunta"
              ref={cajaRef}
              value={pregunta}
              maxLength={MAX_PREGUNTA}
              rows={1}
              placeholder="Escribe tu duda sobre leyes federales"
              onChange={(e) => setPregunta(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  void preguntar(pregunta)
                }
              }}
            />
            {ocupado ? (
              <button type="button" className="btn btn-linea" onClick={() => ctrlRef.current?.abort()}>
                <Icono n="detener" /> Detener
              </button>
            ) : (
              <button type="submit" className="btn btn-tinta" disabled={pregunta.trim().length < 3}>
                Preguntar <Icono n="flecha" />
              </button>
            )}
          </div>
          <p className="ventanilla-nota">
            <span>Leyes federales vigentes. No sustituye asesoría legal.</span>
            {restantes <= 80 && <span aria-live="polite">{restantes} caracteres</span>}
          </p>
        </form>
      </main>

      {cita && <ArticlePanel key={activa} cita={cita} onClose={cerrarCita} onIr={setCita} />}
    </div>
  )
}
