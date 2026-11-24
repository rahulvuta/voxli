import { Maximize2, Plus, Sparkles, Square, Volume2, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useCtx } from '../ctx'
import { IconBtn } from './ui'

const BASE = [['Repeat', 'Could you repeat that, please?'], ['Slower', 'Could you speak a bit slower, please?'], ['One sec', 'One second, please.'], ['Yes', 'Yes.'], ['No', 'No.'], ['Thanks', 'Thank you.']] as const

interface Props { phrases: string[]; setPhrases(p: string[]): void; speaking: boolean; speak(t: string): void; stop(): void; suggest(): void; onShow(t: string): void; lastSpoken: string; text: string; setText(t: string): void }

export function Composer(p: Props) {
  const { state } = useCtx()
  const form = useRef<HTMLFormElement>(null)
  const [open, setOpen] = useState(false)
  const t = p.text.trim()
  const canSave = t && !p.phrases.includes(t) && !BASE.some(([, x]) => x === t)
  const showText = t || p.lastSpoken
  const submit = (e: React.FormEvent) => { e.preventDefault(); if (t) { p.speak(t); p.setText('') } }
  // The tray closes on a tap anywhere outside the composer or on Escape.
  useEffect(() => {
    if (!open) return
    const out = (e: PointerEvent) => { if (!form.current?.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('pointerdown', out)
    return () => document.removeEventListener('pointerdown', out)
  }, [open])
  return (
    <form ref={form} className="composer" onSubmit={submit} aria-label="Reply" onKeyDown={(e) => { if (e.key === 'Escape') setOpen(false) }}>
      {open && (
        <div className="tray" onMouseDown={(e) => { if ((e.target as HTMLElement).tagName !== 'INPUT') e.preventDefault() }}>
          {(state.suggesting || state.replies.length > 0) && (
            <div className="chips" role="group" aria-label="Suggested replies. Tap one to edit it; nothing is spoken automatically">
              <span className="chips-label"><Sparkles size={14} aria-hidden="true" />{state.suggesting ? 'Thinking of replies…' : 'Suggested'}</span>
              {state.replies.map((r) => <button key={r} type="button" className="chip" onClick={() => p.setText(r)}>{r}</button>)}
            </div>
          )}
          <div className="chips" role="group" aria-label="Quick phrases. Tap to speak">
            <span className="chips-label">Say now</span>
            {BASE.map(([l, full]) => <button key={l} type="button" className="chip" onClick={() => p.speak(full)} aria-label={`Say: ${full}`}>{l}</button>)}
            {p.phrases.map((x) => (
              <span key={x} className="chip custom">
                <button type="button" onClick={() => p.speak(x)}>{x}</button>
                <button type="button" className="x" onClick={() => p.setPhrases(p.phrases.filter((y) => y !== x))} aria-label={`Remove quick phrase ${x}`}><X size={14} aria-hidden="true" /></button>
              </span>
            ))}
            {canSave && <button type="button" className="chip add" onClick={() => p.setPhrases([...p.phrases, t])}><Plus size={14} aria-hidden="true" />Save “{t.length > 18 ? `${t.slice(0, 18)}…` : t}”</button>}
          </div>
        </div>
      )}
      <div className="crow">
        <div className="field">
          <input value={p.text} onChange={(e) => p.setText(e.target.value)} onFocus={() => setOpen(true)} aria-label="Type something to say aloud" placeholder="Type to speak…" enterKeyHint="send" autoComplete="off" />
          <IconBtn icon={Sparkles} label="Suggest replies" onClick={() => { setOpen(true); p.suggest() }} disabled={state.suggesting} size={20} />
          <IconBtn icon={Maximize2} label="Show to them in large letters" onClick={() => p.onShow(showText)} disabled={!showText} size={20} />
        </div>
        {p.speaking
          ? <button type="button" className="speak stop" onClick={p.stop}><Square size={18} fill="currentColor" aria-hidden="true" />Stop</button>
          : <button type="submit" className="speak" disabled={!t}><Volume2 size={20} aria-hidden="true" />Speak</button>}
      </div>
      <p className="sr-only" role="status">{p.speaking ? 'Speaking' : ''}</p>
    </form>
  )
}
