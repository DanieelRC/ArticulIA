import { useCallback, useEffect, useState } from 'react'

/** Ruteo mínimo con History API: dos vistas no justifican una librería. */
export function useRoute() {
  const [path, setPath] = useState(() => window.location.pathname)

  useEffect(() => {
    const onPop = () => setPath(window.location.pathname)
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  const go = useCallback((to: string) => {
    if (to !== window.location.pathname) window.history.pushState(null, '', to)
    setPath(to)
    window.scrollTo?.(0, 0)
  }, [])

  return { path, go }
}
