export function Meter({ value, total, tone = 'cyan', inline = false }: { value: number; total: number; tone?: 'cyan' | 'violet' | 'amber'; inline?: boolean }) {
  const percent = Math.max(0, Math.min(100, (value / total) * 100))
  const Track = inline ? 'span' : 'div'
  return (
    <Track className="meter-track" aria-label={`${percent.toFixed(0)} percent`}>
      <span className={`meter-fill ${tone}`} style={{ width: `${percent}%` }} />
    </Track>
  )
}

