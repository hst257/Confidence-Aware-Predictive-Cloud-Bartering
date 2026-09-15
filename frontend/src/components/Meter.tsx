export function Meter({ value, total, tone = 'cyan' }: { value: number; total: number; tone?: 'cyan' | 'violet' | 'amber' }) {
  const percent = Math.max(0, Math.min(100, (value / total) * 100))
  return (
    <div className="meter-track" aria-label={`${percent.toFixed(0)} percent`}>
      <span className={`meter-fill ${tone}`} style={{ width: `${percent}%` }} />
    </div>
  )
}

