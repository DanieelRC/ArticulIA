import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

// Texto real de la LFT (arts. 59 y 61) para el artículo que abre el panel.
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

const RESPUESTA = {
  respuesta:
    'La jornada ordinaria no puede pasar de cuarenta horas semanales [LFT, art. 59]. La diurna dura ocho horas [LFT, art. 61].',
  citas: [
    { id: 'LFT-59', ley: 'LFT', numero: '59', etiqueta: '[LFT, art. 59]', url: '/articles/LFT/59' },
    { id: 'LFT-61', ley: 'LFT', numero: '61', etiqueta: '[LFT, art. 61]', url: '/articles/LFT/61' },
  ],
  sin_evidencia: false,
}

function sse(events: [string, unknown][]): Response {
  const body = events.map(([e, d]) => `event: ${e}\ndata: ${JSON.stringify(d)}\n\n`).join('')
  return new Response(body, { headers: { 'Content-Type': 'text/event-stream' } })
}

const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })

let streamEvents: [string, unknown][]
let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  streamEvents = [
    ['paso', { nodo: 'razonar', mensaje: 'Buscando en el corpus', herramientas: [{ nombre: 'buscar_articulos', args: { consulta: 'jornada máxima' } }] }],
    ['paso', { nodo: 'herramientas', mensaje: '2 artículos recuperados', articulos: ['LFT-59', 'LFT-61'] }],
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
  await user.type(screen.getByLabelText('Tu pregunta'), texto)
  await user.click(screen.getByRole('button', { name: 'Preguntar' }))
  return user
}

describe('App', () => {
  it('muestra la respuesta con citas clicables', async () => {
    await preguntar()
    expect(await screen.findByRole('button', { name: 'Abrir LFT, art. 61' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Abrir LFT, art. 59' })).toBeInTheDocument()
    expect(screen.getByText('Fuentes')).toBeInTheDocument()
  })

  it('abre el panel con el texto completo del artículo citado', async () => {
    const user = await preguntar()
    await user.click(await screen.findByRole('button', { name: 'Abrir LFT, art. 61' }))

    const panel = await screen.findByRole('complementary', { name: 'LFT, Artículo 61' })
    expect(await within(panel).findByText(/ocho horas la diurna, siete la nocturna y siete horas y media la mixta/)).toBeInTheDocument()
    expect(within(panel).getByText('Ley Federal del Trabajo')).toBeInTheDocument()
    expect(within(panel).getByRole('link', { name: /PDF oficial/ })).toHaveAttribute('href', LFT_61.url)

    await user.keyboard('{Escape}')
    expect(screen.queryByRole('complementary')).not.toBeInTheDocument()
  })

  it('manda el filtro de ley seleccionado', async () => {
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: 'LFT' }))
    await user.type(screen.getByLabelText('Tu pregunta'), '¿Cuál es la jornada máxima?{Enter}')
    await screen.findByText('Fuentes')

    const [, init] = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/ask/stream'))!
    expect(JSON.parse(init.body)).toEqual({ pregunta: '¿Cuál es la jornada máxima?', leyes: ['LFT'] })
  })

  it('pliega los pasos del agente al terminar', async () => {
    const user = await preguntar()
    const toggle = await screen.findByRole('button', { name: /Ver cómo se encontró \(3 pasos\)/ })
    await user.click(toggle)
    expect(screen.getByText('LFT-59, LFT-61')).toBeInTheDocument()
  })

  it('muestra la abstención de forma distinta', async () => {
    streamEvents = [['respuesta', { respuesta: 'No encontré evidencia suficiente.', citas: [], sin_evidencia: true }]]
    await preguntar('¿Cuánto pago de tenencia en la CDMX?')
    expect(await screen.findByText('Sin evidencia suficiente en el corpus')).toBeInTheDocument()
    expect(screen.queryByText('Fuentes')).not.toBeInTheDocument()
  })

  it('muestra el error de la API', async () => {
    fetchMock.mockImplementation(async (url: string) =>
      url.endsWith('/ask/stream')
        ? json({ detail: 'Falta la API key para LLM_PROVIDER=gemini en .env' }, 503)
        : json([]),
    )
    await preguntar()
    expect(await screen.findByRole('alert')).toHaveTextContent('Falta la API key')
  })

  it('no envía preguntas vacías', async () => {
    render(<App />)
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1)) // solo /laws
    expect(screen.getByRole('button', { name: 'Preguntar' })).toBeDisabled()
  })
})
