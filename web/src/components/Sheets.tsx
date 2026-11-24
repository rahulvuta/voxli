import { useEffect, useState } from 'react'
import { useCtx } from '../ctx'
import { SIZES, type Settings } from '../settings'
import { Glyph, Sheet } from './ui'

export function SpeakerSheet({ skey, onClose, onRename, onMerge }: { skey: string; onClose(): void; onRename(skey: string, name: string): void; onMerge(from: string, into: string): void }) {
  const { state, look, name } = useCtx()
  const s = state.speakers[skey]
  const [val, setVal] = useState(s?.name ?? '')
  const [into, setInto] = useState('')
  if (!s) return null
  const l = look(skey)
  const others = Object.values(state.speakers).filter((o) => o.key !== skey && o.epoch === s.epoch && o.id !== 'YOU')
  const dir = s.direction_deg == null ? 'unknown (mono microphone or not located yet)' : `about ${Math.abs(Math.round(s.direction_deg))}° to your ${s.direction_deg < 0 ? 'left' : 'right'}`
  return (
    <Sheet title={name(skey)} onClose={onClose}>
      <p className="who-line"><Glyph shape={l.shape} color={l.color} size={28} /> <span>{s.label}{s.id !== 'YOU' && <> · direction {dir}</>}</span></p>
      {s.id === 'YOU' ? <p className="muted">These are the replies you typed and spoke aloud.</p> : (
        <>
          <form className="stack" onSubmit={(e) => { e.preventDefault(); if (val.trim()) { onRename(skey, val.trim()); onClose() } }}>
            <label htmlFor="rn">Name this person</label>
            <div className="row"><input id="rn" value={val} onChange={(e) => setVal(e.target.value)} placeholder={s.label} autoComplete="off" /><button className="btn primary" type="submit" disabled={!val.trim()}>Save</button></div>
          </form>
          {others.length > 0 && (
            <form className="stack" onSubmit={(e) => { e.preventDefault(); if (into) { onMerge(skey, into); onClose() } }}>
              <label htmlFor="mg">Same person as…</label>
              <p className="muted small">If Voxli split one person into two labels, merge them. Their lines move to the person you pick.</p>
              <div className="row">
                <select id="mg" value={into} onChange={(e) => setInto(e.target.value)}>
                  <option value="">Choose a person</option>
                  {others.map((o) => <option key={o.key} value={o.key}>{name(o.key)}</option>)}
                </select>
                <button className="btn" type="submit" disabled={!into}>Merge</button>
              </div>
            </form>
          )}
        </>
      )}
    </Sheet>
  )
}

export function CatchUpSheet({ onClose, onAsk }: { onClose(): void; onAsk(sec: number): void }) {
  const { state, look, name } = useCtx()
  const [sec, setSec] = useState(60)
  useEffect(() => { onAsk(sec) }, [sec]) // eslint-disable-line
  const opts = [[30, '30 s'], [60, '1 min'], [180, '3 min']] as const
  return (
    <Sheet title="Catch me up" onClose={onClose}>
      <div className="seg wide" role="group" aria-label="How far back">
        {opts.map(([v, l]) => <button key={v} type="button" aria-pressed={sec === v} onClick={() => setSec(v)}>Last {l}</button>)}
      </div>
      <div aria-live="polite">
        {state.catching && <p className="muted">Gathering what was said…</p>}
        {state.catchUp && state.catchUp.length === 0 && <p className="muted">Nothing was said in that time.</p>}
        {state.catchUp?.map((it) => {
          const l = look(it.skey)
          const lines = it.ukeys.map((k) => state.utts[k]).filter(Boolean)
          return (
            <section key={it.skey} className="cu" style={{ '--c': l.color } as React.CSSProperties}>
              <h3><Glyph shape={l.shape} color={l.color} size={18} /> {name(it.skey)}</h3>
              <ul className="verbatim">{lines.map((u) => <li key={u.key}>{u.text}</li>)}</ul>
              {it.summary && <p className="ai"><span className="tag ai-tag">AI summary</span> {it.summary}</p>}
            </section>
          )
        })}
      </div>
      <p className="muted small">Lines are exactly what was heard. Summaries are written by AI and may miss detail.</p>
    </Sheet>
  )
}

function Switch({ id, checked, onChange, label, help }: { id: string; checked: boolean; onChange(v: boolean): void; label: string; help?: string }) {
  return (
    <div className="setting">
      <label htmlFor={id} className="switch-row"><span>{label}</span><input id={id} type="checkbox" role="switch" checked={checked} onChange={(e) => onChange(e.target.checked)} /></label>
      {help && <p className="muted small">{help}</p>}
    </div>
  )
}

export function SettingsSheet({ s, set, onClose, onVoice, onForget }: { s: Settings; set(p: Partial<Settings>): void; onClose(): void; onVoice(v: boolean): void; onForget(): void }) {
  const [confirm, setConfirm] = useState(false)
  return (
    <Sheet title="Settings" onClose={onClose}>
      <fieldset className="setting">
        <legend>Text size</legend>
        <div className="seg wide">{SIZES.map((z, i) => <button key={z.label} type="button" aria-pressed={s.size === i} onClick={() => set({ size: i })} aria-label={`Text size ${z.label}`}>{z.label}</button>)}</div>
        <p className="sample" aria-hidden="true">Sample caption text</p>
      </fieldset>
      <Switch id="hc" checked={s.contrast} onChange={(v) => set({ contrast: v })} label="High contrast" />
      <fieldset className="setting">
        <legend>Speaker colours</legend>
        <div className="seg wide">
          <button type="button" aria-pressed={s.palette === 'standard'} onClick={() => set({ palette: 'standard' })}>Colour + shape</button>
          <button type="button" aria-pressed={s.palette === 'mono'} onClick={() => set({ palette: 'mono' })}>Shape only</button>
        </div>
        <p className="muted small">Colours are colour-blind safe, and every person also has their own shape.</p>
      </fieldset>
      <Switch id="rm" checked={s.reduceMotion} onChange={(v) => set({ reduceMotion: v })} label="Reduce motion" help="Stops pulsing and sliding. Starts on if your device asks for it." />
      <Switch id="vm" checked={s.voiceMemory} onChange={onVoice} label="Remember voices" help="Off by default. When on, Voxli keeps a numeric voice fingerprint (never recordings) on the server so it can recognise and name the same people next time." />
      <div className="setting danger">
        <h3>Delete everything</h3>
        <p className="muted small">Removes this conversation, all speakers, remembered voices and history from the server and this screen.</p>
        {confirm ? (
          <div className="row"><button className="btn danger" type="button" onClick={() => { onForget(); setConfirm(false); onClose() }}>Yes, delete everything</button><button className="btn" type="button" onClick={() => setConfirm(false)}>Cancel</button></div>
        ) : <button className="btn danger" type="button" onClick={() => setConfirm(true)}>Delete everything…</button>}
      </div>
    </Sheet>
  )
}

export function ShowSheet({ text, onClose }: { text: string; onClose(): void }) {
  return (
    <Sheet title="Showing to them" onClose={onClose} kind="full">
      <p className="show-text" lang={navigator.language}>{text}</p>
    </Sheet>
  )
}
