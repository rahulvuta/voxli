// ?mock=1 — a scripted fake conversation so the UI can be built and demoed without the backend.
// Extra switches: &speed=2  &mono=1 (one mic channel)  &asr=local  &drop=1 (connection drops at ~30 s)
import type { ClientMessage, ServerEvent, Speaker, Utterance, Word } from './protocol'
import type { Transport } from './net'
import type { Conn } from './store'

interface Opts { speed: number; mono: boolean; asr: 'deepgram' | 'local'; drop: boolean }
interface H { conn(c: Conn): void; event(e: ServerEvent): void }

const NAMES: Record<string, Partial<Speaker>> = {
  S1: { label: 'Speaker A', color_index: 0, direction_deg: -55 },
  S2: { label: 'Speaker B', color_index: 1, direction_deg: 5 },
  S3: { label: 'Speaker C', color_index: 2, direction_deg: 55 },
  S4: { label: 'Speaker D', color_index: 3, direction_deg: null },
  YOU: { label: 'You', color_index: 7, direction_deg: null },
}
const SUMMARY: Record<string, string> = {
  S1: 'Wants to start with the budget; later agrees on the cheaper catering.',
  S2: 'Asks about the finance numbers and which venue called.',
  S3: 'Says the venue on Main Street raised its price.',
  S4: 'Thinks the plan is still affordable if catering is cut.',
}

export function createMock(h: H, o: Opts): Transport {
  const timers: number[] = []
  const t0 = performance.now()
  const clock = () => ((performance.now() - t0) / 1000) * o.speed
  const at = (t: number, fn: () => void) => timers.push(window.setTimeout(fn, Math.max(0, (t * 1000) / o.speed - (performance.now() - t0))))
  const spk: Record<string, Speaker> = {}
  const finals: { id: string; speaker_id: string; end: number }[] = []
  let youN = 0

  const upsert = (id: string, patch: Partial<Speaker> = {}) => {
    const base: Speaker = { id, label: 'Speaker', name: null, name_source: null, color_index: 0, direction_deg: null, active: false }
    spk[id] = { ...base, ...NAMES[id], ...spk[id], ...patch }
    h.event({ type: 'speaker', speaker: spk[id] })
  }
  const announce = () => {
    h.event({ type: 'status', asr: o.asr, stereo: !o.mono })
    for (const id of Object.keys(spk)) upsert(id, o.mono ? { direction_deg: null } : {})
  }

  /** Streams `text` word by word (interim), then finalises. Times are session seconds. */
  const say = (t: number, uid: string, speaker: string, text: string, dur: number, x: Partial<Utterance> = {}, low: number[] = []) => {
    const ws = text.split(' ')
    const words: Word[] = ws.map((w, i) => ({ w, start: t + (dur * i) / ws.length, end: t + (dur * (i + 1)) / ws.length, conf: low.includes(i) ? 0.42 : 0.96 }))
    const mk = (n: number, fin: boolean): Utterance => ({
      id: uid, speaker_id: speaker, speaker_confidence: 0.92, speaker_uncertain: false, text: ws.slice(0, n).join(' '),
      words: fin ? words : [], start: t, end: t + (dur * n) / ws.length, is_final: fin, overlap_group: null, source: 'live',
      direction_deg: o.mono ? null : (NAMES[speaker]?.direction_deg ?? null), ...x,
    })
    at(t, () => upsert(speaker, { active: true }))
    const step = Math.max(1, Math.ceil(ws.length / 6))
    for (let n = step; n < ws.length; n += step) at(t + (dur * n) / ws.length, () => h.event({ type: 'utterance', utterance: mk(n, false) }))
    at(t + dur, () => {
      h.event({ type: 'utterance', utterance: mk(ws.length, true) })
      finals.push({ id: uid, speaker_id: speaker, end: t + dur })
    })
    at(t + dur + 1.2, () => upsert(speaker, { active: false }))
  }
  const ann = (t: number, id: string, reply_to: string | null, interrupts: string | null = null, incomplete = false) =>
    at(t, () => h.event({ type: 'annotation', utterance_id: id, reply_to, interrupts, thread_id: null, incomplete }))

  const script = () => {
    announce()
    // 1. Self-introduction -> name applied automatically (with Undo).
    say(1, 'u1', 'S1', "Hi everyone, I'm Maya. Shall we start with the budget?", 3.8)
    at(4.9, () => {
      upsert('S1', { name: 'Maya', name_source: 'auto' })
      h.event({ type: 'name_suggestion', id: 'n1', speaker_id: 'S1', name: 'Maya', evidence_utterance_id: 'u1', kind: 'self_intro', auto_applied: true })
    })
    // 2. Reply
    say(6.5, 'u2', 'S2', 'Sure. Did you get the numbers from finance?', 3, {}, [4])
    ann(9.6, 'u2', 'u1')
    // 3. Interruption: C cuts in on A.
    say(11, 'u3', 'S1', 'Yes, they came in this morning and the total is', 3.4)
    say(13.4, 'u4', 'S3', 'Sorry to cut in, but the venue just called.', 2.8)
    ann(14.5, 'u3', null, null, true)
    ann(16.3, 'u4', 'u2', 'u3')
    // 4. Overlap: B and C talk at the same time (two separated streams).
    say(19, 'u5', 'S2', 'Wait, which venue? Is it the one downtown?', 3.6, { overlap_group: 'g1', source: 'separated' })
    say(19.6, 'u6', 'S3', 'The one on Main Street, they raised the price again.', 3.4, { overlap_group: 'g1', source: 'separated' }, [8])
    ann(23.3, 'u5', 'u4')
    // 5. Uncertain speaker (new voice, short evidence).
    say(25, 'u7', 'S4', 'I think we can still afford it if we cut the catering.', 3.6, { speaker_uncertain: true, speaker_confidence: 0.41 }, [1, 8])
    ann(28.7, 'u7', 'u6')
    // 6. Introduction by someone else -> suggestion chip needing confirmation.
    say(31, 'u8', 'S2', 'Oh, and this is my friend Priya, she helps with events.', 3.4)
    at(34.6, () => h.event({ type: 'name_suggestion', id: 'n2', speaker_id: 'S4', name: 'Priya', evidence_utterance_id: 'u8', kind: 'introduced', auto_applied: false }))
    say(36, 'u9', 'S4', 'Thanks for having me.', 1.6)
    ann(37.7, 'u9', 'u8')
    say(39.5, 'u10', 'S1', "That works for me. Let's go with the cheaper catering.", 3.4)
    ann(43, 'u10', 'u7')

    if (o.drop) {
      at(30, () => h.conn('reconnecting'))
      at(37, () => { h.conn('open'); announce() })
    }
  }
  at(0.3, () => { h.conn('open'); script() })

  return {
    audio() {},
    setChannels() {},
    close() { timers.forEach(clearTimeout) },
    send(m: ClientMessage) {
      switch (m.type) {
        case 'tts_start': {
          const t = clock()
          at(t + 0.1, () => {
            upsert('YOU')
            h.event({ type: 'utterance', utterance: { id: `y${++youN}`, speaker_id: 'YOU', speaker_confidence: 1, speaker_uncertain: false, text: m.text, words: [], start: t, end: t + 1.5, is_final: true, overlap_group: null, source: 'you', direction_deg: null } })
          })
          break
        }
        case 'suggest_replies':
          at(clock() + 0.7, () => h.event({ type: 'reply_suggestions', options: ['Sounds good to me', 'Can you say that again?', "I'm not sure yet"] }))
          break
        case 'catch_up': {
          const now = clock()
          const by = new Map<string, string[]>()
          for (const f of finals) if (f.end >= now - m.seconds) by.set(f.speaker_id, [...(by.get(f.speaker_id) ?? []), f.id])
          at(now + 0.8, () => h.event({ type: 'catch_up', items: [...by].map(([speaker_id, utterance_ids]) => ({ speaker_id, utterance_ids, summary: SUMMARY[speaker_id] ?? '' })) }))
          break
        }
        case 'rename_speaker': upsert(m.speaker_id, { name: m.name, name_source: 'user' }); break
        case 'merge_speakers': delete spk[m.from_id]; h.event({ type: 'speaker_removed', id: m.from_id, merged_into: m.into_id }); break
        case 'name_suggestion_response': {
          const s = m.suggestion_id === 'n1' ? 'S1' : 'S4'
          const name = m.suggestion_id === 'n1' ? 'Maya' : 'Priya'
          upsert(s, m.accept ? { name, name_source: 'user' } : { name: null, name_source: null })
          break
        }
        default: break
      }
      return true
    },
  }
}
