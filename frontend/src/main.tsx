import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
// Fuentes autoalojadas: sin peticiones a terceros.
import '@fontsource-variable/archivo/wdth.css'
import '@fontsource-variable/literata/wght.css'
import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
