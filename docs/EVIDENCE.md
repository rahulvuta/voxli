# Evidence

Everything here is produced by a script in this repo; the script is named next to each table. **All audio is synthetic**: macOS `say` text-to-speech voices mixed by `backend/scripts/make_clips.py` (14 clips, 6 to 58 s, in `eval/clips/`, listed in `eval/clips/manifest.json`). TTS is cleaner, more regular and more separable than real speech, so absolute numbers are optimistic. Nothing here was tested with real Deaf or hard-of-hearing users, in a real room, or on a real phone microphone. Machine: Apple Silicon Mac that was also running other agents' jobs (load average 4-8), which inflates latencies. Run date 2026-11-24.

Contents: 1 ASR comparison (A1) / 2 R2 cases / 3 R3 failures / 4 identity (A2, A3) / 5 overlap (A2, A3) / 6 Claude context layer (A1, A2, A3) / 7 limits / 8 how to reproduce.

---

## 1. ASR model comparison (A1)   `backend/scripts/eval_asr.py` -> `eval/out/asr.md`

8 clips, 4.7 audio-minutes, WER after normalising case/punctuation/numbers (`$25`, `7:30`), one run per cell. Deepgram live is streamed in real time over its WebSocket; the others receive the whole clip.

| clip | Deepgram live (Nova-3) | OpenRouter `deepgram/nova-3` | OpenRouter `nvidia/parakeet-tdt-0.6b-v3` | OpenRouter `openai/whisper-large-v3-turbo` | local `parakeet-mlx` v3 |
|---|---|---|---|---|---|
| turns_2spk (31 s) | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| cafe_4spk (58 s, 1.3 s interruption) | 1.6% | 1.1% | 1.1% | 0.0% | 1.1% |
| noisy_cafe_babble_snr10 | 1.1% | 1.1% | 3.3% | 4.4% | 3.3% |
| noisy_cafe_babble_snr5 | 6.0% | 3.8% | 5.5% | 5.5% | 8.2% |
| noisy_turns_pink_snr10 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| selfintro_sarah, introduced_marcus | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| overlap_2spk_2s (2 voices, 2 s overlap) | 24.1% | 27.6% | 20.7% | **48.3%** | 20.7% |
| **mean, all 8 clips** | 4.1% | 4.2% | 3.8% | 7.3% | 4.2% |
| mean, 3 noisy clips | 2.4% | 1.6% | 2.9% | 3.3% | 3.8% |

| engine | latency measured | price | cost of this run (4.7 min) |
|---|---|---|---|
| Deepgram live Nova-3 | first caption 0.44 s after the first word starts; an interim update about every 0.92 s (not per word); final result median 1.04 s after speech ends | $0.0048 / min = $0.29 / h streaming, diarization is a $0.0020 / min add-on we do not use ([Deepgram pricing](https://deepgram.com/pricing), read 2026-11-24) | $0.023 |
| OpenRouter `deepgram/nova-3` | batch 0.056 s per audio-second | OpenRouter-reported cost per call, about $0.26 / h | $0.020 |
| OpenRouter `nvidia/parakeet-tdt-0.6b-v3` | batch 0.076 s per audio-second | about $0.07 / h | $0.006 |
| OpenRouter `openai/whisper-large-v3-turbo` | batch 0.125 s per audio-second | about $0.02 / h | $0.001 |
| local `parakeet-mlx` | batch 0.026 s per audio-second on the Apple GPU (0.064 on CPU). By default the MLX GPU kernel fails to load on this M5 / macOS 26.1 (`steel_gemm_fused_nax`); setting `MLX_METAL_GPU_ARCH=applegpu_g16s` (workaround found by the pipeline agent) fixes it | $0 | $0 |

Prices: OpenRouter model list API `https://openrouter.ai/api/v1/models` (per-second rates, e.g. nova-3 $0.0000717/s) and per-call `usage.cost` in each response; Deepgram from the pricing page above.

**What this shows (and does not).**
- On clean synthetic speech every engine is at 0-1% WER, so **ASR accuracy is not what separates the options** here; the decision rests on streaming, cost, privacy and failure behaviour. Deepgram Nova-3 live is the only one in this table that streams interim words, so it is the main path. Local Parakeet is within about 1 WER point on clean clips and in noise 3.8% vs 2.4%, costs nothing and works offline, so it is the fallback.
- Whisper-large-v3-turbo is cheapest but worst on the overlap clip (48.3%): it transcribed only one speaker. Rejected for the overlap re-transcription step.
- **Every engine dropped the same two words ("not yet") in the 1.3 s interruption in `cafe_4spk`** (checked by word alignment), the only ordinary-clip error shared by all five. That is the case the overlap feature exists for.
- Deepgram live is not word-by-word in this setup: interim updates came about once a second whatever the chunk size we sent (20 ms vs 100 ms tested). Captions therefore appear in bursts of about a second.
- Limits: TTS speech, 8 clips, one run per cell (differences of 1-2 points are within noise), batch vs live latencies are not comparable, no accented or real noisy speech, timings were taken on a loaded machine.

---

## 2. R2: ordinary cases, a repeat, a demanding case   `eval/run_r2.py` -> `eval/out/r2_r3.md`

Each clip is streamed **in real time** through the real `Session` (`backend/scripts/replay.py --realtime`: Deepgram live -> identity -> overlap -> context) and scored against the manifest ground truth. "Speaker acc" = final utterances whose label matches the true speaker under the best label mapping; a "?" is not counted correct but is not a confident error. WER is on the live stream only; "recall" is the share of reference words appearing anywhere in the final utterances (live, then live + separated).

| | case (clip) | expected | actual | met? |
|---|---|---|---|---|
| **Ordinary 1** | 2-speaker turn-taking (`turns_2spk`, 31 s) | all 8 turns captioned, WER <= 5%, 2 labels, 0 flips, 0 confident-wrong | WER 0.0%, 100% speaker acc (8/8), 2 labels for 2 speakers, 0 flips, 0 "?"; first caption 487 ms after speech onset; median final-line lag 1.55 s | yes |
| **Ordinary 2** | self-introduction (`selfintro_sarah`, 18 s) | "Sarah" attached to the speaker who said "I'm Sarah", auto-applied | WER 0.0%, 100% speaker acc (5/5); `S1 = Sarah (auto)`, one `name_suggestion` kind `self_intro`, `auto_applied: true` | yes |
| **Repeat** | same clip as Ordinary 1, second run | same result | WER 0.0%, 100% (8/8), 0 flips; first caption 438 ms, final lag 1.56 s (run 1: 487 ms, 1.55 s) | yes (repeatable within about 50 ms) |
| **Demanding A** | 4 speakers, babble noise at 5 dB SNR, one interruption (`noisy_cafe_babble_snr5`, 58 s) | WER <= 15%, no confident-wrong label ("?" allowed) | live WER 6.6% (reference-word recall 95% live, 98% with separated lines); **0 confident-wrong, 6 "?"**; but only 45% of lines carried a correct label (5/11), 5 labels for 4 speakers; **the overlap detector fired 18 times on a clip with 1 real overlap** (36 separated lines, mostly false alarms on the babble); **median final-line lag 9.8 s** | partly: WER and no-confident-wrong met; label coverage, false overlaps and lag are not acceptable yet |
| **Demanding B** | 2 voices overlapping 2 s (`overlap_2spk_2s`, 8 s) | both sentences shown, same `overlap_group` | **overlap not detected in the pipeline run**: one live line, A's sentence plus half of B's ("...main entrance The delivery is from the warehouse..."), live WER 24.1%, recall 79%, no separated lines | **no** (see section 5 for the offline separation numbers) |

Raw JSON including every final utterance: `eval/out/r2_r3.json`. All five rows are one run each; results shift between runs because Deepgram and the machine load vary.

---

## 3. R3: two different failure causes   `eval/run_r2.py`

| | cause | how detected | how handled | expected | actual | met? |
|---|---|---|---|---|---|---|
| **1a** | ASR service unavailable (invalid Deepgram key) | connection fails, no results | status `reconnecting -> reconnecting -> local`, on-device Parakeet takes over | captions still appear, WER near normal | status sequence as expected, captions appear, but **WER 34%, recall 66%**: local mode emitted three ~10 s lines and lost the 20-30 s region; speaker attribution within those long lines is poor (33%) | partly: failover works, "no lost captions" does not hold in this run (the machine was loaded, and `replay.py` waits only 4 s after the audio ends) |
| **1b** | connection lost mid-stream (Deepgram socket closed at 8 s) | socket closes | `reconnecting -> local -> deepgram`, gap replayed from the audio buffer | no gap in captions | **WER 0.0%, recall 100%**, status `reconnecting -> deepgram -> reconnecting -> local -> deepgram`; speaker accuracy 67% (6 lines, 1 confident-wrong, 2 flips around the switch) | yes for captions; identity glitched at the switch |
| **2** | phone delivers duplicated mono (iPhone Safari) | web app compares L/R energy before `hello` and sends `channels:1` (web agent's fake-microphone test, `docs/dev-log/web.md`); backend DOA returns None for identical channels (`backend/tests/test_doa.py`) | no direction is invented, captions unaffected, the UI shows its mono banner | no direction value, no crash, captions normal | `stereo_dupmono` through the session: WER 0.0%, 100% speaker acc, no `direction_deg` on any utterance | yes at session level. **Not tested:** the banner on a real phone, a real iPhone microphone |

Other handled cases that exist but were not part of these runs: malformed WebSocket messages produce `error` events (pipeline tests); uncertain speaker shows "?" (identity eval section 4).

---

## 4. Speaker identity (A2, A3)   `backend/scripts/eval_identity.py` -> `eval/out/identity.md`

Produced by the identity agent's script (not re-run by eval; it was finished and its output file is dated before this document). Summary of its own tables, all on **synthetic `say` voices**:

- Embedding choice: ECAPA-TDNN EER 3.1% vs WeSpeaker ResNet34 6.0%, 37 vs 55 ms per 4 s clip -> ECAPA. Thresholds chosen by a 45-conversation sweep: T_HI 0.65, T_LO 0.40, T_MERGE 0.80 (dev log items 4 and 6).
- Short segments are weak evidence: same-speaker similarity falls from 0.85 (full) to 0.52 (0.5 s), so segments under 0.8 s never create speakers.
- Deepgram diarization (best case: whole file, prerecorded API) vs Voxli identity on the same turns:

| conversation | method | accuracy (all turns) | confident-wrong turns | label flips |
|---|---|---|---|---|
| easy4 (4 distinct voices, 32 turns) | Deepgram diarization | 75% | 8 | 0 (3 labels for 4 speakers) |
| | Voxli | 69% (rest are "?") | **0** | 0 |
| similar4 | Deepgram | 97% | 1 | 1 |
| | Voxli | 69% | 6 | 0 |
| twins3 (near-identical voices) | Deepgram | 67% | 8 | 0 |
| | Voxli | 58% | 7 | 0 |
| noisy_cafe_babble_snr5 | Deepgram | 75% | 4 | 0 |
| | Voxli | 75% | 2 | 2 |

- **Honest reading:** Voxli does not beat Deepgram's diarization on raw accuracy. On the clean 4-voice case it replaces 8 confident wrong labels with 0 by showing "?" for about a third of turns, and it never merged two distinct voices; on the harder `similar4` set it was worse (6 confident-wrong vs 1). The claim we can support is **fewer confident wrong labels on distinct voices, at the cost of coverage**, not higher accuracy. Real voices were not tested. See `eval/out/identity.md` for all rows (including the full clips and per-length breakdown).
- `assign` latency 32 ms median, 95 ms p95 on CPU.

---

## 5. Overlap separation (A2, A3)   `backend/scripts/eval_overlap.py` -> `eval/out/overlap.md`

12 two-talker synthetic mixtures (4 voice pairs x 1/2/3 s overlap, equal level). cpWER = WER of both reference sentences against the method's output streams (best stream permutation), each stream transcribed with OpenRouter `deepgram/nova-3`. SI-SDRi = separation quality gain over the mixture. Runtime on a loaded Apple Silicon Mac (MPS), per second of audio.

**Clean mixtures**

| method | cpWER 1 s | 2 s | 3 s | all | SI-SDRi | runtime (s per audio s) |
|---|---|---|---|---|---|---|
| no separation | 24% | 54% | 51% | **43%** | 0 dB | 0 |
| MossFormer2 | 26% | 7% | 7% | **13%** | 18.6 dB | 0.62 |
| TIGER | 7% | 17% | 15% | **13%** | 15.7 dB | 1.19 |

**Same mixtures with synthetic reverb (RT60 about 0.4 s) and white noise at 10 dB SNR**

| method | cpWER 1 s | 2 s | 3 s | all | SI-SDRi | runtime |
|---|---|---|---|---|---|---|
| no separation | 59% | 75% | 95% | **76%** | 0 dB | 0 |
| MossFormer2 | 54% | 54% | 57% | **55%** | 5.5 dB | 0.60 |
| TIGER | 22% | 23% | 40% | **28%** | 10.5 dB | 1.19 |

**Reading:** separation cuts the error on overlapped speech from 43% to 13% on clean mixtures and from 76% to 28% (TIGER) with reverb and noise. The models tie on clean audio (MossFormer2 is about twice as fast) but TIGER is clearly more robust under reverb and noise, so **TIGER is the default** (`VOXLI_SEP_MODEL`). Limits: TTS voices, equal levels, exactly 2 talkers, synthetic reverb; runtime above 1 s per audio second means a 3 s overlap takes about 3.6 s to separate, which is a likely (not verified) contributor to the lag in section 2.

Detector: pyannote segmentation is gated (anonymous download returned 401), so a pitch-cancellation fallback detector is used; on the synthetic mixtures its recall was 67% at the chosen threshold with 4.5% false candidates on single-speaker audio (overlap dev log item 5). The end-to-end results in section 2 show both failure directions: a miss on `overlap_2spk_2s` and many false alarms on babble noise.

---

## 6. Claude context layer (A1, A2, A3)   `eval/context/run_names.py` -> `eval/out/context.md`

Produced by the context agent's script (not re-run by eval, to avoid re-spending about $0.36). 50 hand-written name items and 12 reply/interrupt snippets, run through the production `ContextEngine`; **typed text written by us, not ASR output**, so scores are optimistic.

| model | name precision / recall | false-name items | latency (median / p90) | cost for the run |
|---|---|---|---|---|
| `anthropic/claude-haiku-5.5` | 100% (38/38) / 100% | 0 of 23 negatives | 1.32 s / 2.24 s | $0.0215 |
| `anthropic/claude-sonnet-5.5` | 100% (38/38) / 100% | 0 of 23 | 1.24 s / 1.81 s | $0.3422 |

Reply-to, interrupts and incomplete flags: 12/12 for both. Verbatim guard: 0 violations across 144 emitted events per model; the adversarial check (rewritten text field, unknown id, free-text thread, hallucinated name, extra field) rejected 5/5. **Reading:** the set cannot separate the models on accuracy (both perfect), so the choice of Haiku rests on about 16x lower cost at similar latency. A perfect score on a set the authors wrote also means the set is too easy; a harder or real-ASR-output set is future work.

---

## 7. Limits (read before quoting any number)

1. Synthetic TTS audio only; 14 short clips; few voices; no real accents, rooms, reverberation, or real phone microphones.
2. One run per cell; Deepgram and the (shared, loaded) machine vary between runs. The first full R2 run was discarded because two replays hung under load and were killed; the table above is the second complete run.
3. No user study with Deaf or hard-of-hearing people; V3 feasibility rests on measured cost and the working pipeline, not on user feedback.
4. Several rows above are **misses** (overlap not detected, local fallback losing words, 9.8 s lag under overlap load, identity worse than Deepgram on similar voices). They are reported as found; fixes belong to the pipeline, overlap and identity owners.
5. Context-layer scores come from typed text, not real ASR output.

## 8. Reproduce

```
cd backend
uv run python scripts/make_clips.py          # clips + manifest
uv run python scripts/eval_asr.py            # section 1 (needs both API keys, about 6 min: live streams in real time)
uv run python ../eval/run_r2.py              # sections 2 and 3 (real-time replays, about 8 min)
uv run python scripts/eval_identity.py       # section 4
uv run python scripts/eval_overlap.py        # section 5
uv run python ../eval/context/run_names.py   # section 6
```
