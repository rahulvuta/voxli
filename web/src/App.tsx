import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react'
import { startMic, MicError, IOS, type Mic } from './audio'
import { Composer } from './components/Composer'
import { Conversation } from './components/Conversation'
import { People } from './components/People'
import { Room } from './components/Room'
import { SettingsSheet } from './components/Settings'
import { CatchUpSheet, ShowSheet, SpeakerSheet } from './components/Sheets'
import { Start } from './components/Start'
import { Toasts } from './components/Toasts'
import { TopBar, type MicStatus, type View } from './components/TopBar'
import { Announcer } from './components/ui'
import { C, type Ctx } from './ctx'
import { createMock } from './mock'
import { createLink, type Transport } from './net'
import { look } from './palette'
import type { ClientMessage, TtsVoices } from './protocol'
import { useSettings } from './settings'
import { derive, init, nameOf, reducer, relations, type Suggestion } from './store'
import { fetchVoices, speak as speakAloud, stopSpeaking } from './tts'

const q = new URLSearchParams(location.search)
const MOCK = q.get('mock') === '1'
const uid = () => (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`)

type Sheet = null | { k: 'settings' | 'catchup' } | { k: 'speaker'; skey: string; focus?: string } | { k: 'show'; text: string }

/** Keep the screen on while listening; the lock is released by the browser when the tab is hidden, so re-take it on return. */
function useWakeLock(on: boolean) {
  useEffect(() => {
    if (!on || !navigator.wakeLock) return
    let lock: WakeLockSentinel | null = null
    let dead = false
    const take = () => {
      if (lock || document.visibilityState !== 'visible') return
      navigator.wakeLock.request('screen').then((l) => {
        if (dead) { void l.release(); return }
        lock = l
        l.onrelease = () => { if (lock === l) lock = null }
      }).catch(() => {})
    }
    take()
    document.addEventListener('visibilitychange', take)
    return () => { dead = true; document.removeEventListener('visibilitychange', take); void lock?.release() }
  }, [on])
}

export default function App() {
  const [state, dispatch] = useReducer(reducer, init)
  const [settings, set] = useSettings()
  const [started, setStarted] = useState(MOCK)
  const [mic, setMic] = useState<MicStatus>(MOCK ? 'demo' : 'off')
  const [micError, setMicError] = useState('')
  const [view, setView] = useState<View>('people')
  const [sheet, setSheet] = useState<Sheet>(null)
  const [text, setText] = useState('')
  const [speaking, setSpeaking] = useState(false)
  const [lastSpoken, setLastSpoken] = useState('')
  const [voices, setVoices] = useState<TtsVoices | null | 'loading'>('loading')
  const [preview, setPreview] = useState<string | null>(null)
  const link = useRef<Transport | null>(null)
  const micRef = useRef<Mic | null>(null)
  const voice = useRef(settings.voiceMemory)
  useEffect(() => { voice.current = settings.voiceMemory }, [settings.voiceMemory])
  useWakeLock(started && mic !== 'denied')

  const send = useCallback((m: ClientMessage) => {
    if (!link.current?.send(m)) dispatch({ t: 'notice', msg: 'Not connected yet. Try again in a moment.' })
  }, [])

  // Demo mode: scripted conversation, no mic, no socket.
  useEffect(() => {
    if (!MOCK) return
    const t = createMock(
      { conn: (conn) => dispatch({ t: 'conn', conn }), event: (ev) => dispatch({ t: 'server', ev }) },
      { speed: Number(q.get('speed')) || 1, from: Number(q.get('from')) || 0, mono: q.get('mono') === '1', asr: q.get('asr') === 'local' ? 'local' : 'deepgram', drop: q.get('drop') === '1' },
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
  useEffect(() => () => { link.current?.close(); micRef.current?.stop(); stopSpeaking() }, [])

  const { groups, hidden, sorted } = useMemo(() => derive(state.utts), [state.utts])
  const { interruptedBy, unsure } = useMemo(() => relations(state.utts, state.ann, sorted), [state.utts, state.ann, sorted])
  const hasDirection = useMemo(() => Object.values(state.speakers).some((s) => s.epoch === state.epoch && s.id !== 'YOU' && s.direction_deg != null), [state.speakers, state.epoch])
  const ctx: Ctx = useMemo(() => ({
    state, settings, groups, hidden, sorted, interruptedBy, unsure, hasDirection,
    look: (k) => look(state.speakers[k], nameOf(state.speakers[k]), settings.palette === 'mono'),
    name: (k) => nameOf(state.speakers[k]),
    jump: (k) => {
      // The newest match is the one on top (a sheet is rendered after the captions behind it).
      const el = [...document.querySelectorAll<HTMLElement>(`[data-u="${CSS.escape(k)}"]`)].pop()
      if (!el) { const u = state.utts[k]; if (u) setSheet({ k: 'speaker', skey: u.skey, focus: k }); return }
      el.scrollIntoView({ block: 'center', behavior: settings.reduceMotion ? 'auto' : 'smooth' })
      el.classList.add('flash')
      window.setTimeout(() => el.classList.remove('flash'), 1600)
    },
    openSpeaker: (skey, focus) => setSheet({ k: 'speaker', skey, focus }),
  }), [state, settings, groups, hidden, sorted, interruptedBy, unsure, hasDirection])

  const dismissSuggestion = useCallback((id: string) => dispatch({ t: 'dismissSuggestion', id }), [])
  const clearNotice = useCallback(() => dispatch({ t: 'notice', msg: null }), [])
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
  const fallback = () => dispatch({ t: 'notice', msg: 'Using phone voice' })
  const speak = (t: string) => {
    const id = uid()
    setLastSpoken(t)
    setSpeaking(true)
    if (IOS) micRef.current?.hold() // else iOS routes the reply to the earpiece at call volume
    void speakAloud(t, settings.voice, { onStart: () => send({ type: 'tts_start', id, text: t }), onEnd: () => send({ type: 'tts_end', id }), onFallback: fallback })
      .then(() => { setSpeaking(false); if (IOS) void micRef.current?.release() })
  }
  const previewVoice = (id: string) => {
    if (preview === id) { stopSpeaking(); return }
    setPreview(id)
    if (IOS) micRef.current?.hold()
    void speakAloud('Hi, this is how I will sound when you type to speak.', id, { onFallback: fallback })
      .then(() => { setPreview((p) => (p === id ? null : p)); if (IOS) void micRef.current?.release() })
  }
  const openSettings = () => {
    setSheet({ k: 'settings' })
    if (voices === 'loading' || voices === null) { setVoices('loading'); void fetchVoices().then(setVoices) }
  }

  const shown: View = view === 'room' && !hasDirection ? 'people' : view
  return (
    <C.Provider value={ctx}>
      {!started ? <Start onStart={begin} /> : (
        <div className="app">
          <TopBar view={shown} setView={setView} mic={mic} onCatchUp={() => setSheet({ k: 'catchup' })} onSettings={openSettings} />
          <main className="stage">
            {shown === 'people' ? <People /> : shown === 'conversation' ? <Conversation /> : <Room />}
            <Toasts mic={mic} micError={micError} started={started} onRetry={begin} onRespond={respond} onDismissSuggestion={dismissSuggestion} onClearNotice={clearNotice} />
          </main>
          <Composer phrases={settings.phrases} setPhrases={(phrases) => set({ phrases })} speaking={speaking} speak={speak} stop={stopSpeaking}
            suggest={() => { dispatch({ t: 'repliesStart' }); send({ type: 'suggest_replies' }) }} onShow={(t) => setSheet({ k: 'show', text: t })} lastSpoken={lastSpoken} text={text} setText={setText} />
          <Announcer />
          {sheet?.k === 'settings' && <SettingsSheet s={settings} set={set} voices={voices} preview={preview} onPreview={previewVoice} onClose={() => { stopSpeaking(); setSheet(null) }}
            onVoiceMemory={(v) => { set({ voiceMemory: v }); send({ type: 'set_voice_memory', enabled: v }) }}
            onForget={() => { send({ type: 'forget_all' }); dispatch({ t: 'clearAll' }); set({ voiceMemory: false, phrases: [] }) }} />}
          {sheet?.k === 'catchup' && <CatchUpSheet onClose={() => { dispatch({ t: 'catchUpClose' }); setSheet(null) }} onAsk={(seconds) => { dispatch({ t: 'catchUpStart' }); send({ type: 'catch_up', seconds }) }} />}
          {sheet?.k === 'speaker' && <SpeakerSheet key={sheet.skey + (sheet.focus ?? '')} skey={sheet.skey} focus={sheet.focus} onClose={() => setSheet(null)} onRename={rename}
            onMerge={(from, into) => send({ type: 'merge_speakers', from_id: state.speakers[from].id, into_id: state.speakers[into].id })} />}
          {sheet?.k === 'show' && <ShowSheet text={sheet.text} onClose={() => setSheet(null)} />}
        </div>
      )}
    </C.Provider>
  )
}
