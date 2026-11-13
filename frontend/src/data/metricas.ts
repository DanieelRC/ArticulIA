/**
 * Métricas reales de eval/results/. Se actualizan a mano después de cada evaluación;
 * no se redondean hacia arriba ni se omiten las que no alcanzan la meta.
 */
export interface Metrica {
  nombre: string
  que: string
  valor: number | null // null = aún no medida
  meta: number | null
}

export const EVALUACION = {
  fecha: '13 de noviembre de 2026',
  preguntas: 60,
  nota: 'Dataset propio en lenguaje cotidiano: 38 directas, 12 de dos artículos y 10 sin respuesta en el corpus. Modelo: grok-build-0.1.',
  metricas: [
    { nombre: 'Citas válidas', que: 'Las citas apuntan a artículos que el agente sí recuperó', valor: 1.0, meta: 1.0 },
    { nombre: 'Abstención correcta', que: 'Dice «sin evidencia» en las preguntas que el corpus no cubre', valor: 1.0, meta: 0.8 },
    { nombre: 'Fidelidad', que: 'Cada afirmación está respaldada por lo que cita (Ragas)', valor: 0.9, meta: 0.85 },
    { nombre: 'Hit@5', que: 'El artículo correcto está entre los 5 recuperados', valor: 0.78, meta: 0.85 },
    { nombre: 'MRR', que: 'Qué tan arriba aparece el artículo correcto', valor: 0.67, meta: 0.7 },
    { nombre: 'Relevancia', que: 'La respuesta atiende lo que se preguntó (Ragas)', valor: 0.74, meta: 0.8 },
  ] as Metrica[],
}

export const GITHUB_URL: string | undefined = import.meta.env.VITE_GITHUB_URL || undefined
export const AUTOR = 'Daniel Rodríguez Carreón'
