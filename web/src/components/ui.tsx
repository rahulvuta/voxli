import { X, type LucideIcon } from 'lucide-react'
import { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import { useCtx } from '../ctx'
import type { Shape } from '../palette'

const SHAPE: Record<Shape, { d: string; y: number }> = {
  circle: { d: 'M12 1.5a10.5 10.5 0 1 1 0 21 10.5 10.5 0 0 1 0-21z', y: 16 },
  square: { d: 'M5 2.5h14a2.5 2.5 0 0 1 2.5 2.5v14a2.5 2.5 0 0 1-2.5 2.5H5A2.5 2.5 0 0 1 2.5 19V5A2.5 2.5 0 0 1 5 2.5z', y: 16 },
  hexagon: { d: 'M12 1.5l9 5.2v10.6l-9 5.2-9-5.2V6.7z', y: 16 },
  diamond: { d: 'M12 1l10.5 11L12 23 1.5 12z', y: 16 },
  octagon: { d: 'M8 2h8l6 6v8l-6 6H8l-6-6V8z', y: 16 },
  pentagon: { d: 'M12 1.5l10 7.3-3.8 11.7H5.8L2 8.8z', y: 16.5 },
  shield: { d: 'M3 3h18v10l-9 9-9-9z', y: 14.5 },
  triangle: { d: 'M12 2.5l10.5 18.5h-21z', y: 18 },
}

/** Speaker identity: shape + initial + colour. Rings (glow = speaking, dashed = unsure) are CSS on the wrapper. */
export function ShapeMark({ shape, color, letter, size = 36, on, unsure }: { shape: Shape; color: string; letter: string; size?: number; on?: boolean; unsure?: boolean }) {
  const p = SHAPE[shape]
  return (
    <span className={`av${on ? ' on' : ''}${unsure ? ' unsure' : ''}`} style={{ '--c': color, '--sz': `${size}px` } as React.CSSProperties} aria-hidden="true">
      <svg viewBox="0 0 24 24">
        <path d={p.d} fill="var(--c)" stroke="var(--c)" strokeWidth="1.6" strokeLinejoin="round" />
        <text x="12" y={p.y} textAnchor="middle" fontSize="12.5" fontWeight="700" fill="var(--on-spk)">{letter}</text>
      </svg>
    </span>
  )
}

export function Avatar({ skey, size = 36 }: { skey: string; size?: number }) {
  const { state, look, unsure } = useCtx()
  const l = look(skey)
  return <ShapeMark {...l} size={size} on={state.speakers[skey]?.active} unsure={unsure.has(skey)} />
}

export function IconBtn({ icon: Icon, label, onClick, pressed, disabled, className = '', size = 22, type = 'button' }: { icon: LucideIcon; label: string; onClick?(): void; pressed?: boolean; disabled?: boolean; className?: string; size?: number; type?: 'button' | 'submit' }) {
  return (
    <button type={type} className={`ib ${className}`} onClick={onClick} aria-label={label} title={label} aria-pressed={pressed} disabled={disabled}>
      <Icon size={size} strokeWidth={2} aria-hidden="true" />
    </button>
  )
}

/** Bottom sheet on the native <dialog>: focus trap, Esc to close and inert background come from the platform. */
export function Sheet({ title, onClose, children, kind, lead }: { title: string; onClose(): void; children: ReactNode; kind?: 'full'; lead?: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null)
  const prev = useRef(document.activeElement as HTMLElement | null)
  const id = useId()
  useEffect(() => {
    const d = ref.current
    if (d && !d.open) { d.showModal(); d.focus() }
    const back = prev.current
    return () => back?.focus?.()
  }, [])
  return (
    <dialog ref={ref} tabIndex={-1} className={`sheet ${kind ?? ''}`} aria-labelledby={id} onClose={onClose} onClick={(e) => { if (e.target === ref.current) onClose() }}>
      <div className="sheet-head">
        {lead}
        <h2 id={id}>{title}</h2>
        <IconBtn icon={X} label={`Close ${title}`} onClick={onClose} />
      </div>
      <div className="sheet-body">{children}</div>
    </dialog>
  )
}

/** Polite, batched screen-reader announcements of finished captions (the visual captions are not live regions). */
export function Announcer() {
  const { sorted, name } = useCtx()
  const [text, setText] = useState('')
  const said = useRef(new Set<string>())
  const queue = useRef<string[]>([])
  useEffect(() => {
    for (const u of sorted) if (u.is_final && u.source !== 'you' && !said.current.has(u.key)) { said.current.add(u.key); queue.current.push(`${name(u.skey)}: ${u.text}`) }
  }, [sorted, name])
  useEffect(() => {
    const t = window.setInterval(() => { if (queue.current.length) setText(queue.current.splice(0).slice(-3).join(' ')) }, 2500)
    return () => clearInterval(t)
  }, [])
  return <div className="sr-only" aria-live="polite" aria-atomic="true">{text}</div>
}
