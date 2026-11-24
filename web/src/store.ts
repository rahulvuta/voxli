import type { ServerEvent, Speaker, Utterance } from './protocol'

// All keys are namespaced by `epoch` (bumped on every reconnect to a new server session) so captions kept
// from an earlier connection never collide with the ids of the new one. "YOU" is shared across epochs.
export type Conn = 'idle' | 'connecting' | 'open' | 'reconnecting'
export interface Spk extends Speaker { key: string; epoch: number }
export interface Utt extends Utterance { key: string; epoch: number; skey: string; gkey: string | null }
export interface Ann { reply_to: string | null; interrupts: string | null; thread_id: string | null; incomplete: boolean }
export interface Suggestion { id: string; skey: string; name: string; kind: 'self_intro' | 'introduced' | 'correction'; auto: boolean }
export interface CatchUpItem { skey: string; ukeys: string[]; summary: string }

export interface State {
  epoch: number
  got: boolean // received any content in this epoch
  conn: Conn
  asr: 'deepgram' | 'local' | 'reconnecting' | 'offline' | null
  stereo: boolean | null
  message: string | null
  speakers: Record<string, Spk>
  utts: Record<string, Utt>
  ann: Record<string, Ann>
  suggestions: Suggestion[]
  catchUp: CatchUpItem[] | null
  catching: boolean
  replies: string[]
  suggesting: boolean
  notice: string | null
  busyRoom: boolean
}

export const init: State = {
  epoch: 0, got: false, conn: 'idle', asr: null, stereo: null, message: null,
  speakers: {}, utts: {}, ann: {}, suggestions: [], catchUp: null, catching: false,
  replies: [], suggesting: false, notice: null, busyRoom: false,
}

export type Action =
  | { t: 'server'; ev: ServerEvent }
  | { t: 'conn'; conn: Conn }
  | { t: 'speaker'; speaker: Speaker } // local optimistic upsert (current epoch)
  | { t: 'dismissSuggestion'; id: string }
  | { t: 'catchUpStart' }
  | { t: 'catchUpClose' }
  | { t: 'repliesStart' }
  | { t: 'repliesClear' }
  | { t: 'notice'; msg: string | null }
  | { t: 'clearAll' }

export const sk = (epoch: number, id: string) => (id === 'YOU' ? 'YOU' : `${epoch}|${id}`)
export const uk = (epoch: number, id: string) => `${epoch}|${id}`

function placeholder(id: string, epoch: number): Spk {
  let h = 0
  for (const c of id) h = (h * 31 + c.charCodeAt(0)) >>> 0
  return { id, label: id === 'YOU' ? 'You' : id === 'UNKNOWN' ? 'Unknown speaker' : `Speaker ${id}`, name: null, name_source: null, color_index: h % 8, direction_deg: null, active: false, key: sk(epoch, id), epoch }
}

export function reducer(state: State, a: Action): State {
  const e = state.epoch
  switch (a.t) {
    case 'conn': {
      if (a.conn === 'open') {
        const bump = state.got
        return {
          ...state, conn: 'open', epoch: bump ? e + 1 : e, got: false,
          asr: bump ? null : state.asr, stereo: bump ? null : state.stereo, suggestions: bump ? [] : state.suggestions,
        }
      }
      // Connection lost: freeze interim text and stop "speaking" pulses; everything received stays.
      const utts = Object.fromEntries(Object.entries(state.utts).map(([k, u]) => [k, u.is_final ? u : { ...u, is_final: true }]))
      const speakers = Object.fromEntries(Object.entries(state.speakers).map(([k, s]) => [k, s.active ? { ...s, active: false } : s]))
      return { ...state, conn: a.conn, utts, speakers, catching: false, suggesting: false }
    }
    case 'speaker': {
      const key = sk(e, a.speaker.id)
      return { ...state, speakers: { ...state.speakers, [key]: { ...a.speaker, key, epoch: state.speakers[key]?.epoch ?? e } } }
    }
    case 'dismissSuggestion': return { ...state, suggestions: state.suggestions.filter((s) => s.id !== a.id) }
    case 'catchUpStart': return { ...state, catching: true, catchUp: null }
    case 'catchUpClose': return { ...state, catching: false, catchUp: null }
    case 'repliesStart': return { ...state, suggesting: true, replies: [] }
    case 'repliesClear': return { ...state, suggesting: false, replies: [] }
    case 'notice': return { ...state, notice: a.msg }
    case 'clearAll': return { ...init, epoch: e + 1, conn: state.conn, asr: state.asr, stereo: state.stereo }
    case 'server': break
  }
  const ev = a.ev
  switch (ev.type) {
    case 'status': return { ...state, asr: ev.asr, stereo: ev.stereo, message: ev.message ?? null }
    case 'room': return { ...state, busyRoom: ev.busy }
    case 'speaker': {
      const key = sk(e, ev.speaker.id)
      return { ...state, got: true, speakers: { ...state.speakers, [key]: { ...ev.speaker, key, epoch: e } } }
    }
    case 'speaker_removed': {
      const key = sk(e, ev.id)
      const into = ev.merged_into ? sk(e, ev.merged_into) : null
      const speakers = { ...state.speakers }
      delete speakers[key]
      const utts: Record<string, Utt> = {}
      for (const [k, u] of Object.entries(state.utts)) {
        if (u.skey !== key) utts[k] = u
        else if (into) utts[k] = { ...u, skey: into }
      }
      return { ...state, speakers, utts, suggestions: state.suggestions.filter((s) => s.skey !== key) }
    }
    case 'utterance': {
      const u = ev.utterance
      const skey = sk(e, u.speaker_id)
      const speakers = state.speakers[skey] ? state.speakers : { ...state.speakers, [skey]: placeholder(u.speaker_id, e) }
      const key = uk(e, u.id)
      return { ...state, got: true, speakers, utts: { ...state.utts, [key]: { ...u, key, epoch: e, skey, gkey: u.overlap_group ? `${e}|${u.overlap_group}` : null } } }
    }
    case 'annotation': {
      const r = (id: string | null) => (id ? uk(e, id) : null)
      return { ...state, ann: { ...state.ann, [uk(e, ev.utterance_id)]: { reply_to: r(ev.reply_to), interrupts: r(ev.interrupts), thread_id: ev.thread_id, incomplete: ev.incomplete } } }
    }
    case 'name_suggestion': {
      const s: Suggestion = { id: ev.id, skey: sk(e, ev.speaker_id), name: ev.name, kind: ev.kind, auto: ev.auto_applied }
      return { ...state, suggestions: [...state.suggestions.filter((x) => x.id !== s.id), s] }
    }
    case 'catch_up':
      return { ...state, catching: false, catchUp: ev.items.map((i) => ({ skey: sk(e, i.speaker_id), ukeys: i.utterance_ids.map((id) => uk(e, id)), summary: i.summary })) }
    case 'reply_suggestions': return { ...state, suggesting: false, replies: ev.options }
    case 'error': return { ...state, notice: ev.message || ev.code }
  }
}

export const nameOf = (s: { name: string | null; label: string } | undefined) => (s ? s.name ?? s.label : 'Someone')

/** Overlap groups (>=2 members) and the live "mixed" originals to hide once separated streams exist. */
export function derive(utts: Record<string, Utt>) {
  const raw = new Map<string, Utt[]>()
  for (const u of Object.values(utts)) if (u.gkey) raw.set(u.gkey, [...(raw.get(u.gkey) ?? []), u])
  const groups = new Map<string, Utt[]>()
  const hidden = new Set<string>()
  for (const [g, list] of raw) {
    const sep = list.filter((u) => u.source === 'separated')
    const shown = sep.length >= 2 ? sep : list
    for (const u of list) if (!shown.includes(u)) hidden.add(u.key)
    if (shown.length >= 2) groups.set(g, shown.sort((a, b) => a.start - b.start))
  }
  const sorted = Object.values(utts).filter((u) => !hidden.has(u.key)).sort((a, b) => a.epoch - b.epoch || a.start - b.start || a.id.localeCompare(b.id))
  return { groups, hidden, sorted }
}
