import { Sparkles } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useCtx } from '../ctx'
import { Line } from './Line'
import { clock } from '../store'
import { Avatar, Sheet } from './ui'

/** A person's full history, newest first. Rename and merge live here too. */
export function SpeakerSheet({ skey, focus, onClose, onRename, onMerge }: { skey: string; focus?: string; onClose(): void; onRename(skey: string, name: string): void; onMerge(from: string, into: string): void }) {
  const { state, sorted, hidden, name } = useCtx()
  const s = state.speakers[skey]
  const [val, setVal] = useState(s?.name ?? '')
  const [into, setInto] = useState('')
  const list = useRef<HTMLUListElement>(null)
  const mine = useMemo(() => sorted.filter((u) => u.skey === skey && !hidden.has(u.key)).reverse(), [sorted, hidden, skey])
  useEffect(() => {
    const el = focus && list.current?.querySelector<HTMLElement>(`[data-u="${CSS.escape(focus)}"]`)
    if (!el) return
    el.scrollIntoView({ block: 'center' })
    el.classList.add('flash')
    const t = window.setTimeout(() => el.classList.remove('flash'), 1600)
    return () => clearTimeout(t)
  }, [focus])
  if (!s) return null
  const others = Object.values(state.speakers).filter((o) => o.key !== skey && o.epoch === s.epoch && o.id !== 'YOU')
  const dir = s.direction_deg == null ? null : `about ${Math.abs(Math.round(s.direction_deg))}° to your ${s.direction_deg < 0 ? 'left' : 'right'}`
  return (
    <Sheet title={name(skey)} onClose={onClose} lead={<Avatar skey={skey} size={40} />}>
      <p className="muted">{s.label}{dir && <> · {dir}</>}</p>
      {s.id !== 'YOU' && (
        <form className="row" onSubmit={(e) => { e.preventDefault(); if (val.trim()) { onRename(skey, val.trim()); onClose() } }}>
          <input aria-label="Name this person" value={val} onChange={(e) => setVal(e.target.value)} placeholder={`Name this person (${s.label})`} autoComplete="off" />
          <button className="btn primary" type="submit" disabled={!val.trim()}>Save</button>
        </form>
      )}
      <h3>{s.id === 'YOU' ? 'What you said aloud' : 'What they said'}</h3>
      <ul className="history" ref={list}>
        {mine.length === 0 && <li className="muted">Nothing yet.</li>}
        {mine.map((u) => <li key={u.key}><time>{clock(u.start)}</time><Line u={u} size="sm" /></li>)}
      </ul>
      {s.id !== 'YOU' && others.length > 0 && (
        <details className="merge">
          <summary>Same person as someone else?</summary>
          <p className="muted small">If Voxli split one person into two labels, merge them. Their lines move to the person you pick.</p>
          <form className="row" onSubmit={(e) => { e.preventDefault(); if (into) { onMerge(skey, into); onClose() } }}>
            <select aria-label="Merge into" value={into} onChange={(e) => setInto(e.target.value)}>
              <option value="">Choose a person</option>
              {others.map((o) => <option key={o.key} value={o.key}>{name(o.key)}</option>)}
            </select>
            <button className="btn" type="submit" disabled={!into}>Merge</button>
          </form>
        </details>
      )}
    </Sheet>
  )
}

export function CatchUpSheet({ onClose, onAsk }: { onClose(): void; onAsk(sec: number): void }) {
  const { state, name } = useCtx()
  const [sec, setSec] = useState(60)
  useEffect(() => { onAsk(sec) }, [sec]) // eslint-disable-line
  const opts = [[30, '30 s'], [60, '1 min'], [180, '3 min']] as const
  return (
    <Sheet title="Catch me up" onClose={onClose}>
      <div className="seg wide" role="group" aria-label="How far back">
        {opts.map(([v, l]) => <button key={v} type="button" aria-pressed={sec === v} onClick={() => setSec(v)}>Last {l}</button>)}
      </div>
      <div aria-live="polite" className="catch-list">
        {state.catching && <p className="muted">Gathering what was said…</p>}
        {state.catchUp && state.catchUp.length === 0 && <p className="muted">Nothing was said in that time.</p>}
        {state.catchUp?.map((it) => {
          const lines = it.ukeys.map((k) => state.utts[k]).filter(Boolean)
          return (
            <section key={it.skey} className="cu">
              <h3><Avatar skey={it.skey} size={28} />{name(it.skey)}</h3>
              <ul className="verbatim">{lines.map((u) => <li key={u.key}>{u.text}</li>)}</ul>
              {it.summary && <p className="ai"><span className="tag ai-tag"><Sparkles size={12} aria-hidden="true" />AI summary</span>{it.summary}</p>}
            </section>
          )
        })}
      </div>
      <p className="muted small">Lines are exactly what was heard. Summaries are written by AI and may miss detail.</p>
    </Sheet>
  )
}

export function ShowSheet({ text, onClose }: { text: string; onClose(): void }) {
  return (
    <Sheet title="Showing to them" onClose={onClose} kind="full">
      <p className={`show-text${text.length > 70 ? ' long' : ''}`} lang={navigator.language}>{text}</p>
    </Sheet>
  )
}
