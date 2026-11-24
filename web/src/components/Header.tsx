import { useCtx } from '../ctx'
import type { Spk } from '../store'
import { Glyph } from './ui'

export type MicStatus = 'off' | 'on' | 'paused' | 'denied' | 'demo'
export type View = 'lanes' | 'timeline'

function Radar() {
  const { state, look, name, openSpeaker } = useCtx()
  const list = Object.values(state.speakers).filter((s) => s.epoch === state.epoch && s.id !== 'YOU' && s.id !== 'UNKNOWN')
  const unknown = list.filter((s) => s.direction_deg == null)
  const pos = (s: Spk) => {
    // -90 (left) .. +90 (right) on the upper arc; unknown: evenly around the ring (all unknown) or along the lower arc.
    const i = unknown.indexOf(s)
    const deg = s.direction_deg ?? (unknown.length === list.length ? (360 * i) / list.length - 90 + 45 : unknown.length === 1 ? 180 : 130 + (100 * i) / (unknown.length - 1))
    const a = (deg * Math.PI) / 180
    return { x: 50 + 37 * Math.sin(a), y: 50 - 37 * Math.cos(a) }
  }
  const dirText = (s: Spk) => (s.direction_deg == null ? 'direction unknown' : Math.abs(s.direction_deg) < 15 ? 'in front' : `to your ${s.direction_deg < 0 ? 'left' : 'right'}`)
  return (
    <div className="radar" role="group" aria-label="Who is speaking and where">
      <svg viewBox="0 0 100 100" aria-hidden="true">
        <circle cx="50" cy="50" r="37" className="ring" />
        <circle cx="50" cy="50" r="20" className="ring inner" />
        <rect x="45" y="41" width="10" height="18" rx="2.5" className="phone" />
      </svg>
      {list.length === 0 && <span className="radar-empty">Listening…</span>}
      {list.map((s) => {
        const { x, y } = pos(s)
        const l = look(s.key)
        const n = name(s.key)
        return (
          <button key={s.key} type="button" className={`dot ${s.active ? 'active' : ''}`} style={{ left: `${x}%`, top: `${y}%`, '--c': l.color } as React.CSSProperties}
            onClick={() => openSpeaker(s.key)} aria-label={`${n}, ${s.active ? 'speaking now, ' : ''}${dirText(s)}. Open options`}>
            <Glyph shape={l.shape} color={l.color} size={30} letter={n.replace(/^Speaker /, '').charAt(0).toUpperCase()} />
          </button>
        )
      })}
    </div>
  )
}

export function Header(p: { view: View; setView(v: View): void; mic: MicStatus; onCatchUp(): void; onSettings(): void; micDetail: string }) {
  const { state } = useCtx()
  const down = state.conn === 'reconnecting'
  const asr = down ? 'reconnecting' : state.asr
  const asrMap = { deepgram: ['circle', 'Deepgram'], local: ['square', 'Local'], reconnecting: ['triangle', 'Reconnecting'], offline: ['down', 'Offline'] } as const
  const [shape, label] = asr ? asrMap[asr] : (['dashed', 'Connecting'] as const)
  const micText = { off: 'Mic off', on: 'Mic on', paused: 'Mic paused', denied: 'Mic blocked', demo: 'Demo' }[p.mic]
  return (
    <header className="top">
      <div className="top-row">
        <h1 className="brand">Voxli</h1>
        <div className="pills">
          <span className="pill" role="status" aria-label={`Captioning engine: ${label}`}><Glyph shape={shape} color="var(--text)" size={12} />{label}</span>
          <span className={`pill mic ${p.mic}`} role="status" aria-label={p.micDetail}><span className="reclamp" aria-hidden="true" />{micText}</span>
          <button type="button" className="btn icon" onClick={p.onSettings} aria-label="Settings">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M4 7h10M18 7h2M4 17h2M10 17h10" /><circle cx="16" cy="7" r="2.2" /><circle cx="8" cy="17" r="2.2" /></svg>
          </button>
        </div>
      </div>
      <div className="top-row mid">
        <div className="seg" role="group" aria-label="View">
          <button type="button" aria-pressed={p.view === 'lanes'} onClick={() => p.setView('lanes')}>Lanes</button>
          <button type="button" aria-pressed={p.view === 'timeline'} onClick={() => p.setView('timeline')}>Timeline</button>
        </div>
        <Radar />
        <button type="button" className="btn primary catch" onClick={p.onCatchUp}>Catch me up</button>
      </div>
    </header>
  )
}
