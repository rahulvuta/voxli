# Voxli identity evaluation

All audio is **synthetic** (macOS `say` voices, not human speech). Real voices vary more across a session (emotion, distance, noise), so absolute numbers are optimistic; use them for relative comparison and sanity-checking thresholds.

## 1. Embedding choice and thresholds (synthetic `say` voices)

| model | same mean | diff mean | diff max | EER (segment pairs >=0.8 s) | most similar distinct pairs (centroid cos) | CPU ms / 4 s clip |
|---|---|---|---|---|---|---|
| ECAPA-TDNN (speechbrain) | 0.74 | 0.14 | 0.72 | 3.1% | Kathy/Junior 0.70, Fred/Ralph 0.57, Ralph/Rocko 0.50 | 67 |
| WeSpeaker ResNet34 (pyannote) | 0.73 | 0.15 | 0.79 | 6.0% | Kathy/Junior 0.78, Fred/Ralph 0.62, Samantha/Karen 0.56 | 108 |

Same-speaker vs different-speaker cosine, ECAPA. Each segment is scored against the centroid of the other segments of each speaker (leave-one-out), which is exactly what `assign` does. Rows crop the segment to the length shown.

| segment | n same | same mean | same p5 | same min | diff mean | diff p95 | diff p99 | diff max | same >= T_HI | diff >= T_HI (wrong accept) | diff < T_LO |
|---|---|---|---|---|---|---|---|---|---|---|---|
| full | 98 | 0.85 | 0.77 | 0.72 | 0.15 | 0.40 | 0.56 | 0.68 | 100% | 0.1% | 95% |
| 1.2 s | 98 | 0.72 | 0.58 | 0.37 | 0.14 | 0.35 | 0.50 | 0.56 | 85% | 0.0% | 97% |
| 0.8 s | 98 | 0.63 | 0.39 | 0.33 | 0.12 | 0.33 | 0.46 | 0.53 | 45% | 0.0% | 98% |
| 0.5 s | 98 | 0.52 | 0.32 | 0.27 | 0.11 | 0.30 | 0.42 | 0.55 | 11% | 0.0% | 98% |

Near-identical synthetic voices (centroid cosine): Eddy/Reed 0.98, Flo/Shelley 0.89. These are the same `say` voice with different pitch/rate, so they are not a fair test of separability; reported as a limit.

Centroid-vs-centroid (merge test): same speaker split in halves min 0.85 / mean 0.89; different speakers max 0.72 / p95 0.45.

**Chosen**: T_HI = 0.65, T_LO = 0.4, T_MERGE = 0.8 (merge only after 3 confident segments each), weak-evidence cut-off 0.8 s.

### Threshold sweep (45 random conversations of 4-6 of the 14 voices, every clip used once)

| T_HI | T_LO | new-speaker pool | turns with a label | confident-wrong (of labelled) | speaker-count error / conversation |
|---|---|---|---|---|---|
| 0.55 | 0.4 | on | 93% | 2.6% | 0.27 |
| 0.6 | 0.4 | on | 90% | 1.7% | 0.27 |
| 0.65 | 0.4 | on | 87% | 1.0% | 0.33 |
| 0.7 | 0.4 | on | 84% | 1.6% | 0.49 |
| 0.75 | 0.4 | on | 75% | 5.4% | 1.36 |
| 0.65 | 0.45 | on | 88% | 1.9% | 0.62 |
| 0.65 | 0.4 | off | 83% | 1.2% | 0.31 |

## 2. Deepgram diarization vs Voxli identity, same turns

Conversations are built from `say` clips (turn boundaries known): our own three plus the eval agent's `turns_2spk`, `cafe_4spk` (with an interruption) and noisy variants. Deepgram: prerecorded API, nova-3, diarize=true on the whole file (its best case: it sees all the audio at once; live streaming diarization has less context). Its label for a turn is the majority speaker of the words inside it. Voxli: `IdentityEngine.assign` on the same audio slice, in time order, **with no hint** (pure voiceprint) and **with Deepgram's label as hint**. Accuracy uses the best label-to-speaker mapping (Hungarian). A turn Voxli marks `?` counts as not-correct in the first accuracy column but is not a confident error. 'Label flips' = times one true speaker's consecutive labelled turns got different labels.

| conversation | method | turns | accuracy (all turns) | turns with a label | accuracy of shown labels | confident-wrong | label flips | labels used / true speakers |
|---|---|---|---|---|---|---|---|---|
| easy4 | Deepgram diarization | 32 | 75% | 100% | 75% | 8 | 0 | 3 / 4 |
| easy4 | Voxli (no hint) | 32 | 81% | 81% | 100% | 0 | 0 | 4 / 4 |
| easy4 | Voxli (+ Deepgram hint) | 32 | 81% | 81% | 100% | 0 | 0 | 4 / 4 |
| similar4 | Deepgram diarization | 32 | 97% | 100% | 97% | 1 | 1 | 4 / 4 |
| similar4 | Voxli (no hint) | 32 | 78% | 78% | 100% | 0 | 0 | 4 / 4 |
| similar4 | Voxli (+ Deepgram hint) | 32 | 78% | 78% | 100% | 0 | 0 | 4 / 4 |
| twins3 | Deepgram diarization | 24 | 67% | 100% | 67% | 8 | 0 | 2 / 3 |
| twins3 | Voxli (no hint) | 24 | 62% | 88% | 71% | 6 | 2 | 3 / 3 |
| twins3 | Voxli (+ Deepgram hint) | 24 | 62% | 88% | 71% | 6 | 2 | 3 / 3 |
| turns_2spk | Deepgram diarization | 8 | 100% | 100% | 100% | 0 | 0 | 2 / 2 |
| turns_2spk | Voxli (no hint) | 8 | 100% | 100% | 100% | 0 | 0 | 2 / 2 |
| turns_2spk | Voxli (+ Deepgram hint) | 8 | 100% | 100% | 100% | 0 | 0 | 2 / 2 |
| cafe_4spk | Deepgram diarization | 16 | 94% | 100% | 94% | 1 | 2 | 4 / 4 |
| cafe_4spk | Voxli (no hint) | 16 | 94% | 94% | 100% | 0 | 0 | 4 / 4 |
| cafe_4spk | Voxli (+ Deepgram hint) | 16 | 94% | 94% | 100% | 0 | 0 | 4 / 4 |
| noisy_cafe_babble_snr10 | Deepgram diarization | 16 | 100% | 100% | 100% | 0 | 0 | 4 / 4 |
| noisy_cafe_babble_snr10 | Voxli (no hint) | 16 | 94% | 94% | 100% | 0 | 0 | 4 / 4 |
| noisy_cafe_babble_snr10 | Voxli (+ Deepgram hint) | 16 | 94% | 94% | 100% | 0 | 0 | 4 / 4 |
| noisy_cafe_babble_snr5 | Deepgram diarization | 16 | 75% | 100% | 75% | 4 | 0 | 3 / 4 |
| noisy_cafe_babble_snr5 | Voxli (no hint) | 16 | 75% | 88% | 86% | 2 | 2 | 6 / 4 |
| noisy_cafe_babble_snr5 | Voxli (+ Deepgram hint) | 16 | 75% | 88% | 86% | 2 | 2 | 6 / 4 |
| noisy_turns_pink_snr10 | Deepgram diarization | 8 | 100% | 100% | 100% | 0 | 0 | 2 / 2 |
| noisy_turns_pink_snr10 | Voxli (no hint) | 8 | 88% | 88% | 100% | 0 | 0 | 2 / 2 |
| noisy_turns_pink_snr10 | Voxli (+ Deepgram hint) | 8 | 88% | 88% | 100% | 0 | 0 | 2 / 2 |

Latency of `assign` (embedding + matching, CPU, M-series Mac), 304 segments of 0.6-5.5 s: median 32 ms, p95 95 ms, max 273 ms.
