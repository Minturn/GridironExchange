export function AreaChart({
  data,
  p0,
  width = 320,
  height = 110,
}: {
  data: number[]
  p0: number
  width?: number
  height?: number
}) {
  if (data.length < 2)
    return <p className="dim" style={{ padding: '4px 14px' }}>No price history yet — charts start with trading.</p>
  const all = [...data, p0]
  const min = Math.min(...all) * 0.96
  const max = Math.max(...all) * 1.04
  const span = max - min || 1
  const X = (i: number) => (i / (data.length - 1)) * (width - 8) + 4
  const Y = (v: number) => height - 8 - ((v - min) / span) * (height - 16)
  const pts = data.map((v, i) => `${X(i).toFixed(1)},${Y(v).toFixed(1)}`).join(' ')
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label="price chart" style={{ maxWidth: '100%' }}>
      <polygon points={`4,${height - 8} ${pts} ${width - 4},${height - 8}`} fill="rgba(179,153,93,.14)" />
      <line x1="4" y1={Y(p0).toFixed(1)} x2={width - 4} y2={Y(p0).toFixed(1)} stroke="var(--ink-faint)" strokeDasharray="3 4" strokeWidth="1" />
      <text x={width - 6} y={(Y(p0) - 4).toFixed(1)} fill="var(--ink-faint)" fontSize="9" textAnchor="end">
        IPO {p0.toFixed(2)}
      </text>
      <polyline points={pts} fill="none" stroke="var(--gold)" strokeWidth="1.6" />
      <circle cx={X(data.length - 1).toFixed(1)} cy={Y(data[data.length - 1]).toFixed(1)} r="2.6" fill="var(--gold-hi)" />
    </svg>
  )
}
