import type { ReactNode } from 'react'

/** Marca: «ARTICUL» en tinta y «IA» resaltado como campo de formato. */
export function Marca({ onClick }: { onClick?: () => void }) {
  const cuerpo = (
    <>
      ARTICUL<span className="marca-ia">IA</span>
    </>
  )
  return onClick ? (
    <button type="button" className="marca" onClick={onClick} aria-label="ArticulIA, ir al inicio">
      {cuerpo}
    </button>
  ) : (
    <span className="marca" aria-label="ArticulIA">
      {cuerpo}
    </span>
  )
}

type Tinta = 'rojo' | 'azul' | 'violeta' | 'negro'

interface SelloProps {
  titulo: string
  linea?: string
  tinta?: Tinta
  /** Cae con golpe al montarse (se omite con prefers-reduced-motion). */
  golpe?: boolean
  className?: string
}

/** Sello de goma: doble marco, tinta irregular y una ligera inclinación. */
export function Sello({ titulo, linea, tinta = 'rojo', golpe, className = '' }: SelloProps) {
  return (
    <span className={`sello sello-${tinta}${golpe ? ' sello-golpe' : ''} ${className}`}>
      <span className="sello-titulo">{titulo}</span>
      {linea && <span className="sello-linea">{linea}</span>}
    </span>
  )
}

const TRAZOS: Record<string, ReactNode> = {
  flecha: <path d="M4 12h15m-6-6 6 6-6 6" />,
  cerrar: <path d="M6 6l12 12M18 6 6 18" />,
  copiar: (
    <>
      <rect x="8" y="8" width="11" height="12" />
      <path d="M5 16V4h11" />
    </>
  ),
  listo: <path d="m5 12.5 4.5 4.5L19 7.5" />,
  detener: <rect x="6.5" y="6.5" width="11" height="11" />,
  mas: <path d="M12 5v14M5 12h14" />,
  borrar: <path d="M5 7h14M10 7V4h4v3m-7 0 1 13h8l1-13" />,
  archivo: <path d="M4 6h6l2 2h8v11H4zM4 11h16" />,
  anterior: <path d="m14 6-6 6 6 6" />,
  siguiente: <path d="m10 6 6 6-6 6" />,
  externo: <path d="M10 5H5v14h14v-5M13 5h6v6m0-6-9 9" />,
  reintentar: <path d="M19 12a7 7 0 1 1-2.2-5.1M19 4v4h-4" />,
}

/** Iconos propios, un solo trazo de 1.75 en cuadrícula de 24. */
export function Icono({ n, size = 18 }: { n: keyof typeof TRAZOS; size?: number }) {
  return (
    <svg
      className="icono"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="square"
      strokeLinejoin="miter"
      aria-hidden="true"
    >
      {TRAZOS[n]}
    </svg>
  )
}

/** Filtros SVG compartidos: dan a los sellos el borde irregular de la tinta. */
export function Filtros() {
  return (
    <svg width="0" height="0" style={{ position: 'absolute' }} aria-hidden="true">
      <filter id="tinta" x="-5%" y="-10%" width="110%" height="120%">
        <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" seed="7" result="r" />
        <feDisplacementMap in="SourceGraphic" in2="r" scale="1.6" />
        <feComponentTransfer>
          <feFuncA type="table" tableValues="0 0.92" />
        </feComponentTransfer>
      </filter>
    </svg>
  )
}
