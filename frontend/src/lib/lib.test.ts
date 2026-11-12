import { describe, expect, it } from 'vitest'
import { citaId, shortLabel, splitCitations, suavizar, toParagraphs } from './citations'
import { SSEParser } from './sse'

describe('SSEParser', () => {
  it('arma eventos aunque lleguen partidos en varios trozos', () => {
    const p = new SSEParser()
    expect(p.push('event: paso\ndata: {"nodo":"raz')).toEqual([])
    expect(p.push('onar"}\n\nevent: respuesta\r\ndata: {}\r\n\r\n')).toEqual([
      { event: 'paso', data: '{"nodo":"razonar"}' },
      { event: 'respuesta', data: '{}' },
    ])
  })

  it('ignora comentarios de keep-alive y une varias líneas data', () => {
    const p = new SSEParser()
    expect(p.push(': ping\n\ndata: a\ndata: b\n\n')).toEqual([{ event: 'message', data: 'a\nb' }])
  })
})

describe('citas', () => {
  // Texto de respuesta con citas a artículos reales (LFT 59 y 61).
  const texto =
    'La jornada ordinaria no puede pasar de cuarenta horas semanales [LFT, art. 59]. ' +
    'La diurna dura ocho horas [LFT, art. 61].'

  it('separa texto y citas', () => {
    const seg = splitCitations(texto)
    expect(seg.map((s) => s.type)).toEqual(['text', 'cita', 'text', 'cita', 'text'])
    expect(seg[1]).toMatchObject({ type: 'cita', cita: { ley: 'LFT', numero: '59', transitorio: false } })
  })

  it('reconoce sufijos y transitorios', () => {
    const [, bis, , trans] = splitCitations('Ver [LFT, art. 47 Bis] y [CPEUM, transitorio Primero].')
    expect(bis).toMatchObject({ cita: { numero: '47 Bis' } })
    expect(trans).toMatchObject({ cita: { ley: 'CPEUM', numero: 'Primero', transitorio: true } })
  })

  it('genera los mismos ids que el backend', () => {
    expect(citaId({ ley: 'LFT', numero: '47 Bis' })).toBe('LFT-47_Bis')
    expect(citaId({ ley: 'CPEUM', numero: 'Primero', transitorio: true })).toBe('CPEUM-T-Primero')
    expect(shortLabel({ ley: 'LFT', numero: '61' })).toBe('LFT 61')
  })

  it('reacomoda los saltos de línea del PDF en párrafos', () => {
    // LFT art. 58, con los saltos originales del PDF.
    const art =
      'Jornada de trabajo es el tiempo durante el cual el trabajador está a disposición del\n' +
      'patrón para prestar su trabajo.\n\nEsta podrá ser distribuida de común acuerdo por las ' +
      'personas empleadoras y trabajadoras.'
    expect(toParagraphs(art)).toEqual([
      'Jornada de trabajo es el tiempo durante el cual el trabajador está a disposición del patrón para prestar su trabajo.',
      'Esta podrá ser distribuida de común acuerdo por las personas empleadoras y trabajadoras.',
    ])
  })
})

describe('suavizar', () => {
  it('quita mayúsculas sostenidas sin tocar números romanos', () => {
    // Encabezados reales del corpus (LFT).
    expect(suavizar('Título TERCERO. Condiciones de Trabajo')).toBe('Título Tercero. Condiciones de Trabajo')
    expect(suavizar('Capítulo VIII. Participación de los trabajadores en las utilidades de las empresas')).toBe(
      'Capítulo VIII. Participación de los trabajadores en las utilidades de las empresas',
    )
  })
})
