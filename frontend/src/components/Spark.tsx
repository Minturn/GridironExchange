export function Spark({ data, width = 72, height = 20 }: { data: number[]; width?: number; height?: number }) {
  if (data.length < 2) return null
  const min = Math.min(...data)
  const max = Math.max(...data)
  const span = max - min || 1
  const pts = data.map((v, i) => [
    (i / (data.length - 1)) * (width - 4) + 2,
    height - 3 - ((v - min) / span) * (height - 6),
  ])
  const up = data[data.length - 1] >= data[0]
  const color = up ? 'var(--gold)' : 'var(--scarlet-hi)'
  const line = pts.map((p) => p.map((n) => n.toFixed(1)).join(',')).join(' ')
  const [lx, ly] = pts[pts.length - 1]
  return (
    <svg width={width} height={height} aria-hidden="true" style={{ display: 'block', marginLeft: 'auto' }}>
      <polyline points={line} fill="none" stroke={color} strokeWidth="1.3" />
      <circle cx={lx.toFixed(1)} cy={ly.toFixed(1)} r="1.8" fill={color} />
    </svg>
  )
}
