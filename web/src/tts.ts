// Voice output: server MP3 (POST /api/tts) first, the phone's own speechSynthesis as the fallback.
import type { TtsVoices } from './protocol'

export async function fetchVoices(): Promise<TtsVoices | null> {
  try {
    const r = await fetch('/api/tts/voices')
    if (!r.ok) return null
    const j = (await r.json()) as TtsVoices
    return Array.isArray(j.voices) && j.voices.length ? j : null
  } catch { return null }
}

// A silent clip played inside the tap unlocks the shared <audio> element on iOS, so the real MP3 can play after the fetch.
const SILENT = 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA='
let el: HTMLAudioElement | null = null
let current: (() => void) | null = null

export const stopSpeaking = () => current?.()

function phoneVoice() {
  const lang = navigator.language.toLowerCase()
  const vs = speechSynthesis.getVoices().filter((v) => v.lang.toLowerCase().startsWith(lang.split('-')[0]))
  return vs.find((v) => /premium|enhanced|natural|google/i.test(v.name) && v.lang.toLowerCase() === lang) ?? vs.find((v) => /premium|enhanced|natural|google/i.test(v.name))
}

interface Hooks {
  onStart?(): void // right before sound starts (send tts_start)
  onEnd?(): void // sound finished or was stopped, only if onStart ran (send tts_end)
  onFallback?(): void // server voice failed; the phone voice is used
}

/** Resolves when this utterance is over (finished, stopped or replaced). */
export function speak(text: string, voice: string | null, h: Hooks = {}): Promise<void> {
  stopSpeaking()
  const a = (el ??= new Audio())
  return new Promise((resolve) => {
    let over = false, started = false, url = ''
    const ac = new AbortController()
    const timer = window.setTimeout(() => ac.abort(), 6500)
    const finish = () => {
      if (over) return
      over = true
      window.clearTimeout(timer)
      ac.abort()
      a.onended = a.onerror = null
      a.pause()
      if (url) URL.revokeObjectURL(url)
      if ('speechSynthesis' in window) speechSynthesis.cancel()
      if (current === finish) current = null
      if (started) h.onEnd?.()
      resolve()
    }
    current = finish
    const begin = () => { if (!started) { started = true; h.onStart?.() } }
    const phone = () => {
      if (over) return
      h.onFallback?.()
      begin()
      if (!('speechSynthesis' in window)) { finish(); return }
      const u = new SpeechSynthesisUtterance(text)
      u.lang = navigator.language
      const v = phoneVoice()
      if (v) u.voice = v
      u.onend = u.onerror = finish
      speechSynthesis.speak(u)
    }
    a.src = SILENT
    void a.play().catch(() => {})
    fetch('/api/tts', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text, voice }), signal: ac.signal })
      .then((r) => { if (!r.ok) throw new Error(String(r.status)); return r.blob() })
      .then((b) => {
        if (over) return
        url = URL.createObjectURL(b)
        a.onended = finish
        a.onerror = phone
        a.src = url
        begin()
        return a.play()
      })
      .catch(phone)
  })
}
