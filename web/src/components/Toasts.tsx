import { AudioLines, Check, CircleAlert, Info, Users, WifiOff, X, type LucideIcon } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useCtx } from '../ctx'
import type { Suggestion } from '../store'
import type { MicStatus } from './TopBar'

interface Item { key: string; icon: LucideIcon; text: React.ReactNode; actions?: React.ReactNode; alert?: boolean; dismissible?: boolean; tone?: 'warn' | 'bad' }

/** Small stack above the composer. Things that need a tap come first; info toasts can be dismissed and stay away until the condition returns. */
export function Toasts({ mic, micError, started, onRetry, onRespond, onDismissSuggestion, onClearNotice }: { mic: MicStatus; micError: string; started: boolean; onRetry(): void; onRespond(s: Suggestion, accept: boolean): void; onDismissSuggestion(id: string): void; onClearNotice(): void }) {
  const { state } = useCtx()
  const [gone, setGone] = useState<string[]>([])
  // Auto-applied names are informational: fade them out, and short notices clear themselves.
  useEffect(() => {
    const ts = state.suggestions.filter((s) => s.auto).map((s) => window.setTimeout(() => onDismissSuggestion(s.id), 12000))
    return () => ts.forEach(clearTimeout)
  }, [state.suggestions, onDismissSuggestion])
  useEffect(() => {
    if (!state.notice) return
    const t = window.setTimeout(onClearNotice, 7000)
    return () => clearTimeout(t)
  }, [state.notice, onClearNotice])

  const items: Item[] = []
  const open = state.conn === 'open'
  const btn = (label: string, fn: () => void, primary = false) => <button type="button" className={`tbtn${primary ? ' primary' : ''}`} onClick={fn}>{label}</button>
  if (mic === 'denied') items.push({ key: 'mic', icon: CircleAlert, tone: 'bad', alert: true, text: <><b>Microphone unavailable.</b> {micError} Allow microphone access for this page, then try again.</>, actions: btn('Try again', onRetry, true) })
  // Short-lived notices come before name suggestions so they are not missed; they clear themselves.
  if (state.notice) items.push({ key: `note-${state.notice}`, icon: Check, dismissible: true, text: state.notice })
  const sg = state.suggestions.filter((s) => state.speakers[s.skey]).sort((a, b) => Number(a.auto) - Number(b.auto))[0]
  if (sg) {
    const spk = state.speakers[sg.skey]
    items.push({
      key: `s${sg.id}`, icon: Users,
      text: sg.auto ? <>Named <b>{sg.name}</b> because they said “I’m {sg.name}”</> : <>Is <b>{spk.name && spk.name_source === 'user' ? spk.name : spk.label}</b> {sg.name}?{state.suggestions.length > 1 && <span className="muted"> ({state.suggestions.length - 1} more)</span>}</>,
      actions: sg.auto ? <>{btn('Undo', () => onRespond(sg, false))}{btn('Keep', () => onRespond(sg, true), true)}</> : <>{btn('No', () => onRespond(sg, false))}{btn('Yes', () => onRespond(sg, true), true)}</>,
    })
  }
  if (started && state.conn === 'reconnecting') items.push({ key: 'rc', icon: WifiOff, tone: 'warn', text: <><b>Reconnecting…</b> Your captions so far are kept{mic === 'demo' ? '.' : '. Anything said during a short gap is sent when we are back.'}</> })
  if (open && state.asr === 'local') items.push({ key: 'local', icon: WifiOff, dismissible: true, text: <><b>Offline captions.</b> Words may arrive slower and less accurately.</> })
  if (open && state.asr === 'reconnecting') items.push({ key: 'eng', icon: Info, tone: 'warn', text: <><b>Switching caption engine…</b> {state.message ?? ''}</> })
  if (open && state.stereo === false) items.push({ key: 'mono', icon: AudioLines, dismissible: true, text: <><b>No direction.</b> This mic is mono, so the Room map is off.</> })
  if (open && state.busyRoom) items.push({ key: 'busy', icon: Users, dismissible: true, text: <><b>Busy room.</b> Overlapping speech isn’t split apart right now.</> })

  const keys = items.map((i) => i.key)
  // A dismissed toast stays away only while its condition lasts (state adjusted during render, per the React docs).
  if (gone.some((g) => !keys.includes(g))) setGone(gone.filter((g) => keys.includes(g)))
  const shown = items.filter((i) => !gone.includes(i.key)).slice(0, 1)
  if (!shown.length) return null
  return (
    <div className="toasts">
      {shown.map((i) => (
        <div key={i.key} className={`toast${i.tone ? ` ${i.tone}` : ''}`} role={i.alert ? 'alert' : 'status'}>
          <i.icon size={20} aria-hidden="true" />
          <p>{i.text}</p>
          {i.actions && <div className="tact">{i.actions}</div>}
          {i.dismissible && <button type="button" className="ib sm" aria-label="Dismiss" onClick={() => { setGone([...gone, i.key]); if (i.key.startsWith('note-')) onClearNotice() }}><X size={18} aria-hidden="true" /></button>}
        </div>
      ))}
    </div>
  )
}
