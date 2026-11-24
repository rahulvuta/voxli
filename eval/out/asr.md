# ASR comparison (SYNTHETIC macOS-`say` clips; WER after normalisation, lower is better)

Generated 2026-11-24 17:42 by backend/scripts/eval_asr.py. Clips are text-to-speech, not real speech: absolute WERs are optimistic; use the table for relative comparison only.

| clip | dur (s) | or:deepgram/nova-3 | or:nvidia/parakeet-tdt-0.6b-v3 | or:openai/whisper-large-v3-turbo | deepgram_live | parakeet_mlx |
|---|---|---|---|---|---|---|
| turns_2spk | 31.49 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| cafe_4spk | 58.16 | 1.1% | 1.1% | 0.0% | 1.6% | 1.1% |
| noisy_cafe_babble_snr10 | 58.16 | 1.1% | 3.3% | 4.4% | 1.1% | 3.3% |
| noisy_cafe_babble_snr5 | 58.16 | 3.8% | 5.5% | 5.5% | 6.0% | 8.2% |
| noisy_turns_pink_snr10 | 31.49 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| overlap_2spk_2s | 7.72 | 27.6% | 20.7% | 48.3% | 24.1% | 20.7% |
| selfintro_sarah | 18.28 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| introduced_marcus | 18.43 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |

## Summary per engine

| engine | mean WER (all) | mean WER (clean: turns/names) | mean WER (noisy) | latency | audio min | cost USD (this run) | $/audio-hour |
|---|---|---|---|---|---|---|---|
| or:deepgram/nova-3 | 4.2% | 0.3% | 1.6% | batch: 0.056 s per audio-s (whole clip, not streaming) | 4.7 | 0.0202 | 0.26 |
| or:nvidia/parakeet-tdt-0.6b-v3 | 3.8% | 0.3% | 2.9% | batch: 0.076 s per audio-s (whole clip, not streaming) | 4.7 | 0.0058 | 0.07 |
| or:openai/whisper-large-v3-turbo | 7.3% | 0.0% | 3.3% | batch: 0.125 s per audio-s (whole clip, not streaming) | 4.7 | 0.0014 | 0.02 |
| deepgram_live | 4.1% | 0.4% | 2.4% | live: first caption 0.44s after first word starts, update every ~0.92s, final-result median 1.04s after speech end | 4.7 | 0.0226 | 0.29 |
| parakeet_mlx | 4.2% | 0.3% | 3.8% | batch: 0.026 s per audio-s (whole clip, not streaming) | 4.7 | 0.0000 | 0.00 |

## Notes / limits
- `deepgram_live` is streamed in real time; the other cloud engines get the whole clip (batch) so their latency is request time, not live latency.
- WER is computed over the clip's concatenated reference text; diarization is not scored here (see identity eval).
- Overlap clip: references contain both speakers, so any single-stream ASR loses one of them by construction.
- Prices: OpenRouter-reported `usage.cost` per call; Deepgram live list price $0.0048/min (deepgram.com/pricing, read 2026-11-24; diarization add-on not included).

## Worst hypotheses (for error analysis)

- `or:openai/whisper-large-v3-turbo` / `overlap_2spk_2s` WER 48%: _ I think we should meet at the main entrance of the station around noon tomorrow._
- `or:deepgram/nova-3` / `overlap_2spk_2s` WER 28%: _I think we should meet at the main entrance to station around noon tomorrow. Expected on Thursday morning before the shop opens._
- `deepgram_live` / `overlap_2spk_2s` WER 24%: _I think we should meet at the main entrance The delivery is from the warehouse is expected on Thursday morning before the shop opens._
- `or:nvidia/parakeet-tdt-0.6b-v3` / `overlap_2spk_2s` WER 21%: _I think we should meet at the main entrance. The delivery from the warehouse is expected on Thursday morning, before the shop opens._
- `parakeet_mlx` / `overlap_2spk_2s` WER 21%: _I think we should meet at the main entrance. The delivery from the warehouse is expected on Thursday morning, before the shop opens._
- `parakeet_mlx` / `noisy_cafe_babble_snr5` WER 8%: _Okay everyone, what are we ordering today? I will have a flat white and a bummer market. Just a black tea for me, thank you. Can I get a nice platy with both mi_