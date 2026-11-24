// Mirrors docs/CONTRACT.md. Add optional fields only.
export type SpeakerId = string // "S1".. | "YOU" | "UNKNOWN"

export interface Speaker {
  id: SpeakerId
  label: string
  name: string | null
  name_source: 'auto' | 'user' | 'suggested' | null
  color_index: number
  direction_deg: number | null
  active: boolean
}

export interface Word { w: string; start: number; end: number; conf: number }

export interface Utterance {
  id: string
  speaker_id: SpeakerId
  speaker_confidence: number
  speaker_uncertain: boolean
  text: string
  words: Word[]
  start: number
  end: number
  is_final: boolean
  overlap_group: string | null
  source: 'live' | 'separated' | 'you'
  direction_deg: number | null
}

export type ServerEvent =
  | { type: 'status'; asr: 'deepgram' | 'local' | 'reconnecting' | 'offline'; stereo: boolean; message?: string }
  | { type: 'speaker'; speaker: Speaker }
  | { type: 'speaker_removed'; id: SpeakerId; merged_into?: SpeakerId }
  | { type: 'utterance'; utterance: Utterance }
  | { type: 'annotation'; utterance_id: string; reply_to: string | null; interrupts: string | null; thread_id: string | null; incomplete: boolean }
  | { type: 'name_suggestion'; id: string; speaker_id: SpeakerId; name: string; evidence_utterance_id: string; kind: 'self_intro' | 'introduced' | 'correction'; auto_applied: boolean }
  | { type: 'catch_up'; items: { speaker_id: SpeakerId; utterance_ids: string[]; summary: string }[] }
  | { type: 'reply_suggestions'; options: string[] }
  | { type: 'room'; busy: boolean }
  | { type: 'error'; code: string; message: string }

export type ClientMessage =
  | { type: 'hello'; sample_rate: 16000; channels: 1 | 2 }
  | { type: 'tts_start'; id: string; text: string }
  | { type: 'tts_end'; id: string }
  | { type: 'rename_speaker'; speaker_id: SpeakerId; name: string }
  | { type: 'merge_speakers'; from_id: SpeakerId; into_id: SpeakerId }
  | { type: 'name_suggestion_response'; suggestion_id: string; accept: boolean }
  | { type: 'catch_up'; seconds: number }
  | { type: 'suggest_replies' }
  | { type: 'set_voice_memory'; enabled: boolean }
  | { type: 'forget_all' }

// Text-to-speech HTTP API (docs/CONTRACT.md "HTTP: text-to-speech").
export interface TtsVoice { id: string; name: string; description: string; accent: string; gender: string }
export interface TtsVoices { default: string; voices: TtsVoice[] }
