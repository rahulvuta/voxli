import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react'
import { startMic, MicError, type Mic } from './audio'
import { Banners, Start, SuggestionTray } from './components/Banners'
import { Announcer, Lanes, Timeline } from './components/Captions'
import { Header, type MicStatus, type View } from './components/Header'
import { ReplyBar } from './components/ReplyBar'
import { CatchUpSheet, SettingsSheet, ShowSheet, SpeakerSheet } from './components/Sheets'
import { C, type Ctx } from './ctx'
import { createMock } from './mock'
import { createLink, type Transport } from './net'
import { look } from './palette'
import type { ClientMessage } from './protocol'
import { useSettings } from './settings'
import { derive, init, nameOf, reducer, type Suggestion } from './store'

const q = new URLSearchParams(location.search)
const MOCK = q.get('mock') === '1'
const uid = () => (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`)

export default function App() {
  const [state, dispatch] = useReducer(reducer, init)
  const [settings, set] = useSettings()
  const [started, setStarted] = useState(MOCK)
  const [mic, setMic] = useState<MicStatus>(MOCK ? 'demo' : 'off')
  const [micError, setMicError] = useState('')
  const [view, setView] = useState<View>('lanes')
  const [sheet, setSheet] = useState<null | { k: 'settings' | 'catchup' } | { k: 'speaker'; skey: string } | { k: 'show'; text: string }>(null)
  const [text, setText] = useState('')
  const [speaking, setSpeaking] = useState<string | null>(null)
  const [lastSpoken, setLastSpoken] = useState('')
  const link = useRef<Transport | null>(null)
  const micRef = useRef<Mic | null>(null)
  const voice = useRef(settings.voiceMemory)
  useEffect(() => { voice.current = settings.voiceMemory }, [settings.voiceMemory])

  const send = useCallback((m: ClientMessage) => {
    if (!link.current?.send(m)) dispatch({ t: 'notice', msg: 'Not connected yet. Try again in a moment.' })
  }, [])

  // Demo mode: scripted conversation, no mic, no socket.
  useEffect(() => {
    if (!MOCK) return
    const t = createMock(
      { conn: (conn) => dispatch({ t: 'conn', conn }), event: (ev) => dispatch({ t: 'server', ev }) },
      { speed: Number(q.get('speed')) || 1, mono: q.get('mono') === '1', asr: q.get('asr') === 'local' ? 'local' : 'deepgram', drop: q.get('drop') === '1' },
    )
    link.current = t
    return () => t.close()
  }, [])

  const begin = async () => {
    link.current?.close()
    micRef.current?.stop()
    setMicError('')
    const l = createLink({
      conn: (conn) => dispatch({ t: 'conn', conn }),
      event: (ev) => dispatch({ t: 'server', ev }),
      onOpen: () => (voice.current ? [{ type: 'set_voice_memory', enabled: true }] : []),
    })
    link.current = l
    setStarted(true)
    try {
      micRef.current = await startMic({ onFrame: (b) => l.audio(b), onChannels: (c) => l.setChannels(c), onState: (s) => setMic(s) })
      setMic('on')
    } catch (e) {
      l.close()
      link.current = null
      setMic('denied')
      setMicError(e instanceof MicError ? e.message : 'Could not start the microphone.')
    }
  }
  useEffect(() => () => { link.current?.close(); micRef.current?.stop() }, [])

  const { groups, hidden, sorted } = useMemo(() => derive(state.utts), [state.utts])
  const ctx: Ctx = useMemo(() => ({
    state, settings, groups, hidden, sorted,
    look: (k) => look(state.speakers[k], settings.palette === 'mono'),
    name: (k) => nameOf(state.speakers[k]),
    jump: (k) => {
      const el = document.getElementById(`u-${k}`)
      if (!el) return
      el.scrollIntoView({ block: 'center', behavior: settings.reduceMotion ? 'auto' : 'smooth' })
      el.classList.add('flash')
      window.setTimeout(() => el.classList.remove('flash'), 1600)
    },
    openSpeaker: (skey) => setSheet({ k: 'speaker', skey }),
  }), [state, settings, groups, hidden, sorted])

  const dismissSuggestion = useCallback((id: string) => dispatch({ t: 'dismissSuggestion', id }), [])
  const respond = (s: Suggestion, accept: boolean) => {
    send({ type: 'name_suggestion_response', suggestion_id: s.id, accept })
    if (!s.auto && accept) dispatch({ t: 'speaker', speaker: { ...state.speakers[s.skey], name: s.name, name_source: 'user' } })
    dispatch({ t: 'dismissSuggestion', id: s.id })
  }
  const rename = (skey: string, name: string) => {
    const s = state.speakers[skey]
    send({ type: 'rename_speaker', speaker_id: s.id, name })
    dispatch({ t: 'speaker', speaker: { ...s, name, name_source: 'user' } })
  }
  const speak = (t: string) => {
    const id = uid()
    send({ type: 'tts_start', id, text: t })
    setLastSpoken(t)
    if (!('speechSynthesis' in window)) { send({ type: 'tts_end', id }); return }
    speechSynthesis.cancel()
    const u = new SpeechSynthesisUtterance(t)
    u.lang = navigator.language
    const done = () => { send({ type: 'tts_end', id }); setSpeaking((c) => (c === id ? null : c)) }
    u.onend = done
    u.onerror = done
    setSpeaking(id)
    speechSynthesis.speak(u)
  }

  const micDetail = { off: 'Microphone is off', on: 'Microphone is on and listening', paused: 'Microphone is paused', denied: 'Microphone is blocked', demo: 'Demo mode, microphone not used' }[mic]
  return (
    <C.Provider value={ctx}>
      {!started ? <Start onStart={begin} error="" /> : (
        <div className="app">
          <Header view={view} setView={setView} mic={mic} micDetail={micDetail} onCatchUp={() => setSheet({ k: 'catchup' })} onSettings={() => setSheet({ k: 'settings' })} />
          <Banners mic={mic} micError={micError} started={started} onRetry={begin} onDismiss={() => dispatch({ t: 'notice', msg: null })} />
          <SuggestionTray onRespond={respond} onDismiss={dismissSuggestion} />
          <main className="stage">{view === 'lanes' ? <Lanes /> : <Timeline />}</main>
          <ReplyBar phrases={settings.phrases} setPhrases={(phrases) => set({ phrases })} speaking={speaking !== null} speak={(t) => { speak(t) }} stop={() => speechSynthesis.cancel()}
            suggest={() => { dispatch({ t: 'repliesStart' }); send({ type: 'suggest_replies' }) }} onShow={(t) => setSheet({ k: 'show', text: t })} lastSpoken={lastSpoken} text={text} setText={setText} />
          <Announcer />
          {sheet?.k === 'settings' && <SettingsSheet s={settings} set={set} onClose={() => setSheet(null)}
            onVoice={(v) => { set({ voiceMemory: v }); send({ type: 'set_voice_memory', enabled: v }) }}
            onForget={() => { send({ type: 'forget_all' }); dispatch({ t: 'clearAll' }); set({ voiceMemory: false, phrases: [] }) }} />}
          {sheet?.k === 'catchup' && <CatchUpSheet onClose={() => { dispatch({ t: 'catchUpClose' }); setSheet(null) }} onAsk={(seconds) => { dispatch({ t: 'catchUpStart' }); send({ type: 'catch_up', seconds }) }} />}
          {sheet?.k === 'speaker' && <SpeakerSheet skey={sheet.skey} onClose={() => setSheet(null)} onRename={rename}
            onMerge={(from, into) => send({ type: 'merge_speakers', from_id: state.speakers[from].id, into_id: state.speakers[into].id })} />}
          {sheet?.k === 'show' && <ShowSheet text={sheet.text} onClose={() => setSheet(null)} />}
        </div>
      )}
    </C.Provider>
  )
}
