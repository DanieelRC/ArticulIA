import { useCallback, useState } from 'react'
import { Filtros } from './components/ui'
import { useRoute } from './lib/router'
import Chat from './pages/Chat'
import Home from './pages/Home'

export const RUTA_CONSULTA = '/consulta'

export default function App() {
  const { path, go } = useRoute()
  const [inicial, setInicial] = useState<string | null>(null)

  const preguntar = useCallback(
    (pregunta?: string) => {
      setInicial(pregunta?.trim() || null)
      go(RUTA_CONSULTA)
    },
    [go],
  )
  const usada = useCallback(() => setInicial(null), [])

  return (
    <>
      <Filtros />
      {path.startsWith(RUTA_CONSULTA) ? (
        <Chat go={go} inicial={inicial} onInicialUsada={usada} />
      ) : (
        <Home onPreguntar={preguntar} />
      )}
    </>
  )
}
