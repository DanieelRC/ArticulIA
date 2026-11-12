import type { Law } from '../lib/api'

interface Props {
  laws: Law[]
  selected: string[]
  onChange: (selected: string[]) => void
  disabled?: boolean
}

/** Filtro por ley: sin selección se busca en todo el corpus. */
export function LawFilter({ laws, selected, onChange, disabled }: Props) {
  const toggle = (clave: string) =>
    onChange(selected.includes(clave) ? selected.filter((c) => c !== clave) : [...selected, clave])

  return (
    <div className="law-filter" role="group" aria-label="Filtrar por ley">
      <button
        type="button"
        className="chip"
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
          className="chip"
          aria-pressed={selected.includes(law.clave)}
          onClick={() => toggle(law.clave)}
          title={`${law.nombre} · ${law.articulos} artículos`}
          disabled={disabled}
        >
          {law.clave}
        </button>
      ))}
    </div>
  )
}
