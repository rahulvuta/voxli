import { useEffect, useId, useRef, type ReactNode } from 'react'
import type { Shape } from '../palette'

const POLY: Record<string, string> = {
  triangle: '10,2.5 18,16.5 2,16.5',
  diamond: '10,1.5 18.5,10 10,18.5 1.5,10',
  star: '10,1.5 12.5,7.4 18.8,7.9 14,12.1 15.5,18.3 10,15 4.5,18.3 6,12.1 1.2,7.9 7.5,7.4',
  plus: '7.2,2 12.8,2 12.8,7.2 18,7.2 18,12.8 12.8,12.8 12.8,18 7.2,18 7.2,12.8 2,12.8 2,7.2 7.2,7.2',
  hexagon: '10,1.5 17.6,5.75 17.6,14.25 10,18.5 2.4,14.25 2.4,5.75',
  down: '2,3.5 18,3.5 10,17.5',
}

/** Speaker shape glyph: the colour-independent half of every speaker's identity. */
export function Glyph({ shape, color, size = 18, letter }: { shape: Shape; color: string; size?: number; letter?: string }) {
  const f = { fill: color, stroke: 'var(--bg)', strokeWidth: 1 }
  return (
    <svg className="glyph" width={size} height={size} viewBox="0 0 20 20" aria-hidden="true">
      {shape === 'circle' && <circle cx="10" cy="10" r="8.5" {...f} />}
      {shape === 'square' && <rect x="2" y="2" width="16" height="16" rx="2.5" {...f} />}
      {shape === 'ring' && <circle cx="10" cy="10" r="7" fill="none" stroke={color} strokeWidth="3" />}
      {shape === 'dashed' && <circle cx="10" cy="10" r="7" fill="none" stroke={color} strokeWidth="2.5" strokeDasharray="3.2 2.6" />}
      {POLY[shape] && <polygon points={POLY[shape]} {...f} strokeLinejoin="round" />}
      {letter && <text x="10" y={shape === 'triangle' ? 14.5 : 13.6} textAnchor="middle" fontSize="9.5" fontWeight="800" fill="#10151b">{letter}</text>}
    </svg>
  )
}

/** Bottom sheet on the native <dialog>: focus trap, Esc to close and inert background come from the platform. */
export function Sheet({ title, onClose, children, kind }: { title: string; onClose(): void; children: ReactNode; kind?: 'full' }) {
  const ref = useRef<HTMLDialogElement>(null)
  const prev = useRef(document.activeElement as HTMLElement | null)
  const id = useId()
  useEffect(() => {
    const d = ref.current
    if (d && !d.open) d.showModal()
    const back = prev.current
    return () => back?.focus?.()
  }, [])
  return (
    <dialog ref={ref} className={`sheet ${kind ?? ''}`} aria-labelledby={id} onClose={onClose} onClick={(e) => { if (e.target === ref.current) onClose() }}>
      <div className="sheet-head">
        <h2 id={id}>{title}</h2>
        <button type="button" className="btn ghost" onClick={onClose} aria-label={`Close ${title}`}>Close</button>
      </div>
      <div className="sheet-body">{children}</div>
    </dialog>
  )
}
