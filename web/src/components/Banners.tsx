import { useEffect, useState } from 'react'
import { useCtx } from '../ctx'
import type { Suggestion } from '../store'
import type { MicStatus } from './Header'

export function Banners({ mic, micError, onRetry, started, onDismiss }: { mic: MicStatus; micError: string; onRetry(): void; started: boolean; onDismiss(): void }) {
  const { state } = useCtx()
  const [hideMono, setHideMono] = useState(false)
  const items: React.ReactNode[] = []
  if (mic === 'denied') items.push(<div key="d" className="banner bad" role="alert"><p><b>Microphone unavailable.</b> {micError} Allow microphone access for this page, then try again.</p><button className="btn" onClick={onRetry}>Try again</button></div>)
  if (started && mic !== 'demo' && mic !== 'denied' && state.conn === 'reconnecting') items.push(<div key="r" className="banner warn" role="status"><p><b>Reconnecting…</b> Your captions so far are kept. Anything said during a short gap is sent when we are back.</p></div>)
  if (started && mic === 'demo' && state.conn === 'reconnecting') items.push(<div key="r" className="banner warn" role="status"><p><b>Reconnecting…</b> Your captions so far are kept.</p></div>)
  if (state.conn === 'open' && state.asr === 'local') items.push(<div key="l" className="banner info" role="status"><p><b>Offline captions.</b> Working without the internet, so words may arrive slower and less accurately.</p></div>)
  if (state.conn === 'open' && state.asr === 'reconnecting') items.push(<div key="a" className="banner warn" role="status"><p><b>Switching caption engine…</b> {state.message ?? ''}</p></div>)
  if (state.conn === 'open' && state.stereo === false && !hideMono)
    items.push(<div key="m" className="banner info" role="status"><p><b>No direction.</b> This phone's mic is mono, so the ring can't place voices. Captions still work.</p><button className="btn ghost" onClick={() => setHideMono(true)}>Dismiss</button></div>)
  if (state.conn === 'open' && state.busyRoom) items.push(<div key="b" className="banner info" role="status"><p><b>Busy room.</b> Lots of background talking, so people speaking at once won't be split apart right now. Captions continue.</p></div>)
  if (state.notice) items.push(<div key="e" className="banner warn" role="status"><p>{state.notice}</p><button className="btn ghost" onClick={onDismiss}>Dismiss</button></div>)
  return items.length ? <div className="banners">{items}</div> : null
}

export function SuggestionTray({ onRespond, onDismiss }: { onRespond(s: Suggestion, accept: boolean): void; onDismiss(id: string): void }) {
  const { state, name } = useCtx()
  // Auto-applied names are informational: fade them out after a while so they don't eat caption space.
  useEffect(() => {
    const ts = state.suggestions.filter((s) => s.auto).map((s) => window.setTimeout(() => onDismiss(s.id), 12000))
    return () => ts.forEach(clearTimeout)
  }, [state.suggestions, onDismiss])
  const list = state.suggestions.filter((s) => state.speakers[s.skey]).sort((a, b) => Number(a.auto) - Number(b.auto))
  if (!list.length) return null
  return (
    <div className="tray" role="region" aria-label="Name suggestions">
      {list.slice(0, 1).map((s) => {
        const spk = state.speakers[s.skey]
        return (
          <div key={s.id} className="sugchip" role="group" aria-label="Name suggestion">
            {s.auto ? <p>Named <b>{s.name}</b> (said “I’m {s.name}”)</p> : <p>Is <b>{spk.name && spk.name_source === 'user' ? spk.name : spk.label}</b> <b>{s.name}</b>?</p>}
            <div className="row">
              {s.auto
                ? <><button className="btn" onClick={() => onRespond(s, false)}>Undo</button><button className="btn ghost" onClick={() => onRespond(s, true)}>Keep</button></>
                : <><button className="btn primary" onClick={() => onRespond(s, true)}>Yes</button><button className="btn" onClick={() => onRespond(s, false)}>No</button></>}
            </div>
            <span className="sr-only">{name(s.skey)}</span>
          </div>
        )
      })}
      {list.length > 1 && <p className="muted small">{list.length - 1} more waiting</p>}
    </div>
  )
}

export function Start({ onStart, error }: { onStart(): void; error: string }) {
  return (
    <main className="start">
      <h1 className="brand big">Voxli</h1>
      <p className="lead">Live captions for group conversations, with a separate lane for each person.</p>
      <ul className="how">
        <li>Put your phone where you can see everyone.</li>
        <li>Captions show who said what, and who is replying to whom.</li>
        <li>Type to speak when you want to join in.</li>
      </ul>
      <button className="btn primary huge" onClick={onStart} autoFocus>Start listening</button>
      {error && <p className="banner bad" role="alert">{error}</p>}
      <p className="muted small">Your microphone audio is sent to the Voxli server to make captions, and may go to a speech-recognition service. Nothing is saved unless you turn on voice memory in Settings.</p>
      <p className="small"><a href="?mock=1">Try the demo without a microphone</a></p>
    </main>
  )
}
