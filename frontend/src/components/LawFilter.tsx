import type { Law } from '../lib/api'

interface Props {
  laws: Law[]
  selected: string[]
  onChange: (selected: string[]) => void
  disabled?: boolean
}

/** Casillas del formato: sin selección se consulta todo el corpus. */
export function LawFilter({ laws, selected, onChange, disabled }: Props) {
  const toggle = (clave: string) =>
    onChange(selected.includes(clave) ? selected.filter((c) => c !== clave) : [...selected, clave])

  return (
    <div className="casillas" role="group" aria-label="Leyes a consultar">
      <button
        type="button"
        className="casilla"
        aria-pressed={selected.length === 0}
        onClick={() => onChange([])}
        disabled={disabled}
      >
        Todas
      </button>
      {laws.map((law) => (
        <button
          key={law.clave}
          type="button"
          className="casilla"
          aria-pressed={selected.includes(law.clave)}
          onClick={() => toggle(law.clave)}
          title={`${law.nombre} · ${law.articulos.toLocaleString('es-MX')} artículos`}
          disabled={disabled}
        >
          {law.clave}
        </button>
      ))}
    </div>
  )
}
