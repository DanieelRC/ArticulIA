/**
 * Métricas reales de eval/results/. Se actualizan a mano después de cada evaluación;
 * no se redondean hacia arriba ni se omiten las que no alcanzan la meta.
 */
export interface Metrica {
  nombre: string
  que: string
  valor: number | null // null = aún no medida
  meta: number | null
  formato?: 'ratio' | 'segundos'
}

export const EVALUACION = {
  fecha: '12 de noviembre de 2026',
  preguntas: 60,
  nota: 'Dataset propio en lenguaje cotidiano: 38 directas, 12 de dos artículos y 10 sin respuesta en el corpus.',
  metricas: [
    { nombre: 'Hit@5', que: 'El artículo correcto está entre los 5 recuperados', valor: 0.78, meta: 0.85 },
    { nombre: 'MRR', que: 'Qué tan arriba aparece el artículo correcto', valor: 0.63, meta: 0.7 },
    { nombre: 'Recall@5', que: 'Fracción de los artículos esperados que se recuperan', valor: 0.75, meta: null },
    { nombre: 'Fidelidad', que: 'Cada afirmación está respaldada por lo que cita (Ragas)', valor: null, meta: 0.85 },
    { nombre: 'Abstención correcta', que: 'Dice «no hay evidencia» cuando no la hay', valor: null, meta: 0.8 },
  ] as Metrica[],
}

export const GITHUB_URL: string | undefined = import.meta.env.VITE_GITHUB_URL || undefined
export const AUTOR = 'Daniel Rodríguez Carreón'
