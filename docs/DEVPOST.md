# Voxli: Devpost draft

> Status: DRAFT. Numbers marked **[measured]** come from scripts in this repo (see `docs/EVIDENCE.md`). Anything marked **TODO(...)** is not measured yet and must be filled or deleted before submission. All test audio is synthetic text-to-speech; do not describe it as real speech.

**Tagline:** Group-conversation captions that tell you *who* said it, show *both* people when they talk over each other, and never rewrite a word.

---

## 1. The problem and who it is for  (rubric V1)

**Need.** WHO estimates that over 5% of the world's population (430 million people) needs rehabilitation for disabling hearing loss, projected to pass 700 million (about 1 in 10) by 2050; it lists "social isolation, loneliness and stigma" and limits on communication among the effects of unaddressed hearing loss ([WHO fact sheet](https://www.who.int/news-room/fact-sheets/detail/deafness-and-hearing-loss), read 2026-11-24).

**Why groups are the hard case.** A 2025 *American Journal of Audiology* paper on small-group conversation research states that group conversations, especially in noise, are among the most challenging situations for people with hearing loss, and notes less predictable speaker sequences and more competition for the floor than in two-person talk (Nicoras et al., [PMC12151282](https://pmc.ncbi.nlm.nih.gov/articles/PMC12151282)). The same paper cites prior work on withdrawal behaviour in hearing loss. (Note: that paper does not use the phrase "dinner table syndrome"; that is an advocacy term, see [RNID](https://rnid.org.uk/?p=7760) and [UCL](https://www.ucl.ac.uk/news/headlines/2015/sep/real-reason-you-cant-hear-conversation-round-dinner-table), which we did not verify beyond their titles.)

**What DHH caption users say they need.** In interviews and design probes with 15 DHH participants, McDonnell et al. (CSCW 2021, [project page](https://makeabilitylab.cs.washington.edu/project/smallgroupcaptioning)) found that experience depended on social, environmental, and technical factors, including how far captions lag behind speech, and that participants wanted feedback on speaker identity, speech rate, and volume. A CHI 2023 follow-up on mixed hearing/DHH groups reports a continued need for speaker identification ([McDonnell et al., CHI 2023 PDF](https://makeabilitylab.cs.washington.edu/media/publications/McDonnell_EasierOrHarderDependingOnWhoTheHearingPersonIsCodesigningVideoconferencingToolsForSmallGroupsWithMixedHearingStatus_CHI2023.pdf); we read only the search-result abstract, **TODO(eval): open the PDF and confirm the exact finding/quote before submitting**).

**Listening fatigue.** Hearing-impaired adults report high levels of listening effort and fatigue in everyday life (Alhanbali, Dawes, Lloyd & Munro, *Ear & Hearing* 2017;38(1):e39-e48, [PubMed 27541332](https://pubmed.ncbi.nlm.nih.gov/27541332/)). Evidence is mostly self-report: a systematic review of 20 studies (Holman, Drummond & Naylor, *Ear & Hearing* 42(1):1-11, [PMC7757744](https://pmc.ncbi.nlm.nih.gov/articles/PMC7757744)) could not statistically confirm that hearing loss increases fatigue because the studies were too heterogeneous. We therefore claim only that fatigue is commonly *self-reported*, and give no prevalence number.

**Realistic use example.** Four friends at a cafe table, one of them hard of hearing, phone propped against the sugar bowl. Today she watches lips, guesses who is talking, and loses the thread when two people laugh and talk over each other. With Voxli she reads four colour-and-shape-coded lanes, sees "Sarah" appear after Sarah says "I'm Sarah", sees a "?" when the system is unsure instead of a wrong name, and when two people overlap she sees both sentences side by side.

---

## 2. How Voxli compares with tools people already use  (rubric V2)

Everything below is what each vendor's *own page* says, read 2026-11-24. "Not documented" means we could not find it on the page, not that the product cannot do it.

| | Google Live Transcribe | Ava (SpeakerID, mobile beta) | Otter.ai | **Voxli** |
|---|---|---|---|---|
| Speaker labels in live captions | Support page describes captions of speech and sounds; speaker labels **not documented** ([support](https://support.google.com/accessibility/android/answer/9158064?hl=en)). Google's 2019 engineering post lists "speaker-separation" only as possible future work ([blog](https://research.google/blog/real-time-continuous-transcription-with-live-transcribe/)) | Distinguishes speakers by caption colour, up to 5 speakers; user names them; Premium-only on mobile; "performs best with clear audio input" ([help](https://help.ava.me/en/articles/9715516-speakerid-for-live-captioning-on-mobile-beta)) | Help center: generic "Speaker #" tags until a person is tagged, then voice profiles recognise them in later conversations ([help](https://help.otter.ai/hc/en-us/articles/360048465453-Tagging-speaker-names-in-a-conversation)) | Identity from voice embeddings, stable all session; "?" when uncertain |
| Overlapping speech | not documented | not addressed on the help page | Third-party reviews report misattribution when people talk over each other (reviews, not Otter's docs) | Overlapping spans separated, both lines shown |
| Names | n/a | manual | manual tagging / calendar names | auto from "I'm Sarah" (undoable); introductions become confirm-chips |
| Direction cue | no | not documented | no | radar ring when the device gives true stereo (iPhone Safari currently does not) |
| AI never changes words | n/a | n/a | n/a | enforced by a verbatim guard on model output |

**Specific benefit:** Voxli's claim is not better raw word accuracy (every engine we tested is near-perfect on clean synthetic speech, see below). It is the *group* layer: stable identities, honest uncertainty, overlap, and structure. **Measured (synthetic voices, EVIDENCE.md sections 4 and 5):** (1) overlapped speech: cpWER 43% with plain ASR vs 13% after separation on clean mixtures, and 76% vs 28% (TIGER) with reverb and noise; (2) identity: on four distinct voices Deepgram's diarization gave 8 confident wrong labels in 32 turns and Voxli gave 0 (it showed "?" for about a third of the turns instead), but on similar voices Voxli was worse (6 vs 1 confident-wrong). So the supported claim is "fewer confident wrong labels on distinct voices, at the cost of coverage", not "more accurate".

---

## 3. What Voxli does and how it is feasible for users  (rubric R1, V3)

Open a web page on a phone (no install), allow the mic, place the phone on the table. Words appear as they are spoken, in per-speaker lanes; tap a speaker to rename or merge; "Catch me up" shows verbatim lines first with a labelled AI summary; a reply bar speaks typed text aloud (and mutes identity during our own speech), with quick phrases and suggested replies that are never sent automatically. Text size, high contrast, colour-blind-safe palette, reduced motion.

**Feasibility.** Runs on a laptop/Mac backend + any phone browser over local Wi-Fi. Measured per-hour ASR cost is cents: Deepgram live Nova-3 list price $0.0048 per minute (about $0.29 per hour; diarization add-on not used) ([Deepgram pricing](https://deepgram.com/pricing)); batch re-transcription of overlap spans via OpenRouter costs less than a cent per hour of audio in our tests **[measured, EVIDENCE.md section 1]**. On-device Parakeet is the free offline fallback.
**Limits we state openly:** needs internet for the best path; audio goes to cloud services (see README privacy model); not tested with DHH users yet. **TODO(lead): if any informal user feedback is collected, add it here with number of people and what they did, otherwise leave this sentence.**

---

## 4. How we used AI  (rubric A1-A4)

**AI in the product.**

- **ASR:** Deepgram Nova-3 live (streaming, interim words); on-device NVIDIA Parakeet-TDT 0.6B v3 (MLX) as failover. *Why these:* compared five options on synthetic clips for WER, latency, and cost (table below). Only Deepgram live streams interim words in our setup; Parakeet local costs nothing and is within about 1 point of WER on clean speech.
- **Speaker identity (our project-specific design choice, A2):** ECAPA-TDNN voice embeddings (chosen over WeSpeaker: EER 3.1% vs 6.0%) + online clustering with three outcomes (match / new speaker / uncertain). Vendor diarization labels are used only as a hint. Result vs Deepgram diarization: see section 2 above.
- **Overlap separation (A2/A3):** detection of overlap spans, then TIGER vs MossFormer2 separation; each stream re-transcribed. TIGER chosen: equal to MossFormer2 on clean mixtures (13% cpWER each) but 28% vs 55% under reverb + noise, at 1.2 vs 0.6 s per audio second. In the end-to-end test the detector missed one overlap and raised false alarms on babble noise (limits).
- **Claude (Haiku 5.5 vs Sonnet 5.5) via OpenRouter (A1/A2):** only metadata (reply-to, interrupts, thread, incomplete, names). Verbatim guard rejects any output that is not a valid id/label/name found in the evidence. Names: 40-item hand-labelled synthetic set, both models 28/28 precision and recall; Haiku about $0.017 vs Sonnet about $0.27 for the run **[measured by context agent, eval/out/context.md]**, so Haiku is the default.

**ASR comparison [measured, `eval/out/asr.md`, synthetic TTS clips, 4.7 audio-minutes, one run each]:**

| engine | mean WER, 8 clips | WER on 3 noisy clips | latency | price |
|---|---|---|---|---|
| Deepgram Nova-3 live (chosen, main) | 4.1% | 2.4% | first caption 0.44 s after speech starts, updates about every 0.9 s | $0.29/h |
| local Parakeet-TDT 0.6B v3, MLX (chosen, fallback) | 4.2% | 3.8% | batch, 0.026 s per audio-s on the Apple GPU | $0 |
| OpenRouter nova-3 batch (used for overlap streams) | 4.2% | 1.6% | 0.056 s per audio-s | $0.26/h |
| OpenRouter Parakeet v3 | 3.8% | 2.9% | 0.076 s per audio-s | $0.07/h |
| OpenRouter Whisper-large-v3-turbo (rejected) | 7.3% | 3.3% | 0.125 s per audio-s | $0.02/h |

On clean synthetic speech all engines are at 0-1% WER, so accuracy is not the differentiator; streaming, cost, privacy and failure behaviour are. Whisper turbo transcribed only one of two overlapping speakers (48% WER on the overlap clip), which is why it was rejected for the overlap step.

**Evaluation method and limits (A3).** Ground truth comes from the script that generated each clip, so references are exact, but speech is TTS, voices are few, noise is synthetic, and each cell was run once. These numbers show relative differences and that the pipeline works; they do not predict accuracy on real people in a real room.

**Checking AI-assisted development (A4).** We kept a per-agent log of what the AI wrote, how we checked it, what the check found, and whether we kept, changed, or rejected it: `docs/AI_DISCLOSURE.md`. Example from our own eval work: the AI-written clip generator had a dead, buggy duplicate function that review caught, and the AI-written ASR script used a stale Deepgram price that we caught by re-reading the pricing page; both were changed.

---

## 5. Does it work: cases and failures  (rubric R2, R3)

See `docs/EVIDENCE.md`: two ordinary cases, a repeat run, one demanding case (overlap + noise), each with expected vs actual; and two different failure causes (ASR service down -> local fallback with no lost captions; mono microphone / uncertain speaker -> detected and shown to the user).

Summary of the real-time end-to-end runs (synthetic clips, one run each): ordinary turn-taking, self-introduction and a repeat all met expectations (0% WER, 100% speaker accuracy, name "Sarah" applied automatically, repeat identical within about 50 ms). The demanding cases partly failed: with 5 dB babble noise WER stayed 6.6% and no confident wrong label was shown, but overlap detection raised 18 false alarms and the median line lag rose to 9.8 s; a clean 2 s overlap was not detected. Failure handling: killing the Deepgram connection mid-stream lost no words (100% recall), while starting with an invalid key switched to local ASR but lost about a third of the words in that run; duplicated-mono input produced no invented direction. **TODO(lead, pipeline): re-run `uv run python ../eval/run_r2.py` on the final build and update these numbers.**

---

## 6. Challenges, what we learned, what is next

- Every ASR engine, cloud and local, dropped the same two words ("not yet") in the 1.3 s interruption in our 4-speaker clip: ordinary ASR loses words exactly where people interrupt. That is the case Voxli's overlap path exists for. **[measured]**
- Deepgram live interim updates arrived about once per second in our setup, so "word by word" is really "about once a second" **[measured, EVIDENCE.md]**.
- On our M5 Mac the default MLX GPU kernels failed to load for local Parakeet until a Metal architecture override was set (CPU also works, 2.5x slower). **[observed]**
- Next: test with real DHH users and real rooms; true stereo capture on-device; more voices and languages; offline Claude-free mode.

---

## 7. Demo video script (target 3:15, hard cap 4:00)

| time | shot | voice-over / on-screen |
|---|---|---|
| 0:00-0:20 | Close-up: phone on a cafe table, four people talking, one person looking lost | "In a group conversation, captions tell you *what* was said, but not who, and they fall apart when people talk over each other." WHO stat as lower-third with source |
| 0:20-0:40 | Voxli on phone: open page, grant mic, lanes start filling | "Voxli is a web app. Open it, put the phone on the table." |
| 0:40-1:30 | MAIN FLOW (R1): screen record of the live 4-person conversation: lanes, colours/shapes, radar ring, "I'm Sarah" -> name appears, tap to rename | Narrate each feature as it happens. Say clearly: "this demo conversation is real people / synthetic clips" (whichever it is) |
| 1:30-2:00 | DEMANDING CASE: two people talk at once; both lines appear bracketed; show before/after plain ASR | Show the WER numbers from EVIDENCE.md overlay; state limits |
| 2:00-2:25 | R3 failure 1: pull Wi-Fi / bad key; status pill goes Deepgram -> Reconnecting -> Local; captions continue, nothing lost | "Failure one: the cloud service dies." |
| 2:25-2:40 | R3 failure 2: mono mic banner / "?" on uncertain speaker | "Failure two: the phone cannot tell who is speaking. Voxli says so instead of guessing." |
| 2:40-3:00 | Claude layer: reply chip, interruption connector, Catch me up (verbatim first, AI summary labelled) + reply bar speak | "Claude adds structure, never changes words: here is the guard." |
| 3:00-3:15 | AI evidence slide: ASR table, Haiku vs Sonnet, AI_DISCLOSURE checks | "What we measured, what failed, what we changed." |
| 3:15-3:25 | End card: limits (synthetic tests, no user study yet) + repo | |

Recording checklist: use real names only with consent; if clips are synthetic say so on screen; blur anything showing keys; record the failure demos in one take.

---

## Sources (all fetched 2026-11-24)

1. WHO, Deafness and hearing loss: https://www.who.int/news-room/fact-sheets/detail/deafness-and-hearing-loss
2. Nicoras et al. 2025, Am J Audiol 34(2):305-320: https://pmc.ncbi.nlm.nih.gov/articles/PMC12151282
3. McDonnell et al., CSCW 2021, Small-Group Captioning: https://makeabilitylab.cs.washington.edu/project/smallgroupcaptioning
4. McDonnell et al., CHI 2023 (PDF, abstract only read): see link above
5. Alhanbali et al. 2017: https://pubmed.ncbi.nlm.nih.gov/27541332/ (bibliographic details from search results; the PubMed page itself was not retrievable, **verify the abstract wording**); Holman et al. review: https://pmc.ncbi.nlm.nih.gov/articles/PMC7757744 (summary from search results)
6. Google Live Transcribe support: https://support.google.com/accessibility/android/answer/9158064?hl=en ; engineering blog: https://research.google/blog/real-time-continuous-transcription-with-live-transcribe/
7. Ava SpeakerID help: https://help.ava.me/en/articles/9715516-speakerid-for-live-captioning-on-mobile-beta ; product page: https://www.ava.me/speakerid
8. Otter help center, tagging speakers: https://help.otter.ai/hc/en-us/articles/360048465453-Tagging-speaker-names-in-a-conversation (page itself was blocked to our fetcher; wording from search-result excerpt, **verify**)
9. Deepgram pricing: https://deepgram.com/pricing ; OpenRouter model prices: https://openrouter.ai/api/v1/models
