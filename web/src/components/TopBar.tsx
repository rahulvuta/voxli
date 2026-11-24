import { History, LayoutGrid, MessagesSquare, Radar, Settings2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useCtx } from '../ctx'
import { Avatar, IconBtn } from './ui'

export type MicStatus = 'off' | 'on' | 'paused' | 'denied' | 'demo'
export type View = 'people' | 'conversation' | 'room'

function Mark() {
  return (
    <svg className="mark" width="22" height="22" viewBox="0 0 32 32" aria-hidden="true">
      <path d="M6 7.5A3.5 3.5 0 0 1 9.5 4h13A3.5 3.5 0 0 1 26 7.5v9a3.5 3.5 0 0 1-3.5 3.5H15l-5.2 4.4a.6.6 0 0 1-1-.5V20h-.3A3.5 3.5 0 0 1 6 16.5z" fill="var(--accent)" />
      <path d="M11 10h10M11 14h6" stroke="var(--on-accent)" strokeWidth="2" strokeLinecap="round" />
    </svg>
  )
}

/** One dot for connection + caption engine; the shape changes too so colour is not the only cue. Tap for details. */
function Status({ mic }: { mic: MicStatus }) {
  const { state, hasDirection } = useCtx()
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const out = (e: PointerEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false) }
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('pointerdown', out)
    document.addEventListener('keydown', esc)
    return () => { document.removeEventListener('pointerdown', out); document.removeEventListener('keydown', esc) }
  }, [open])
  const down = state.conn === 'reconnecting' || state.conn === 'connecting' || state.asr === 'reconnecting'
  const [tone, shape, label, detail] =
    mic === 'denied' ? ['bad', 'square', 'Microphone blocked', 'Captions cannot start until the microphone is allowed.']
    : down ? ['warn', 'ring', 'Reconnecting', 'Captions so far are kept. Reconnecting to the Voxli server.']
    : state.asr === 'local' ? ['warn', 'square', 'On-device captions', 'Working without the internet. Words may arrive slower and less accurately.']
    : state.asr === 'offline' ? ['bad', 'square', 'Captions offline', state.message ?? 'No caption engine is available right now.']
    : state.asr === 'deepgram' ? ['ok', 'dot', 'Live captions', 'Speech is being captioned by the cloud engine.']
    : ['warn', 'ring', 'Connecting', 'Waiting for the first connection.']
  const micText = { off: 'off', on: 'on and listening', paused: 'paused', denied: 'blocked', demo: 'not used (demo mode)' }[mic]
  return (
    <div className="status" ref={box}>
      <button type="button" className={`sdot ${tone}`} onClick={() => setOpen(!open)} aria-expanded={open} aria-label={`Status: ${label}. Show details`}>
        <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
          {shape === 'dot' && <circle cx="7" cy="7" r="5.5" fill="currentColor" />}
          {shape === 'square' && <rect x="2" y="2" width="10" height="10" rx="2" fill="currentColor" />}
          {shape === 'ring' && <circle cx="7" cy="7" r="4.6" fill="none" stroke="currentColor" strokeWidth="2.4" strokeDasharray="4.4 2.4" />}
        </svg>
      </button>
      {open && (
        <div className="pop" role="status">
          <p className="pop-title"><b>{label}</b></p>
          <p>{detail}</p>
          <dl>
            <dt>Microphone</dt><dd>{micText}</dd>
            <dt>Direction</dt><dd>{state.stereo === null ? 'checking' : hasDirection ? 'stereo, people are placed in the Room view' : state.stereo ? 'stereo, no one placed yet' : 'mono mic, no direction'}</dd>
          </dl>
        </div>
      )}
    </div>
  )
}

export function TopBar(p: { view: View; setView(v: View): void; mic: MicStatus; onCatchUp(): void; onSettings(): void }) {
  const { state, hasDirection, name, openSpeaker } = useCtx()
  const people = Object.values(state.speakers).filter((s) => s.epoch === state.epoch && s.id !== 'YOU')
  const views = [['people', 'People', LayoutGrid], ['conversation', 'Conversation', MessagesSquare], ...(hasDirection ? [['room', 'Room', Radar] as const] : [])] as const
  return (
    <header className="top">
      <h1 className="brand"><Mark />Voxli</h1>
      <Status mic={p.mic} />
      <div className="strip" role="group" aria-label="People in the conversation">
        {people.map((s) => <button key={s.key} type="button" className={s.active ? 'on' : ''} onClick={() => openSpeaker(s.key)} aria-label={`${name(s.key)}${s.active ? ', speaking' : ''}. Open history`}><Avatar skey={s.key} size={30} /></button>)}
      </div>
      <div className="seg" role="group" aria-label="Caption view">
        {views.map(([v, label, Icon]) => <IconBtn key={v} icon={Icon} label={`${label} view`} pressed={p.view === v} onClick={() => p.setView(v)} size={20} />)}
      </div>
      <div className="acts">
        <button type="button" className="ib catch" onClick={p.onCatchUp} aria-label="Catch me up" title="Catch me up"><History size={22} aria-hidden="true" /><span>Catch me up</span></button>
        <IconBtn icon={Settings2} label="Settings" onClick={p.onSettings} className="top-settings" />
      </div>
    </header>
  )
}
