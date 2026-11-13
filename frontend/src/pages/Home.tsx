import { type FormEvent, useEffect, useState } from 'react'
import { Icono, Marca, Sello } from '../components/ui'
import { AUTOR, EVALUACION, GITHUB_URL } from '../data/metricas'
import { type Law, getLaws } from '../lib/api'
import { EJEMPLOS, MAX_PREGUNTA } from '../lib/constantes'

interface Props {
  /** Abre la consulta; con texto, la envía al entrar. */
  onPreguntar: (pregunta?: string) => void
}

/** Lo que se sabe del corpus aunque la API no responda (texto vigente indexado). */
const CORPUS_BASE: Law[] = [
  { clave: 'CPEUM', nombre: 'Constitución Política de los Estados Unidos Mexicanos', articulos: 136, fecha_ultima_reforma: '2026-10-07', url: '' },
  { clave: 'LFT', nombre: 'Ley Federal del Trabajo', articulos: 1114, fecha_ultima_reforma: '2026-05-14', url: '' },
  { clave: 'CCF', nombre: 'Código Civil Federal', articulos: 2920, fecha_ultima_reforma: '2025-11-14', url: '' },
  { clave: 'LFPDPPP', nombre: 'Ley Federal de Protección de Datos Personales en Posesión de los Particulares', articulos: 64, fecha_ultima_reforma: '2025-11-14', url: '' },
  { clave: 'LFDA', nombre: 'Ley Federal del Derecho de Autor', articulos: 259, fecha_ultima_reforma: '2026-05-14', url: '' },
  { clave: 'LFPC', nombre: 'Ley Federal de Protección al Consumidor', articulos: 181, fecha_ultima_reforma: '2025-12-12', url: '' },
]

const fecha = (iso: string | null) =>
  iso
    ? new Date(`${iso}T12:00:00`).toLocaleDateString('es-MX', { day: '2-digit', month: 'short', year: 'numeric' })
    : 'sin dato'

const valorTxt = (v: number | null) => (v === null ? 'pendiente' : v.toFixed(2))

export default function Home({ onPreguntar }: Props) {
  const [pregunta, setPregunta] = useState('')
  const [laws, setLaws] = useState<Law[]>(CORPUS_BASE)

  useEffect(() => {
    const ctrl = new AbortController()
    getLaws(ctrl.signal)
      .then((l) => l.length && setLaws(l))
      .catch(() => undefined)
    return () => ctrl.abort()
  }, [])

  const enviar = (e: FormEvent) => {
    e.preventDefault()
    onPreguntar(pregunta.trim().length >= 3 ? pregunta : undefined)
  }

  const total = laws.reduce((n, l) => n + l.articulos, 0)

  return (
    <div className="portada">
      <section className="tinta">
        <header className="portada-nav">
          <Marca />
          <nav aria-label="Secciones">
            <a href="#tramite">Cómo funciona</a>
            <a href="#corpus">Corpus</a>
            <a href="#evaluacion">Evaluación</a>
            {GITHUB_URL && (
              <a href={GITHUB_URL} target="_blank" rel="noreferrer">
                GitHub
              </a>
            )}
          </nav>
          <button type="button" className="btn btn-copia" onClick={() => onPreguntar()}>
            Abrir consulta
          </button>
        </header>

        <div className="heroe">
          <div className="heroe-texto">
            <h1>
              Ninguna respuesta <span>sin su artículo.</span>
            </h1>
            <p className="heroe-bajada">
              ArticulIA responde dudas sobre leyes federales mexicanas, cita el artículo exacto de
              cada afirmación y coteja las citas antes de entregar. Si no hay fundamento, se
              abstiene.
            </p>
            <form className="heroe-forma" onSubmit={enviar}>
              <label htmlFor="pregunta-portada">Pregunta</label>
              <div className="heroe-fila">
                <input
                  id="pregunta-portada"
                  type="text"
                  value={pregunta}
                  maxLength={MAX_PREGUNTA}
                  placeholder="¿Cuántos días de vacaciones me tocan?"
                  onChange={(e) => setPregunta(e.target.value)}
                  autoComplete="off"
                />
                <button type="submit" className="btn btn-copia">
                  Preguntar <Icono n="flecha" />
                </button>
              </div>
            </form>
          </div>

          <figure className="muestra" aria-label="Ejemplo de respuesta del agente">
            <div className="muestra-hoja">
              <header>
                <span className="folio">
                  Folio <b>0001</b>
                </span>
                <span>Ejemplo de respuesta</span>
              </header>
              <p className="muestra-pregunta">¿Cuántos días de vacaciones me tocan al cumplir un año?</p>
              <p className="muestra-texto">
                Las personas trabajadoras con más de un año de servicios disfrutan de un periodo
                anual de vacaciones pagadas que no puede ser inferior a doce días laborables{' '}
                <span className="cita cita-fija">LFT 76</span>. De ese periodo, doce días deben ser
                continuos por lo menos <span className="cita cita-fija">LFT 78</span>.
              </p>
              <Sello titulo="Cotejado" linea="2 citas · LFT" golpe className="sello-esquina" />
            </div>
          </figure>
        </div>
      </section>

      <section className="banda" id="tramite">
        <h2>El trámite de cada pregunta</h2>
        <ol className="ruta">
          <li>
            <Sello titulo="Busca" tinta="violeta" />
            <h3>En {total.toLocaleString('es-MX')} artículos</h3>
            <p>
              Búsqueda híbrida en PostgreSQL: significado con embeddings y palabras exactas con texto
              completo, fusionadas y reordenadas por un reranker.
            </p>
          </li>
          <li>
            <Sello titulo="Redacta" tinta="negro" />
            <h3>Con la cita en cada afirmación</h3>
            <p>
              El agente escribe solo con los artículos que recuperó y marca cada frase con su
              fundamento, por ejemplo <span className="cita cita-fija">LFT 61</span>.
            </p>
          </li>
          <li>
            <Sello titulo="Coteja" tinta="rojo" />
            <h3>O no entrega</h3>
            <p>
              Un verificador comprueba que cada cita exista entre lo recuperado y respalde lo
              dicho. Si falla, reintenta una vez; si vuelve a fallar, se abstiene.
            </p>
          </li>
        </ol>

        <div className="abstencion-demo">
          <div>
            <h3>También sabe decir que no</h3>
            <p>
              Una pregunta sobre el ISR, un reglamento de tránsito o una ley estatal queda fuera
              de las seis leyes. En vez de improvisar, ArticulIA lo dice.
            </p>
          </div>
          <div className="hoja hoja-abstencion">
            <Sello titulo="Sin evidencia" linea="en el corpus" tinta="azul" />
            <p className="muestra-pregunta">¿Cuánto ISR me retienen si gano 20 mil pesos al mes?</p>
            <p className="hoja-nota">Las tarifas del ISR están en una ley que no forma parte del corpus.</p>
          </div>
        </div>
      </section>

      <section className="banda banda-papel" id="corpus">
        <h2>Seis leyes, texto vigente</h2>
        <p className="banda-bajada">
          Tomadas de la Cámara de Diputados y divididas por artículo, que es la unidad que se cita.
        </p>
        <table className="libro">
          <thead>
            <tr>
              <th scope="col">Clave</th>
              <th scope="col">Ley</th>
              <th scope="col" className="num">Artículos vigentes</th>
              <th scope="col" className="num">Última reforma</th>
            </tr>
          </thead>
          <tbody>
            {laws.map((l) => (
              <tr key={l.clave}>
                <th scope="row">{l.clave}</th>
                <td>{l.nombre}</td>
                <td className="num">{l.articulos.toLocaleString('es-MX')}</td>
                <td className="num">{fecha(l.fecha_ultima_reforma)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="banda" id="evaluacion">
        <h2>Constancia de evaluación</h2>
        <p className="banda-bajada">
          {EVALUACION.preguntas} preguntas, {EVALUACION.fecha}. {EVALUACION.nota} Los números se
          publican como salieron.
        </p>
        <table className="libro constancia">
          <thead>
            <tr>
              <th scope="col">Métrica</th>
              <th scope="col">Qué mide</th>
              <th scope="col" className="num">Resultado</th>
              <th scope="col" className="num">Meta</th>
              <th scope="col">Dictamen</th>
            </tr>
          </thead>
          <tbody>
            {EVALUACION.metricas.map((m) => {
              const cumple = m.valor !== null && m.meta !== null ? m.valor >= m.meta : null
              return (
                <tr key={m.nombre}>
                  <th scope="row">{m.nombre}</th>
                  <td>{m.que}</td>
                  <td className="num grande">{valorTxt(m.valor)}</td>
                  <td className="num">{m.meta === null ? 'sin meta' : `≥ ${m.meta.toFixed(2)}`}</td>
                  <td>
                    {m.valor === null ? (
                      <span className="dictamen">Por medir</span>
                    ) : cumple === null ? (
                      <span className="dictamen">Se reporta</span>
                    ) : cumple ? (
                      <span className="dictamen dictamen-ok">Cumple</span>
                    ) : (
                      <span className="dictamen dictamen-no">Aún no cumple</span>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
        <p className="pila">
          Hecho con LangGraph, FastAPI con streaming, PostgreSQL y pgvector, embeddings bge-m3 en
          local, Ragas para la evaluación y Docker Compose.
        </p>
      </section>

      <section className="tinta cierre">
        <h2>Haz la prueba con una duda real.</h2>
        <ul className="ejemplos ejemplos-tinta">
          {EJEMPLOS.map((ej) => (
            <li key={ej}>
              <button type="button" onClick={() => onPreguntar(ej)}>
                <span>{ej}</span>
                <Icono n="flecha" />
              </button>
            </li>
          ))}
        </ul>
        <footer className="pie">
          <p>
            Proyecto de {AUTOR}.
            {GITHUB_URL && (
              <>
                {' '}
                <a href={GITHUB_URL} target="_blank" rel="noreferrer">
                  Código en GitHub
                </a>
                .
              </>
            )}
          </p>
          <p>Información de leyes federales vigentes. No sustituye asesoría legal.</p>
        </footer>
      </section>
    </div>
  )
}
