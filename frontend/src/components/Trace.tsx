import type { Reading } from '../api/client'

/** A tiny scope-style trace for one channel. Non-numeric channels draw nothing. */
export function Trace({ values }: { values: Reading['value'][] }) {
  const numbers = values.filter((value): value is number => typeof value === 'number')
  if (numbers.length < 2 || numbers.length !== values.length) return null
  const width = 72
  const height = 22
  const min = Math.min(...numbers)
  const max = Math.max(...numbers)
  const span = max - min || 1
  const points = numbers.map((value, index) => {
    const x = (index / (numbers.length - 1)) * (width - 4) + 2
    const y = max === min ? height / 2 : height - 3 - ((value - min) / span) * (height - 6)
    return `${x.toFixed(1)},${y.toFixed(1)}`
  })
  return (
    <svg className="trace" viewBox={`0 0 ${width} ${height}`} width={width} height={height} aria-hidden="true">
      <line x1="0" x2={width} y1={height / 2} y2={height / 2} className="trace-axis" />
      <polyline points={points.join(' ')} className="trace-line" />
    </svg>
  )
}
