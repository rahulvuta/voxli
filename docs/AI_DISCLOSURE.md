# AI disclosure

Compiled from `docs/dev-log/*.md` (one log per agent, written by that agent at the time) by the eval agent on 2026-11-24. Nothing here was invented to look good: the entries marked **rejected** or **changed** are the interesting ones.

## 1. How AI was used to build Voxli

Voxli was built in one sprint by a team of Claude agents working in parallel from written task cards (`docs/PHASES.md`) against a shared interface contract (`docs/CONTRACT.md`): a lead (Claude Opus) plus one agent per card (pipeline, identity, overlap, context, web, eval; Claude Sonnet). **The AI wrote essentially all of the code and documentation.** The human owner set the goal, the rubric-driven task cards, and the rules (verbatim captions, "?" instead of a wrong label, synthetic data labelled as synthetic, no raw audio on disk); checks listed below were run by the agents (tests, scripts, profilers, screenshots) and reviewed by the lead.

**TODO(lead / owner): state here, in one honest sentence, which checks a human personally did (for example: phone test on a real device, reading the diff of X). Until that is written, the document must not claim human review.**

How to read the log: **AI produced -> checked how -> found -> decision**.

## 2. Checks of AI-assisted development (A4)

### Lead / pipeline
| AI produced | Checked how | Found | Decision |
|---|---|---|---|
| `audio.py` ring buffer, session/server skeleton (Opus) | built-in self-test (1 s stereo write + wraparound); FastAPI TestClient smoke test | passed | kept |
| Deepgram live client written from memory of the API | fetched the Deepgram streaming reference, compared fields, streamed a clip in real time | endpointing settings never produced `speech_final` on clips with short pauses (one caption grew for 12 s); re-sent finals produced duplicate segments | **changed**: sentence splitting with a cut-off time; unit test added |
| `parakeet-mlx` streaming API for local fallback, from the README | read library source, ran on a clip | Metal kernel crash on M5; streaming mode accuracy poor; draft timestamps wrong | **changed**: GPU-arch env override; streaming **rejected**, re-decode with the offline call every ~0.6 s |
| Silero VAD wiring | read `VADIterator` source, ran on clips | model hallucinated a word on digital silence | changed: skip decoding when RMS < 0.004 |
| Failover state machine | 5 fake-engine tests, then real runs (invalid key, socket closed mid-clip) | tests found two bugs (reattach replayed 60 s of old audio; first status deduplicated) | kept after fixes |
| Session rewrite (interim speakers, overlap task, undo, malformed input) | pytest with TestClient, end-to-end `replay.py` runs | false "Deepgram silent" failovers while the machine was loaded | kept; watchdog left at 2 s (see EVIDENCE.md section 3 for how it behaves under load) |
| OpenRouter nova-3 request format | fetched the OpenRouter STT docs, made a real call | word times via `verbose_json` work | kept |

### Identity (Card 2)
| AI produced | Checked how | Found | Decision |
|---|---|---|---|
| Proposed ECAPA vs WeSpeaker embeddings | both run on 18 `say` voices x 8 sentences: EER and CPU time | ECAPA EER 3.1% vs 6.0%, 37 vs 55 ms | **ECAPA kept, WeSpeaker rejected** |
| Assumed MPS would be fastest | timed CPU vs MPS on 1-6 s inputs | CPU 15-44 ms, MPS 41-95 ms | **changed** to CPU |
| "Similar-sounding" voice pairs picked by name | centroid cosine matrix | Eddy/Reed 0.98 = same TTS voice, not a fair hard case | **changed**: reported only as a limit, real hard pairs chosen from the matrix |
| First thresholds T_HI 0.6 / T_LO 0.4 | conversation-level run, then 45-conversation sweep | two voices merged with confident labels (6 confident-wrong) | **changed**: pool for in-between segments; T_HI 0.65, T_LO 0.40 (1.0% confident-wrong); 0.75/0.45 rejected |
| T_MERGE 0.90 | split-half vs different-speaker centroid cosines | gap midpoint is 0.80 | **changed** to 0.80 |
| Unit tests, voice-memory privacy | run; test asserts file holds only name/vector, deleted by forget_all, mode 0600 | an unused variable and a no-op pad in the first draft | removed; 10 tests pass |
| Deepgram-vs-Voxli scoring script | hand-verified mapping logic on one printed conversation | a column-header bug | fixed |

### Overlap / direction (Card 3)
| AI produced | Checked how | Found | Decision |
|---|---|---|---|
| Model choice from READMEs | fetched current model pages and gated flags, not memory | `clearvoice` pip package pins an incompatible soundfile | vendored model code only |
| Vendored TIGER / MossFormer2 | `load_state_dict(strict=True)`; MPS vs CPU output diff | all keys match, diff 4e-6; MPS crash in `.type()` | changed code, kept |
| Separation first run | `torch.profiler` | 114 s for 5 s audio; 85% time in an NNPACK conv | **changed**: scoped NNPACK off (~10x) + MPS |
| Overlap detector (pyannote gated, fallback YIN-based) | 12 synthetic mixtures + 190 s single-speaker audio, threshold sweep | threshold 0.35: 51% recall; 0.45: 67% recall with 4.5% false candidates | 0.45 chosen; limits documented (voiced+voiced, TTS-tuned) |
| GCC-PHAT DOA | synthetic delays, dup-mono, silence, `say` speech with known delays | angles match asin(delay*c/fs/d); docstring sign note was confusing | rewritten |
| Unit tests | run | one SI-SDR assertion compared two ~140 dB numbers (float noise) | changed |

### Context AI (Card 4)
| AI produced | Checked how | Found | Decision |
|---|---|---|---|
| Engine + prompts | 12 mocked-HTTP tests (invalid ids, forward interrupts, hallucinated name, timeouts, coalescing...) | in-flight case showed skipped utterances must stay un-annotated | design changed, kept |
| `provider.require_parameters=true` for structured output | live call | HTTP 404 on every call | **rejected**; replies are parsed and validated locally |
| Verbatim guard | 5 adversarial outputs (rewritten text field, unknown id, free-text thread, hallucinated name, extra field) | 5/5 rejected; an eval bug gave 37 false violations | eval fixed (guard run per snippet) |
| Name rules / prompt | eval run | "Dr. Okafor" failed because prompt said "first name" | prompt changed; the eval label was edited after seeing model output (disclosed) |
| Eval sets | read by hand | typed text, not ASR output; both models ~100%, set cannot separate them on accuracy | stated as a limit |
| catch_up / suggest_replies | live smoke test | Haiku once misattributed an action in a summary; summaries over 15 words truncated mid-sentence | labelled AI text in UI; limit documented |

### Web app (Card 5)
| AI produced | Checked how | Found | Decision |
|---|---|---|---|
| Epoch-keyed store; reconnect | mock drop mode + killing the real backend | works; lane tags too noisy | tag shortened, kept |
| Mic capture, dup-mono detector | fake `getUserMedia` fed from our stereo and dup-mono clips, inspected WS frames | stereo -> channels 2; dup mono -> channels 1; **not tested on a real iPhone** | kept, caveat stated |
| Websocket reconnect | killed/restarted real backend | stale-closure risk | fixed with a ref |
| Lanes / chips layout | screenshots at 375x812 and 768x1024 | class-name collision made a tall pill; lanes did not follow new captions; 4 lanes cramped; unrenderable glyph | all fixed |
| Accessibility | computed WCAG contrast for all pairs; tab-order and live-region DOM dump | border colour 2.5:1; `role="log"` double announcements | raised to >=3.9:1; role changed |
| Mock script | played it and clicked through flows | scheduler timing bug | fixed |

### Eval / docs (Card 6; `docs/dev-log/eval.md`)
| AI produced | Checked how | Found | Decision |
|---|---|---|---|
| `make_clips.py` | read back, manifest overlap windows, GCC-PHAT sign check on stereo clips | dead buggy duplicate function; stereo lags +-6 samples as expected | dead code deleted |
| `eval_asr.py` | printed word alignments before trusting WER; checked price against the live pricing page | stale Deepgram price ($0.0077 vs $0.0048/min); local MLX GPU kernel crash; first-word latency metric produced negative values because Deepgram's first interim word end is unreliable | price fixed, GPU override adopted (CPU fallback kept), metric redefined (arrival minus first word start) |
| `eval/run_r2.py` | single-case run, then full run | first full run under CPU contention: two replays hung and were killed, so scores were meaningless; WER counted separated utterances twice | per-case timeout; WER on live stream only plus a separate reference-word recall that includes separated utterances; cases re-run |
| DEVPOST citations | fetched each source | I first attributed the listening-fatigue paper to the wrong first author (found when checking authors) and a search claimed a "dinner table syndrome" study that does not exist as such | citation fixed; wording limited to what pages say |

### Cross-cutting patterns (what AI got wrong)
- **Defaults and guesses were frequently wrong until measured:** device choice (MPS), thresholds, price constants, an API flag, a "similar voices" list. Every one was fixed by a measurement, which is why the evaluation scripts exist.
- **Evaluation code needed checking as much as product code:** double-counted words, collided ids, bogus latency timestamps.
- **Nothing was accepted on the strength of the AI's own claim:** each item above has an executable check (test, script, profiler, screenshot, or fetched source).

## 3. AI inside the finished product

| Job | Model / tool | Why this one | Guardrail |
|---|---|---|---|
| Live captions (main path) | Deepgram Nova-3 streaming | only candidate that streams interim words; WER on par with the others on our clips (EVIDENCE.md section 1) | text shown verbatim; status pill shows which engine is live |
| Captions when offline / service fails | NVIDIA Parakeet-TDT 0.6B v3 via `parakeet-mlx`, on device | free, private, WER within about 1 point of Nova-3 on clean clips | automatic failover, audio replayed from the buffer |
| Re-transcribe separated overlap streams | Deepgram Nova-3 (OpenRouter file endpoint) | same accuracy class, cents per hour | separated lines are tagged `source: separated` |
| Who is speaking | SpeechBrain ECAPA-TDNN embeddings + our online clustering | chosen over WeSpeaker by EER and speed on our test voices; Deepgram diarization used only as a hint | "?" when unsure; user rename/merge; opt-in voiceprint memory |
| Two people at once | overlap detector + TIGER or MossFormer2 separation | TIGER chosen by measured cpWER/SI-SDR/runtime: 28% vs 55% under reverb + noise, equal on clean (EVIDENCE.md section 5) | only runs on detected spans |
| Conversation structure | Claude Haiku 5.5 via OpenRouter (Sonnet 5.5 compared) | Haiku equal accuracy on our set at about 1/16 the cost | metadata only: ids, thread labels, names present in the evidence; verbatim guard rejects anything else; names from introductions need confirmation |
| Catch-up summaries, reply suggestions | same Claude model | the only free-text AI outputs | labelled "AI summary"; verbatim lines shown first; replies never sent automatically |

**What the AI in the product never does:** rewrite caption words, silently guess a speaker, speak on the user's behalf, or store raw audio.

**Data leaving the device:** microphone audio to Deepgram (and short overlap spans to OpenRouter); transcript text to Anthropic via OpenRouter. See README privacy model.
