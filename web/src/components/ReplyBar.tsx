import { useState } from 'react'
import { useCtx } from '../ctx'

const BASE = [['Repeat', 'Could you repeat that, please?'], ['Slower', 'Could you speak a bit slower, please?'], ['One sec', 'One second, please.']] as const

export function ReplyBar(p: { phrases: string[]; setPhrases(p: string[]): void; speaking: boolean; speak(t: string): void; stop(): void; suggest(): void; onShow(t: string): void; lastSpoken: string; text: string; setText(t: string): void }) {
  const { state } = useCtx()
  const [hint, setHint] = useState('')
  const t = p.text.trim()
  const canSave = t && !p.phrases.includes(t) && !BASE.some(([, x]) => x === t)
  const submit = (e: React.FormEvent) => { e.preventDefault(); if (t) { p.speak(t); p.setText('') } }
  const showText = t || p.lastSpoken
  return (
    <form className="reply" onSubmit={submit} aria-label="Reply">
      {(state.replies.length > 0 || state.suggesting) && (
        <div className="chips" role="group" aria-label="Suggested replies (tap to edit, nothing is spoken automatically)">
          {state.suggesting && <span className="muted small">Thinking of replies…</span>}
          {state.replies.map((r) => <button key={r} type="button" className="chip sug" onClick={() => { p.setText(r); setHint('Edit it or press Speak') }}>{r}</button>)}
        </div>
      )}
      <div className="chips" role="group" aria-label="Quick phrases (tap to speak)">
        <button type="button" className="chip tool" onClick={p.suggest} disabled={state.suggesting}>Suggest</button>
        <button type="button" className="chip tool" onClick={() => p.onShow(showText)} disabled={!showText}>Show to them</button>
        {BASE.map(([l, full]) => <button key={l} type="button" className="chip phrase" onClick={() => p.speak(full)} aria-label={`Say: ${full}`}>{l}</button>)}
        {p.phrases.map((x) => (
          <span key={x} className="chip phrase custom">
            <button type="button" onClick={() => p.speak(x)}>{x}</button>
            <button type="button" className="x" onClick={() => p.setPhrases(p.phrases.filter((y) => y !== x))} aria-label={`Remove quick phrase ${x}`}>×</button>
          </span>
        ))}
      </div>
      <div className="row">
        <input value={p.text} onChange={(e) => { p.setText(e.target.value); setHint('') }} aria-label="Type something to say aloud" placeholder="Type to speak…" enterKeyHint="send" autoComplete="off" />
        {canSave && <button type="button" className="btn" onClick={() => p.setPhrases([...p.phrases, t])} aria-label="Save as quick phrase">Save</button>}
        {p.speaking ? <button type="button" className="btn danger" onClick={p.stop}>Stop</button> : <button type="submit" className="btn primary" disabled={!t}>Speak</button>}
      </div>
      <p className="sr-only" role="status">{p.speaking ? 'Speaking' : hint}</p>
    </form>
  )
}
