# Overlap separation eval (synthetic, `say` voices)

12 two-talker mixtures (4 voice pairs x overlaps [1.0, 2.0, 3.0] s, equal level). Each reference sentence is 3-4 s long, so the
overlapped region is 25-100% of the clip. cpWER = concatenated-permutation WER of both sentences vs the method's streams, transcribed with OpenRouter deepgram/nova-3.
Machine: macOS-26.1-arm64-arm-64bit (arm64); models run on MPS (PyTorch 2.15.0); the Mac was shared with other jobs, so runtimes are upper bounds.
Both separators get the whole mixture (3-6 s), the size the pipeline sends (spans are capped at 6 s).

## Clean mixtures

| method | cpWER 1 s overlap | cpWER 2 s | cpWER 3 s | cpWER all | SI-SDRi | runtime (s per audio s) |
|---|---|---|---|---|---|---|
| no separation | 24% | 54% | 51% | **43%** | 0.0 dB | 0 |
| mossformer2 | 26% | 7% | 7% | **13%** | 18.6 dB | 0.62 |
| tiger | 7% | 17% | 15% | **13%** | 15.7 dB | 1.19 |

## Reverb (RT60 ~0.4 s, own RIR per talker) + white noise at 10 dB SNR

| method | cpWER 1 s overlap | cpWER 2 s | cpWER 3 s | cpWER all | SI-SDRi | runtime (s per audio s) |
|---|---|---|---|---|---|---|
| no separation | 59% | 75% | 95% | **76%** | 0.0 dB | 0 |
| mossformer2 | 54% | 54% | 57% | **55%** | 5.5 dB | 0.60 |
| tiger | 22% | 23% | 40% | **28%** | 10.5 dB | 1.19 |

Synthetic TTS voices: real rooms, real microphones and 3+ talkers will be worse; see docs/dev-log/overlap.md.
