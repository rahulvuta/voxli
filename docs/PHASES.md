# Voxli phase cards

Deadline: **Nov 28, 2026, 3:00 p.m. PST**. Build window for these cards: today (Nov 24) → integration Nov 26.
All six run in parallel against `docs/CONTRACT.md`. Lead (Opus) integrates, tests on phone, and handles cross-card changes.
Each card is sized to roughly the same effort. Each card's "Evidence" feeds a rubric section.

Shared rules: only edit files you own. Python: `cd backend && uv run ...`. Adding a Python package: `uv add <pkg>`; if it fails because another agent is installing at the same moment, wait 30 s and retry. Never print API keys. No raw audio to disk outside `eval/`. Log AI-code checks in `docs/dev-log/<card>.md`.

---

## Card 1 — Live pipeline & ASR  (owner: agent `pipeline`)
**Goal:** word-by-word captions from the phone mic, with the session surviving network/service failures.
**Owns:** `backend/src/voxli/server.py`, `session.py`, `audio.py`, `asr/**`, `backend/tests/test_asr*.py`, `backend/tests/test_session*.py`, `docs/dev-log/pipeline.md`
**Build:**
1. `asr/deepgram_live.py`: Deepgram live WebSocket (Nova-3, `interim_results`, `smart_format`, `punctuate`, `diarize` (hint only), `utterance_end_ms`, `vad_events`, linear16 16 kHz). Map to `ASRResult` with session-relative times; stable `segment_id` from interim → final. KeepAlive during silence.
2. `asr/local_parakeet.py`: offline fallback using `parakeet-mlx` on Apple Silicon. Silero VAD chunks speech; emits finals (and interims if feasible via its streaming API).
3. `asr/failover.py`: wraps both. If Deepgram can't connect, errors, or goes silent while audio has speech → switch to local within ~2 s, emit `status` (`reconnecting` → `local`), keep trying Deepgram in background and switch back. No captions lost: audio from the gap is replayed into the local engine from `AudioBuffer`.
4. `session.py`: use failover ASR; make interim utterances keep the speaker from a quick provisional identity pass when available; track `active` speakers (emit `speaker` updates when someone starts/stops talking); integrate the overlap path: on each final, call `overlap.detect` on that span; if overlap, `await overlap.separate`, re-transcribe each stream via OpenRouter `deepgram/nova-3` file endpoint (`POST https://openrouter.ai/api/v1/audio/transcriptions`, base64 wav, `model:"deepgram/nova-3"`), identity-assign each, emit as `source:"separated"` utterances sharing an `overlap_group` (keep the original live utterance but mark it with the same `overlap_group`). Handle `name_suggestion_response` (apply/undo via identity.rename). Proper `tts_end` handling.
5. Robust WS: malformed messages → `error` event, not a crash.
**Done when:** pytest passes; a script `backend/scripts/replay.py <wav>` streams a wav file through the real session in real time and prints events (used by everyone for testing); killing network / bad Deepgram key falls back to local with status events (test it by setting an invalid key in an env override).
**Evidence:** R1 (main flow), R3 failure #1 (service unavailable → local fallback, no lost captions), latency numbers (first-word ms) logged by replay.py.

## Card 2 — Voice identity engine  (owner: agent `identity`)
**Goal:** the same person keeps the same identity all session; "?" instead of a confident wrong label.
**Owns:** `backend/src/voxli/identity/**`, `backend/tests/test_identity*.py`, `docs/dev-log/identity.md`
**Build:**
1. Embeddings with SpeechBrain ECAPA (`speechbrain/spkrec-ecapa-voxceleb`, ungated) on MPS/CPU; compare with pyannote's WeSpeaker ResNet34 if easy and pick by test. Cache model under `backend/models_cache/`.
2. Online clustering: per-speaker centroid (running mean of L2-normalized embeddings, plus a small set of exemplars). Thresholds: match ≥ T_hi → assign; < T_lo → new speaker; between → `uncertain=True` with best guess. Segments < ~0.8 s: weak evidence (low confidence, don't create new speakers from them; lean on vendor `hint` + direction).
3. Use `hint` (Deepgram label) and `direction` as tiebreakers only.
4. Labels "Speaker A, B, …", `color_index` stable. `rename`, `merge` (merge centroids), mute windows (TTS), `forget_all`.
5. Opt-in voice memory: save/load centroids + names to `config.VOICE_MEMORY_PATH` (JSON, embeddings only, never audio). Off by default; `forget_all` deletes the file.
6. Late correction: if a new speaker's centroid converges onto an existing one (similarity > merge threshold after N segments), auto-merge and return info so session can emit `speaker_removed`. Expose this via a method `pending_merges()`.
**Done when:** unit tests on synthetic speakers (use macOS `say` voices to generate test speech, e.g. `say -v Samantha -o x.aiff` then convert with ffmpeg to 16 kHz wav, under `eval/clips/identity/`) show stable assignment across ≥3 voices and turns; threshold choices are justified by a printed similarity table.
**Evidence:** A2 (the identity layer is our project-specific AI design choice) — produce `eval/out/identity_report.md`-ready numbers: label flips and speaker accuracy for (a) Deepgram's own diarization labels vs (b) Voxli identity, on the same clips. Write the measuring script as `backend/scripts/eval_identity.py`.

## Card 3 — Overlap separation & direction  (owner: agent `overlap`)
**Goal:** when two people talk at once, show both contributions; show where voices come from when the phone gives stereo.
**Owns:** `backend/src/voxli/overlap/**`, `backend/src/voxli/spatial/**`, `backend/tests/test_overlap*.py`, `backend/tests/test_doa*.py`, `backend/vendor/**` (third-party model code if needed, with LICENSE), `docs/dev-log/overlap.md`
**Build:**
1. Overlap detection: pyannote segmentation (overlap output) if its weights download without a gated HF token; otherwise a fallback detector (e.g., two-speaker evidence from frame-level embeddings changing within a segment + energy), and report what's needed for the better path.
2. Separation: evaluate **TIGER** and **MossFormer2** (ClearerVoice; note `clearvoice` pins soundfile 0.12.1 which conflicts — vendor just the model code/weights if needed) on 2-speaker mixtures; pick by SI-SDR improvement and speed on M5. Only run on detected overlap spans (≤ ~6 s).
3. `spatial/doa.py`: GCC-PHAT time-difference between the two channels → angle; phone mic spacing assumption documented (configurable, default ~0.14 m). Return confidence; return None for mono or identical channels (iPhone Safari gives duplicated mono — detect it).
**Done when:** tests pass; on synthetic mixtures made from `say` voices (overlap 1–3 s) separation produces two streams whose transcripts (via OpenRouter nova-3) each recover most of the original sentence; DOA test on synthetic delayed stereo returns the right side.
**Evidence:** A3 + R2 demanding case — a table: WER of the overlapped region without separation vs with TIGER vs with MossFormer2, plus runtime per second of audio. Script `backend/scripts/eval_overlap.py`.

## Card 4 — Context AI (Claude via OpenRouter)  (owner: agent `context`)
**Goal:** structure the conversation without ever changing anyone's words; learn names from introductions; catch-up and reply suggestions.
**Owns:** `backend/src/voxli/context/**`, `backend/tests/test_context*.py`, `eval/context/**`, `docs/dev-log/context.md`
**Build:**
1. OpenRouter chat completions (`https://openrouter.ai/api/v1/chat/completions`), model `config.CONTEXT_MODEL` (`anthropic/claude-haiku-5.5`; compare `anthropic/claude-sonnet-5.5` in eval). JSON-only output with schema validation; timeouts (~4 s) and graceful no-op on failure.
2. `on_final`: send the last ~12 utterances as `[id] Speaker: text` lines; get back annotations (`reply_to`, `interrupts`, `thread_id`, `incomplete`) referencing **only existing IDs** (validate; drop invalid ones) and name events.
3. Names: self-intro ("I'm Sarah") → `auto_applied:true`; introduced by someone else ("this is my friend Sarah") → suggestion attached to the next different speaker, `auto_applied:false`; mere mentions ignored; corrections update. A cheap regex pre-filter decides whether to even ask the model about names.
4. `catch_up`: per-speaker utterance_ids from the window + ≤ 15-word summary each (labeled AI summary). `suggest_replies`: 3 short options in the user's voice (first person), never sent automatically.
5. Verbatim guard: a function that proves the model output contains no rewritten text fields for utterances (only IDs/metadata) — unit-tested.
6. Batch/debounce so a busy conversation doesn't fire a request per utterance (e.g., at most 1 in-flight; coalesce).
**Done when:** tests pass with a mocked HTTP layer AND a live run of `eval/context/run_names.py` on a ≥30-item labeled set (`eval/context/names.jsonl`: self-intros, third-party intros, mere mentions, corrections, tricky negatives like "I'm tired") reports precision/recall/false-name rate for Haiku vs Sonnet, plus latency.
**Evidence:** A1 (Haiku vs Sonnet speed/cost/accuracy), A2 (verbatim-guard + name rules), A3 (name eval with limits), D4 (reply/interrupt relationships).

## Card 5 — Phone web app  (owner: agent `web`)
**Goal:** the most readable live conversation view possible on a phone, plus type-to-speak.
**Owns:** everything under `web/` except `web/src/protocol.ts` (read-only; request changes in report), `docs/dev-log/web.md`
**Build:**
1. Mic capture: AudioWorklet → 16 kHz Int16 frames; request `channelCount: 2`, check actual track settings and detect duplicated-mono; send `hello` with real channel count. Auto-reconnect WS with backoff; keep all received captions on reconnect (R3).
2. Layout (mobile-first, also fine on tablet): top **radar ring** with speaker dots (direction when known, else evenly placed; pulse when `active`); **speaker lanes** (one per speaker, independent scroll, newest at bottom, colour + shape glyph per speaker, colour-blind-safe palette); **overlap**: utterances sharing `overlap_group` shown bracketed side-by-side; **reply/interrupt** thin connector or "↩ Sarah" chip; interim text in lighter weight; low-`conf` words dotted underline; `speaker_uncertain` → "?" badge; tap speaker → rename / merge sheet; name suggestions as chips with confirm / undo; "Catch me up" sheet (verbatim lines first, AI summary labeled); also a "Timeline" toggle that shows a single interleaved view.
3. Reply bar pinned at bottom: type → speak via `speechSynthesis` (send `tts_start`/`tts_end`), quick-phrase chips (repeat / slower / one sec / custom saved in localStorage), "Suggest" button → reply_suggestions chips (tap to fill, never auto-speak), "Show to them" full-screen large text.
4. Settings: text size (S–XXL), high contrast, speaker colours, reduce motion, voice memory toggle (with clear explanation), "Delete everything" (forget_all). Always-visible mic/recording indicator and ASR status pill (Deepgram / Local / Reconnecting).
5. `?mock=1` mode: a scripted fake conversation (3–4 speakers, an interruption, an overlap, a self-intro name, an uncertain speaker) driven from `web/src/mock.ts` so the UI can be built and demoed without the backend.
**Done when:** `npm run build` passes; works in phone-sized viewport in mock mode and against the real backend at `https://<LAN-IP>:5173`; accessible (labels, contrast, focus order, `prefers-reduced-motion`).
**Evidence:** D1–D4 (emphasis, consistent design, reduced effort: auto names + quick replies, relationships visible), R3 failure #2 UI (mono mic / uncertain speaker / reconnect banners).

## Card 6 — Evaluation, test clips & submission docs  (owner: agent `eval`)
**Goal:** the evidence judges score, and the written submission.
**Owns:** `eval/**` except `eval/context/**`, `README.md`, `docs/DEVPOST.md`, `docs/AI_DISCLOSURE.md`, `docs/EVIDENCE.md`, `docs/dev-log/eval.md`, `backend/scripts/eval_asr.py`, `backend/scripts/make_clips.py`
**Build:**
1. **Test clips first (others need them — do within your first stretch):** `backend/scripts/make_clips.py` generates scripted conversations with macOS `say` voices (several distinct voices, ffmpeg → 16 kHz mono wav) with ground-truth JSON (speaker, text, start, end): (a) 2-speaker turn-taking, (b) 4-speaker café-style with an interruption, (c) overlap clips (two voices 1–3 s simultaneous), (d) a noisy version (mix in generated babble/pink noise at 5–10 dB SNR), (e) a stereo version with per-speaker inter-channel delay for DOA tests, (f) a self-intro clip ("Hi, I'm Sarah"). Write to `eval/clips/` + `eval/clips/manifest.json`. Clearly label these as synthetic.
2. `backend/scripts/eval_asr.py` (A1): WER + latency on the clips for Deepgram live (streamed in real time), OpenRouter `deepgram/nova-3`, `nvidia/parakeet-tdt-0.6b-v3`, `openai/whisper-large-v3-turbo`, and local parakeet-mlx; record cost from published prices. Output `eval/out/asr.md`.
3. `docs/EVIDENCE.md`: the R2 table (2 ordinary cases, a repeat, 1 demanding case), R3 table (2 failure causes), and slots for identity/overlap/context results (other agents' scripts produce them; you run them at the end if available and paste results, else leave clearly marked TODO).
4. `README.md`: what Voxli is, architecture diagram (mermaid), setup (uv, npm, .env keys, `./dev.sh`, phone HTTPS cert note), privacy model, limitations, credits/licenses of third-party models.
5. `docs/DEVPOST.md`: draft answers to the 5 Devpost questions, citing sources for the need (WHO hearing-loss stats, research on group-conversation fatigue for DHH people) and a comparison vs Google Live Transcribe, Ava, Otter (cite their docs). Plus a 2–4 min demo video script with shot list.
6. `docs/AI_DISCLOSURE.md`: compile `docs/dev-log/*.md` at the end into the A4 format; describe AI in the product (models, jobs, why).
**Done when:** clips + manifest exist, `eval_asr.py` produced real numbers, README/DEVPOST/EVIDENCE drafted with real numbers where available and explicit TODOs elsewhere.
**Evidence:** V1, V2, V3, A1, A4, R2 table, the whole write-up.
