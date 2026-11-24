import { Monitor, Moon, Play, Square, Sun } from 'lucide-react'
import { useState } from 'react'
import type { TtsVoices } from '../protocol'
import { SIZES, type Settings } from '../settings'
import { SHAPES } from '../palette'
import { Sheet, ShapeMark } from './ui'

function Switch({ id, checked, onChange, label, help }: { id: string; checked: boolean; onChange(v: boolean): void; label: string; help?: string }) {
  return (
    <div className="setting">
      <label htmlFor={id} className="switch-row"><span>{label}</span><input id={id} type="checkbox" role="switch" checked={checked} onChange={(e) => onChange(e.target.checked)} /></label>
      {help && <p className="muted small">{help}</p>}
    </div>
  )
}

interface Props {
  s: Settings
  set(p: Partial<Settings>): void
  voices: TtsVoices | null | 'loading'
  preview: string | null // voice id being previewed
  onPreview(id: string): void
  onClose(): void
  onVoiceMemory(v: boolean): void
  onForget(): void
}

export function SettingsSheet({ s, set, voices, preview, onPreview, onClose, onVoiceMemory, onForget }: Props) {
  const [confirm, setConfirm] = useState(false)
  const list = voices && voices !== 'loading' ? voices : null
  const chosen = s.voice ?? list?.default
  return (
    <Sheet title="Settings" onClose={onClose}>
      <section className="group" aria-labelledby="g-display">
        <h3 id="g-display">Display</h3>
        <div className="setting">
          <span className="lbl" id="l-size">Text size</span>
          <div className="seg wide" role="group" aria-labelledby="l-size">{SIZES.map((z, i) => <button key={z.label} type="button" aria-pressed={s.size === i} onClick={() => set({ size: i })} aria-label={`Text size ${z.label}`}>{z.label}</button>)}</div>
          <p className="sample" aria-hidden="true">Sample caption: Did you get the numbers from finance?</p>
        </div>
        <div className="setting">
          <span className="lbl" id="l-theme">Theme</span>
          <div className="seg wide" role="group" aria-labelledby="l-theme">
            {([['system', 'Auto', Monitor], ['light', 'Light', Sun], ['dark', 'Dark', Moon]] as const).map(([v, l, Icon]) => <button key={v} type="button" aria-pressed={s.theme === v} onClick={() => set({ theme: v })}><Icon size={16} aria-hidden="true" />{l}</button>)}
          </div>
        </div>
        <Switch id="hc" checked={s.contrast} onChange={(v) => set({ contrast: v })} label="High contrast" />
        <div className="setting">
          <span className="lbl" id="l-pal">Speaker colours</span>
          <div className="seg wide" role="group" aria-labelledby="l-pal">
            <button type="button" aria-pressed={s.palette === 'standard'} onClick={() => set({ palette: 'standard' })}>Colour + shape</button>
            <button type="button" aria-pressed={s.palette === 'mono'} onClick={() => set({ palette: 'mono' })}>Shape only</button>
          </div>
          <div className="preview-row" aria-hidden="true">{SHAPES.map((sh, i) => <ShapeMark key={sh} shape={sh} letter={'ABCDEFGH'[i]} color={s.palette === 'mono' ? 'var(--spk-neutral)' : `var(--spk${i})`} size={30} />)}</div>
          <p className="muted small">Colours are colour-blind safe, and every person also has their own shape and initial.</p>
        </div>
        <Switch id="rm" checked={s.reduceMotion} onChange={(v) => set({ reduceMotion: v })} label="Reduce motion" help="Turns off fades and highlights. Starts on if your device asks for it." />
      </section>

      <section className="group" aria-labelledby="g-voice">
        <h3 id="g-voice">Voice</h3>
        <div className="setting">
          <span className="lbl" id="l-voice">Your voice</span>
          {voices === 'loading' && <p className="muted small">Loading voices…</p>}
          {voices === null && <p className="muted small">Natural voices need the Voxli server, which is not reachable. Replies will use this phone’s voice.</p>}
          {list && (
            <div className="voices" role="radiogroup" aria-labelledby="l-voice">
              {list.voices.map((v) => (
                <div key={v.id} className={`vrow${chosen === v.id ? ' sel' : ''}`}>
                  <label>
                    <input type="radio" name="voice" checked={chosen === v.id} onChange={() => set({ voice: v.id })} />
                    <span><b>{v.name}</b><small>{[v.accent, v.gender].filter(Boolean).join(', ')}. {v.description}</small></span>
                  </label>
                  <button type="button" className="ib" onClick={() => onPreview(v.id)} aria-label={preview === v.id ? `Stop preview of ${v.name}` : `Play preview of ${v.name}`}>
                    {preview === v.id ? <Square size={18} fill="currentColor" aria-hidden="true" /> : <Play size={18} fill="currentColor" aria-hidden="true" />}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>

      <section className="group" aria-labelledby="g-privacy">
        <h3 id="g-privacy">Privacy</h3>
        <Switch id="vm" checked={s.voiceMemory} onChange={onVoiceMemory} label="Remember voices" help="Off by default. When on, Voxli keeps a numeric voice fingerprint (never recordings) on the server so it can recognise and name the same people next time." />
        <div className="setting">
          <span className="lbl">Delete everything</span>
          <p className="muted small">Removes this conversation, all speakers, remembered voices and history from the server and this screen.</p>
          {confirm ? (
            <div className="row"><button className="btn danger solid" type="button" onClick={() => { onForget(); setConfirm(false); onClose() }}>Yes, delete everything</button><button className="btn" type="button" onClick={() => setConfirm(false)}>Cancel</button></div>
          ) : <button className="btn danger" type="button" onClick={() => setConfirm(true)}>Delete everything…</button>}
        </div>
      </section>
    </Sheet>
  )
}
