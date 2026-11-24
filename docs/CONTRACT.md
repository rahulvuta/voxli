# Voxli shared contract

Every agent builds against this. Do not rename or remove anything here. You may ADD optional
fields; list any you add in your final report.

## Runtime layout
- Backend: `backend/` (Python 3.12, uv). Run: `cd backend && uv run uvicorn voxli.server:app --host 127.0.0.1 --port 8000`
- Web: `web/` (Vite + React + TS). Run: `cd web && npm run dev` → `https://<LAN-IP>:5173` (self-signed HTTPS, needed for phone mic).
- Vite proxies `/ws` → `ws://127.0.0.1:8000/ws`, so the phone only talks to one origin.
- Secrets: repo-root `.env` has `OPENROUTER_API_KEY`, `DEEPGRAM_API_KEY`. Load with `voxli.config`. Never print or log them.
- All session times are **seconds since session start** (float). Audio is **16 kHz**.

## WebSocket `/ws`

### Client → server
First message (JSON): `{"type":"hello","sample_rate":16000,"channels":1|2}`
Then **binary frames**: Int16 little-endian PCM, 16 kHz, interleaved if channels=2 (~20–100 ms per frame).

JSON control messages:
| type | fields | meaning |
|---|---|---|
| `tts_start` | `id`, `text` | phone is about to speak typed text; server mutes identity for this window and emits a `YOU` utterance with `source:"you"` |
| `tts_end` | `id` | speaking finished |
| `rename_speaker` | `speaker_id`, `name` | user named a speaker (`name_source:"user"`) |
| `merge_speakers` | `from_id`, `into_id` | user says two labels are one person |
| `name_suggestion_response` | `suggestion_id`, `accept: bool` | accept/reject/undo a name suggestion |
| `catch_up` | `seconds` | request catch-up for last N seconds |
| `suggest_replies` | – | request 2–3 short reply options |
| `set_voice_memory` | `enabled: bool` | opt-in to remember voiceprints across sessions (local file) |
| `forget_all` | – | delete all speakers, voiceprints, history |

### Server → client (all JSON)
| type | payload |
|---|---|
| `status` | `{asr: "deepgram"\|"local"\|"reconnecting"\|"offline", stereo: bool, message?: str}` |
| `speaker` | `{speaker: Speaker}` upsert |
| `speaker_removed` | `{id, merged_into?}` |
| `utterance` | `{utterance: Utterance}` upsert by `id` (interim → final reuse same id) |
| `annotation` | `{utterance_id, reply_to: id\|null, interrupts: id\|null, thread_id: str\|null, incomplete: bool}` |
| `name_suggestion` | `{id, speaker_id, name, evidence_utterance_id, kind: "self_intro"\|"introduced"\|"correction", auto_applied: bool}` |
| `catch_up` | `{items: [{speaker_id, utterance_ids: [id], summary: str}]}` (summary is AI-written and labeled as such in UI; utterance text is verbatim) |
| `reply_suggestions` | `{options: [str]}` |
| `room` | `{busy: bool}` — true while background chatter is continuous; overlap separation is paused (captions continue) |
| `error` | `{code, message}` |

```ts
Speaker = { id: "S1"|"S2"|...|"YOU"|"UNKNOWN", label: "Speaker A", name: string|null,
            name_source: "auto"|"user"|"suggested"|null, color_index: number,
            direction_deg: number|null /* -90 left .. +90 right, null if mono/unknown */,
            active: boolean /* speaking in last ~1.5 s */ }
Word = { w: string, start: number, end: number, conf: number }
Utterance = { id: string, speaker_id: string, speaker_confidence: number /*0..1*/,
              speaker_uncertain: boolean, text: string /* VERBATIM from ASR, never rewritten */,
              words: Word[], start: number, end: number, is_final: boolean,
              overlap_group: string|null /* same value = spoke at the same time */,
              source: "live"|"separated"|"you", direction_deg: number|null }
```

## Python module interfaces (backend/src/voxli/)
- `audio.AudioBuffer` — session audio ring buffer: `append(pcm_int16_interleaved)`, `mono(start,end)->float32`, `stereo(start,end)->float32[n,2]|None`, `now()`. (Exists. Owner: pipeline.)
- `asr.base.ASREngine` — `async start(on_result)`, `async feed(pcm_mono_int16: bytes)`, `async stop()`; calls `on_result(ASRResult)`.
- `identity.engine.IdentityEngine` — `assign(audio, t_start, t_end, hint=None, direction=None) -> Assignment`, `rename`, `merge`, `speakers()`, `add_mute_window(start,end)`, `is_muted(start,end)`, `forget_all()`, `set_voice_memory(bool)`.
- `overlap.processor.OverlapProcessor` — `detect(audio, t0) -> list[(start,end)]`, `async separate(audio, t0) -> list[SeparatedStream]` (each with its own float32 audio; pipeline re-transcribes + re-identifies).
- `spatial.doa.estimate(stereo) -> (deg, confidence) | None`
- `context.engine.ContextEngine` — `async on_final(utt, history) -> list[dict events]`, `async catch_up(history, speakers, seconds) -> dict`, `async suggest_replies(history, speakers) -> dict`.

Data classes for these live in `voxli/types.py` (exists). Stubs exist for every module so the server runs end-to-end from day one; replace the stub internals, keep signatures.

## Hard rules (all agents)
1. Utterance `text` is verbatim ASR output. AI may add metadata, never alter words.
2. Uncertain speaker → `speaker_uncertain: true` (UI shows "?"), never a confident wrong label.
3. No raw audio written to disk except under `eval/` test clips. Voiceprints persist only if voice memory is on.
4. Only edit files you own (see `docs/PHASES.md`). Need a change elsewhere? Describe it in your final report.
5. Log every meaningful AI-generated-code check in your own `docs/dev-log/<card>.md` (what AI produced, how checked, what the check found, kept/changed/rejected). The eval/docs agent compiles these into `docs/AI_DISCLOSURE.md`.

## HTTP: text-to-speech (added for the voice upgrade)
Vite proxies `/api` → `http://127.0.0.1:8000`. Keys stay on the server.
- `GET /api/tts/voices` → `{"default": "<voice_id>", "voices": [{"id", "name", "description", "accent", "gender"}]}` — a short curated list (8–12) of Deepgram Aura-2 English voices.
- `POST /api/tts` JSON `{"text": str (1–500 chars), "voice": voice_id | null}` → `200 audio/wav` bytes (Deepgram Aura-2 linear16, loudness-normalised to about -13 dBFS with a soft limiter). Errors: `400` bad input, `502`/`503` provider unavailable or timeout (≤ 6 s), body `{"error": str}`. The web app falls back to the browser's `speechSynthesis` on any non-200 and shows a small notice.
- The web app still sends `tts_start` right before playback starts and `tts_end` when playback ends (so the session mutes the phone's own voice for exactly that window).
