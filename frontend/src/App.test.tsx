import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

// Texto real de la LFT (art. 61) para el artículo que abre el panel.
const LFT_61 = {
  id: 'LFT-61',
  ley: 'LFT',
  ley_nombre: 'Ley Federal del Trabajo',
  numero: '61',
  tipo: 'articulo',
  derogado: false,
  titulo: 'Título TERCERO. Condiciones de Trabajo',
  capitulo: 'Capítulo II. Jornada de trabajo',
  seccion: null,
  texto:
    'La duración de la jornada diaria será de ocho horas la diurna, siete la nocturna y siete\nhoras y media la mixta.',
  reformas: ['Artículo reformado DOF 01-05-2026'],
  fecha_ultima_reforma: '2026-05-14',
  url: 'https://www.diputados.gob.mx/LeyesBiblio/pdf/LFT.pdf',
}

const TEXTO =
  'La jornada ordinaria no puede pasar de cuarenta horas semanales [LFT, art. 59]. La diurna dura ocho horas [LFT, art. 61].'

const RESPUESTA = {
  respuesta: TEXTO,
  citas: [
    { id: 'LFT-59', ley: 'LFT', numero: '59', etiqueta: '[LFT, art. 59]', url: '/articles/LFT/59' },
    { id: 'LFT-61', ley: 'LFT', numero: '61', etiqueta: '[LFT, art. 61]', url: '/articles/LFT/61' },
  ],
  sin_evidencia: false,
}

type Evento = [string, unknown]

function sse(events: Evento[]): Response {
  const body = events.map(([e, d]) => `event: ${e}\ndata: ${JSON.stringify(d)}\n\n`).join('')
  return new Response(body, { headers: { 'Content-Type': 'text/event-stream' } })
}

const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })

const tokens = (texto: string): Evento[] =>
  (texto.match(/\S+\s*/g) ?? []).map((w) => ['token', { texto: w }])

let streamEvents: Evento[]
let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  localStorage.clear()
  window.history.pushState(null, '', '/consulta')
  streamEvents = [
    ['paso', { nodo: 'razonar', mensaje: 'Buscando en el corpus', herramientas: [{ nombre: 'buscar_articulos', args: { consulta: 'jornada máxima' } }] }],
    ['paso', { nodo: 'herramientas', mensaje: '2 artículos recuperados', articulos: ['LFT-59', 'LFT-61'] }],
    ...tokens(TEXTO),
    ['paso', { nodo: 'verificar', mensaje: 'Citas verificadas' }],
    ['respuesta', RESPUESTA],
  ]
  fetchMock = vi.fn(async (url: string, _init?: RequestInit) => {
    if (url.endsWith('/laws'))
      return json([{ clave: 'LFT', nombre: 'Ley Federal del Trabajo', articulos: 1114, fecha_ultima_reforma: '2026-05-14', url: '' }])
    if (url.endsWith('/ask/stream')) return sse(streamEvents)
    if (url.endsWith('/articles/LFT/61')) return json(LFT_61)
    return json({ detail: `No existe ${url}` }, 404)
  })
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => vi.unstubAllGlobals())

async function preguntar(texto = '¿Cuál es la jornada máxima?') {
  const user = userEvent.setup()
  render(<App />)
  await user.type(screen.getByLabelText('Pregunta'), texto)
  await user.click(screen.getByRole('button', { name: /^Preguntar/ }))
  return user
}

describe('Consulta', () => {
  it('muestra la respuesta cotejada con citas clicables y folio', async () => {
    await preguntar()
    expect(await screen.findByText('Cotejado')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Abrir LFT, art. 61' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Abrir LFT, art. 59' })).toBeInTheDocument()
    expect(screen.getByText('Fundamento')).toBeInTheDocument()
    expect(screen.getAllByText('0001').length).toBeGreaterThan(0)
  })

  it('abre la copia del artículo citado y navega al vecino', async () => {
    const user = await preguntar()
    await user.click(await screen.findByRole('button', { name: 'Abrir LFT, art. 61' }))

    const panel = await screen.findByRole('complementary', { name: 'LFT, Artículo 61' })
    expect(
      await within(panel).findByText(/ocho horas la diurna, siete la nocturna y siete horas y media la mixta/),
    ).toBeInTheDocument()
    expect(within(panel).getByText('Ley Federal del Trabajo')).toBeInTheDocument()
    expect(within(panel).getByRole('link', { name: /PDF oficial/ })).toHaveAttribute('href', LFT_61.url)

    await user.click(within(panel).getByRole('button', { name: /Art\. 62/ }))
    expect(await screen.findByRole('complementary', { name: 'LFT, Artículo 62' })).toBeInTheDocument()

    await user.keyboard('{Escape}')
    expect(screen.queryByRole('complementary')).not.toBeInTheDocument()
  })

  it('manda el filtro de ley seleccionado', async () => {
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: 'LFT' }))
    await user.type(screen.getByLabelText('Pregunta'), '¿Cuál es la jornada máxima?{Enter}')
    await screen.findByText('Cotejado')

    const [, init] = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/ask/stream'))!
    expect(JSON.parse(init.body)).toEqual({ pregunta: '¿Cuál es la jornada máxima?', leyes: ['LFT'] })
  })

  it('muestra el borrador en vivo sin sello hasta que llega la verificación', async () => {
    // El stream entrega el texto y se queda abierto: la verificación aún no llega.
    const enc = new TextEncoder()
    const abierto = new ReadableStream<Uint8Array>({
      start(c) {
        for (const [e, d] of streamEvents.slice(0, -2))
          c.enqueue(enc.encode(`event: ${e}
data: ${JSON.stringify(d)}

`))
      },
    })
    fetchMock.mockImplementation(async (url: string) =>
      url.endsWith('/ask/stream')
        ? new Response(abierto, { headers: { 'Content-Type': 'text/event-stream' } })
        : json([]),
    )
    await preguntar()
    expect(await screen.findByText(/Borrador sin cotejar/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Abrir LFT, art. 59' })).toBeInTheDocument()
    expect(screen.queryByText('Cotejado')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Detener/ })).toBeInTheDocument()
  })

  it('limpia el texto cuando el verificador descarta el borrador', async () => {
    streamEvents = [
      ...tokens('Texto equivocado que se descarta [LFT, art. 59].'),
      ['borrador_descartado', { problemas: ['El art. 59 no dice eso.'] }],
      ...tokens(TEXTO),
      ['respuesta', RESPUESTA],
    ]
    await preguntar()
    await screen.findByText('Cotejado')
    expect(screen.queryByText(/Texto equivocado/)).not.toBeInTheDocument()
  })

  it('pliega la bitácora al terminar y la abre a petición', async () => {
    const user = await preguntar()
    const toggle = await screen.findByRole('button', { name: /Ver bitácora · 3 pasos/ })
    await user.click(toggle)
    expect(screen.getByText('LFT-59 LFT-61', { collapseWhitespace: true })).toBeInTheDocument()
  })

  it('sella la abstención de forma distinta y sin fuentes', async () => {
    streamEvents = [['respuesta', { respuesta: 'El ISR no está en el corpus.', citas: [], sin_evidencia: true }]]
    await preguntar('¿Cuánto ISR me retienen?')
    expect(await screen.findByText('Sin evidencia')).toBeInTheDocument()
    expect(screen.getByText('El ISR no está en el corpus.')).toBeInTheDocument()
    expect(screen.queryByText('Fundamento')).not.toBeInTheDocument()
  })

  it('explica el límite de consultas (429) sin ofrecer reintento', async () => {
    fetchMock.mockImplementation(async (url: string) =>
      url.endsWith('/ask/stream')
        ? json({ detail: 'La demo alcanzó su tope de consultas por hoy.' }, 429)
        : json([]),
    )
    await preguntar()
    const alerta = await screen.findByRole('alert')
    expect(alerta).toHaveTextContent('Ventanilla cerrada')
    expect(alerta).toHaveTextContent('tope de consultas')
    expect(within(alerta).queryByRole('button')).not.toBeInTheDocument()
  })

  it('ofrece volver a preguntar ante un error del servicio', async () => {
    fetchMock.mockImplementation(async (url: string) =>
      url.endsWith('/ask/stream') ? json({ detail: 'Servicio ocupado.' }, 503) : json([]),
    )
    await preguntar()
    const alerta = await screen.findByRole('alert')
    expect(within(alerta).getByRole('button', { name: /Volver a preguntar/ })).toBeInTheDocument()
  })

  it('no envía preguntas vacías', async () => {
    render(<App />)
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1)) // solo /laws
    expect(screen.getByRole('button', { name: /^Preguntar/ })).toBeDisabled()
  })

  it('guarda la consulta en el archivo del navegador y la reabre', async () => {
    const { unmount } = render(<App />)
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Pregunta'), '¿Cuál es la jornada máxima?{Enter}')
    await screen.findByText('Cotejado')
    unmount()

    render(<App />)
    const archivo = screen.getByRole('navigation', { name: 'Archivo de consultas' })
    await user.click(within(archivo).getByRole('button', { name: /^0001/ }))
    expect(await screen.findByRole('button', { name: 'Abrir LFT, art. 61' })).toBeInTheDocument()

    await user.click(within(archivo).getByRole('button', { name: /Borrar consulta/ }))
    expect(within(archivo).getByText(/se guardan aquí/)).toBeInTheDocument()
  })
})

describe('Portada', () => {
  beforeEach(() => window.history.pushState(null, '', '/'))

  it('presenta el producto, el corpus y las métricas reales', async () => {
    render(<App />)
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Ninguna respuesta sin su artículo.')
    expect(screen.getByText('Constancia de evaluación')).toBeInTheDocument()
    expect(screen.getByText('0.78')).toBeInTheDocument()
    expect(screen.getAllByText('Aún no cumple').length).toBeGreaterThan(0)
    expect(await screen.findByText('1,114')).toBeInTheDocument()
  })

  it('lleva la pregunta escrita a la consulta y la envía', async () => {
    const user = userEvent.setup()
    render(<App />)
    await user.type(screen.getByLabelText('Pregunta'), '¿Cuál es la jornada máxima?{Enter}')
    expect(window.location.pathname).toBe('/consulta')
    expect(await screen.findByText('Cotejado')).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2, name: '¿Cuál es la jornada máxima?' })).toBeInTheDocument()
  })
})
