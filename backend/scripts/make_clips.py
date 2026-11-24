"""Generate SYNTHETIC test clips (macOS `say` voices) + ground truth -> eval/clips/manifest.json.

All speech is text-to-speech, NOT real people. Results on these clips are an easier,
cleaner proxy than real conversation; the docs say so everywhere.

    cd backend && uv run python scripts/make_clips.py

Output (wavs are gitignored, regenerate with this script; manifest.json is committed):
  eval/clips/<id>.wav           16 kHz, mono (stereo for the DOA clips)
  eval/clips/stems/<id>__<spk>.wav   clean per-speaker stems for overlap clips (SI-SDR reference)
  eval/clips/manifest.json
Times in the manifest are seconds from clip start.

Stereo convention (DOA clips): channel 0 = LEFT mic, channel 1 = RIGHT mic, spacing 0.14 m,
c = 343 m/s. Angle is -90 (hard left) .. +90 (hard right), 0 = front. A source on the right
reaches the right mic first, so the LEFT channel is delayed by d*sin(theta)/c. Pure inter-channel
time delay only (no level difference, no reverb) -> an idealised case.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

SR = 16000
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "eval" / "clips"
STEMS = OUT / "stems"
MIC_SPACING_M = 0.14
SPEED_OF_SOUND = 343.0
TARGET_RMS = 0.07  # ~ -23 dBFS per voice before mixing
rng = np.random.default_rng(1234)

# speaker id -> macOS voice (distinct accents/genders so identity has something to separate)
VOICES = {"A": "Samantha", "B": "Daniel", "C": "Karen", "D": "Rishi", "E": "Tessa", "F": "Fred"}

_cache: dict[tuple[str, str], np.ndarray] = {}


def tts(voice: str, text: str) -> np.ndarray:
    """Speak `text`, return float32 mono 16 kHz with leading/trailing silence trimmed, RMS-normalised."""
    key = (voice, text)
    if key in _cache:
        return _cache[key]
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.wav"
        subprocess.run(["say", "-v", voice, "--file-format=WAVE", "--data-format=LEI16@16000", "-o", str(p), text],
                       check=True)
        x, sr = sf.read(p, dtype="float32")
    assert sr == SR
    idx = np.where(np.abs(x) > 0.01)[0]
    x = x[idx[0]: idx[-1] + 1] if len(idx) else x
    x = x * (TARGET_RMS / (np.sqrt(np.mean(x**2)) + 1e-9))
    _cache[key] = x.astype(np.float32)
    return _cache[key]


def place(turns, total_pad=0.4):
    """turns: list of dict(spk, text, gap=seconds after previous turn's END (negative = starts early),
    or at=absolute start). Returns (mix, segments, stems)."""
    segs, cursor = [], total_pad
    for t in turns:
        x = tts(VOICES[t["spk"]], t["text"])
        start = t["at"] if "at" in t else max(0.0, cursor + t.get("gap", 0.35))
        segs.append({"speaker": t["spk"], "text": t["text"], "start": round(start, 3),
                     "end": round(start + len(x) / SR, 3), "_x": x, **({"note": t["note"]} if "note" in t else {})})
        cursor = start + len(x) / SR
    n = int((cursor + total_pad) * SR)
    stems: dict[str, np.ndarray] = {}
    for s in segs:
        st = stems.setdefault(s["speaker"], np.zeros(n, np.float32))
        i = int(s["start"] * SR)
        st[i: i + len(s["_x"])] += s["_x"]
    mix = sum(stems.values())
    return mix.astype(np.float32), segs, stems


def overlaps_of(segs):
    out = []
    for i, a in enumerate(segs):
        for b in segs[i + 1:]:
            s, e = max(a["start"], b["start"]), min(a["end"], b["end"])
            if e - s > 0.05:
                out.append({"start": round(s, 3), "end": round(e, 3), "speakers": [a["speaker"], b["speaker"]]})
    return out


def pink(n):
    f = np.fft.rfft(rng.standard_normal(n))
    f[1:] /= np.sqrt(np.arange(1, len(f)))
    f[0] = 0
    x = np.fft.irfft(f, n)
    return (x / np.std(x)).astype(np.float32)


BABBLE_LINES = [
    "Did you see the game last night, I could not believe the ending at all",
    "We should really book the tickets before the prices go up again next week",
    "She said the train was delayed so she would be about twenty minutes late",
    "I think the report needs another look before it goes to the whole team",
    "Honestly the coffee here is better than the place we went to last time",
    "My brother just moved to a new apartment near the river and loves it",
    "Can you pass the menu over, I still have not decided what to order yet",
    "They told me the package would arrive on Tuesday but nothing has shown up",
]


def babble(n, nvoices=5):
    """Sum of several different TTS voices reading unrelated text (cocktail-party style, intelligible-ish)."""
    voices = ["Fred", "Ralph", "Kathy", "Moira", "Reed", "Sandy", "Shelley", "Eddy"][:nvoices]
    mix = np.zeros(n, np.float32)
    for k, v in enumerate(voices):
        t, line = 0, rng.permutation(BABBLE_LINES)
        j = 0
        while t < n:
            x = tts(v, str(line[j % len(line)]))
            gap = int(rng.uniform(0.1, 0.8) * SR)
            seg = x[: n - t]
            mix[t: t + len(seg)] += seg
            t += len(x) + gap
            j += 1
    return mix


def mix_at_snr(clean, noise, snr_db):
    """SNR measured on active frames of `clean` (frames >-40 dB re peak-frame) so silence does not inflate it."""
    fr = clean[: len(clean) // 320 * 320].reshape(-1, 320)
    e = np.mean(fr**2, axis=1)
    p_sig = np.mean(e[e > e.max() * 1e-4])
    noise = noise[: len(clean)]
    g = np.sqrt(p_sig / (10 ** (snr_db / 10)) / (np.mean(noise**2) + 1e-12))
    return clean + g * noise


def frac_delay(x, delay_s):
    """Delay by (possibly fractional) seconds using an FFT phase shift."""
    n = len(x) + int(abs(delay_s) * SR) + 8
    X = np.fft.rfft(x, n)
    X *= np.exp(-2j * np.pi * np.fft.rfftfreq(n) * delay_s * SR)
    return np.fft.irfft(X, n)[: len(x)].astype(np.float32)


def stereo_from_stems(stems, angles):
    n = len(next(iter(stems.values())))
    L, R = np.zeros(n, np.float32), np.zeros(n, np.float32)
    for spk, st in stems.items():
        tau = MIC_SPACING_M * np.sin(np.deg2rad(angles[spk])) / SPEED_OF_SOUND
        if tau >= 0:  # right of centre: left channel lags
            R += st
            L += frac_delay(st, tau)
        else:         # left of centre: right channel lags
            L += st
            R += frac_delay(st, -tau)
    return np.stack([L, R], axis=1)


def write(clip_id, audio, meta, stems=None, segs=None):
    peak = np.max(np.abs(audio))
    if peak > 0.95:
        audio = audio * (0.95 / peak)
        if stems:
            stems = {k: v * (0.95 / peak) for k, v in stems.items()}
    OUT.mkdir(parents=True, exist_ok=True)
    sf.write(OUT / f"{clip_id}.wav", audio, SR, subtype="PCM_16")
    entry = {"id": clip_id, "file": f"{clip_id}.wav", "synthetic": True, "sample_rate": SR,
             "channels": 1 if audio.ndim == 1 else 2, "duration_s": round(len(audio) / SR, 2), **meta}
    if segs is not None:
        entry["segments"] = [{k: v for k, v in s.items() if not k.startswith("_")} for s in segs]
        entry["overlaps"] = overlaps_of(segs)
        entry["reference_text"] = " ".join(s["text"] for s in sorted(segs, key=lambda s: s["start"]))
    if stems:
        STEMS.mkdir(exist_ok=True)
        entry["stems"] = {}
        for spk, st in stems.items():
            f = f"stems/{clip_id}__{spk}.wav"
            sf.write(OUT / f, st[: len(audio)], SR, subtype="PCM_16")
            entry["stems"][spk] = f
    return entry


def main():
    clips = []

    # (a) 2-speaker turn-taking ------------------------------------------------------------------
    t_a = [
        ("A", "Hi, did you manage to find the restaurant okay?"),
        ("B", "Yes, it was easy. The bus stops right outside the door."),
        ("A", "Great. I booked a table for seven thirty, so we have a little time."),
        ("B", "Perfect. Should we order a starter to share while we wait?"),
        ("A", "Good idea. I heard the mushroom soup here is excellent."),
        ("B", "Then I will have the soup, and maybe a green salad on the side."),
        ("A", "Sounds good. I will ask the waiter to bring two glasses of water."),
        ("B", "Thank you. By the way, did you get my message about Friday?"),
    ]
    mix, segs, stems = place([{"spk": s, "text": t} for s, t in t_a])
    clips.append(write("turns_2spk", mix, {
        "kind": "turn_taking", "description": "2 speakers, clean turn-taking, no overlap (ordinary case 1)",
        "speakers": {k: VOICES[k] for k in "AB"}}, segs=segs))
    turns_2spk_clean, turns_2spk_stems = mix, stems

    # (b) 4-speaker cafe with an interruption ------------------------------------------------------
    t_b = [
        {"spk": "A", "text": "Okay everyone, what are we ordering today?"},
        {"spk": "B", "text": "I will have a flat white and a blueberry muffin, please."},
        {"spk": "C", "text": "Just a black tea for me, thank you."},
        {"spk": "D", "text": "Can I get an iced latte with oat milk and two shots?"},
        {"spk": "A", "text": "And I will take a cappuccino. Does anyone want to share a croissant?"},
        {"spk": "C", "text": "Yes, I would love half of one, but only if it is warm.", "gap": 0.3},
        {"spk": "B", "text": "Did you all see the new exhibition that opens on Saturday at the museum?", "gap": 0.5},
        {"spk": "D", "text": "Not yet, I heard the tickets cost twenty five dollars each.",
         "gap": -1.3, "note": "interrupts previous speaker (starts ~1.3 s before B finishes)"},
        {"spk": "A", "text": "That seems like a lot, but I would still go if we went together."},
        {"spk": "C", "text": "Let us check the opening hours first. I think they close at five."},
        {"spk": "B", "text": "I can look it up right now on my phone.", "gap": 0.25},
        {"spk": "D", "text": "While you do that, could someone please pass the sugar?"},
        {"spk": "A", "text": "Here you go. So, is Saturday afternoon good for everybody?"},
        {"spk": "C", "text": "Saturday works for me, as long as we leave before four."},
        {"spk": "B", "text": "They are open until six, so that should be fine for all of us."},
        {"spk": "D", "text": "Great, then it is settled. I will book four tickets tonight."},
    ]
    mix, segs, stems = place(t_b)
    cafe_mix, cafe_segs, cafe_stems = mix, segs, stems
    clips.append(write("cafe_4spk", mix, {
        "kind": "multi_speaker", "description": "4 speakers, cafe-style, one interruption (D cuts in on B)",
        "speakers": {k: VOICES[k] for k in "ABCD"},
        "interruptions": [{"interrupter": "D", "interrupted": "B"}]}, segs=segs))

    # (c) overlap clips: 2 voices simultaneous 1/2/3 s -----------------------------------------------
    sa = "I think we should meet at the main entrance of the station around noon tomorrow."
    sb = "The delivery from the warehouse is expected on Thursday morning, before the shop opens."
    for ov in (1.0, 2.0, 3.0):
        mix, segs, stems = place([{"spk": "A", "text": sa}, {"spk": "B", "text": sb, "gap": -ov}])
        # make the overlap precise: B starts exactly `ov` s before A ends
        a_end = segs[0]["end"]
        segs[1]["start"] = round(a_end - ov, 3)
        segs[1]["end"] = round(segs[1]["start"] + len(segs[1]["_x"]) / SR, 3)
        n = int((segs[1]["end"] + 0.4) * SR)
        stA = np.zeros(n, np.float32); stB = np.zeros(n, np.float32)
        stA[int(segs[0]["start"] * SR): int(segs[0]["start"] * SR) + len(segs[0]["_x"])] = segs[0]["_x"]
        i = int(segs[1]["start"] * SR); stB[i: i + len(segs[1]["_x"])] = segs[1]["_x"]
        clips.append(write(f"overlap_2spk_{int(ov)}s", stA + stB, {
            "kind": "overlap", "overlap_s": ov,
            "description": f"A and B talk simultaneously for {ov:.0f} s (2 voices; stems provided for SI-SDR)",
            "speakers": {k: VOICES[k] for k in "AB"}}, stems={"A": stA, "B": stB}, segs=segs))
    # a same-gender, harder overlap (A=Samantha, E=Tessa both female) at 2 s
    sc = "My flight lands at nine fifteen, so I will take a taxi straight to the hotel."
    mix, segs, stems = place([{"spk": "A", "text": sa}, {"spk": "E", "text": sc, "gap": -2.0}])
    segs[1]["start"] = round(segs[0]["end"] - 2.0, 3)
    segs[1]["end"] = round(segs[1]["start"] + len(segs[1]["_x"]) / SR, 3)
    n = int((segs[1]["end"] + 0.4) * SR)
    stA = np.zeros(n, np.float32); stE = np.zeros(n, np.float32)
    stA[int(segs[0]["start"] * SR): int(segs[0]["start"] * SR) + len(segs[0]["_x"])] = segs[0]["_x"]
    i = int(segs[1]["start"] * SR); stE[i: i + len(segs[1]["_x"])] = segs[1]["_x"]
    clips.append(write("overlap_2spk_2s_samegender", stA + stE, {
        "kind": "overlap", "overlap_s": 2.0, "description": "two female voices overlap 2 s (harder to separate)",
        "speakers": {"A": VOICES["A"], "E": VOICES["E"]}}, stems={"A": stA, "E": stE}, segs=segs))

    # (d) noisy versions -------------------------------------------------------------------------------
    for snr in (10, 5):
        noisy = mix_at_snr(cafe_mix, babble(len(cafe_mix)), snr)
        clips.append(write(f"noisy_cafe_babble_snr{snr}", noisy, {
            "kind": "noisy", "noise": "babble (5 unrelated TTS voices)", "snr_db": snr,
            "description": f"cafe_4spk + babble noise at {snr} dB SNR (SNR on speech-active frames)",
            "speakers": {k: VOICES[k] for k in "ABCD"}, "base_clip": "cafe_4spk"}, segs=cafe_segs))
    noisy = mix_at_snr(turns_2spk_clean, pink(len(turns_2spk_clean)), 10)
    _, segs2, _ = place([{"spk": s, "text": t} for s, t in t_a])
    clips.append(write("noisy_turns_pink_snr10", noisy, {
        "kind": "noisy", "noise": "pink noise", "snr_db": 10,
        "description": "turns_2spk + pink noise at 10 dB SNR",
        "speakers": {k: VOICES[k] for k in "AB"}, "base_clip": "turns_2spk"}, segs=segs2))

    # (e) stereo clips for DOA --------------------------------------------------------------------------
    angles = {"A": -60.0, "B": 60.0}
    st = stereo_from_stems(turns_2spk_stems, angles)
    clips.append(write("stereo_2spk_lr", st, {
        "kind": "stereo_doa", "mic_spacing_m": MIC_SPACING_M, "speed_of_sound": SPEED_OF_SOUND,
        "angles_deg": angles, "convention": "ch0=left mic, ch1=right mic; +deg = source on RIGHT; "
        "left channel delayed for right sources (ITD only, no level difference)",
        "description": "turns_2spk with A at -60 deg (left) and B at +60 deg (right)",
        "speakers": {k: VOICES[k] for k in "AB"}, "base_clip": "turns_2spk"}, segs=segs2))
    angles4 = {"A": -75.0, "B": -25.0, "C": 25.0, "D": 75.0}
    st4 = stereo_from_stems(cafe_stems, angles4)
    clips.append(write("stereo_cafe_4spk", st4, {
        "kind": "stereo_doa", "mic_spacing_m": MIC_SPACING_M, "speed_of_sound": SPEED_OF_SOUND,
        "angles_deg": angles4, "convention": "same as stereo_2spk_lr",
        "description": "cafe_4spk with 4 speakers at -75/-25/+25/+75 deg",
        "speakers": {k: VOICES[k] for k in "ABCD"}, "base_clip": "cafe_4spk"}, segs=cafe_segs))
    clips.append(write("stereo_dupmono", np.stack([turns_2spk_clean, turns_2spk_clean], axis=1), {
        "kind": "stereo_doa", "angles_deg": None,
        "description": "2 identical channels (what iPhone Safari delivers): DOA must return None",
        "speakers": {k: VOICES[k] for k in "AB"}, "base_clip": "turns_2spk"}, segs=segs2))

    # (f) name clips ------------------------------------------------------------------------------------
    VOICES["S"] = "Moira"  # Sarah's voice
    mix, segs, _ = place([
        {"spk": "S", "text": "Hi everyone, I'm Sarah. I just joined the team last week."},
        {"spk": "B", "text": "Welcome Sarah, great to have you with us."},
        {"spk": "S", "text": "Thank you. I am still finding my way around the building."},
        {"spk": "B", "text": "No problem, I can show you the kitchen after the meeting."},
        {"spk": "S", "text": "That would be really helpful, thanks."},
    ])
    clips.append(write("selfintro_sarah", mix, {
        "kind": "names", "description": "self-introduction: Moira voice says 'I'm Sarah' (expected: S -> Sarah, auto-applied)",
        "speakers": {"S": VOICES["S"], "B": VOICES["B"]},
        "name_events": [{"speaker": "S", "name": "Sarah", "kind": "self_intro", "at_segment": 0}]}, segs=segs))
    VOICES["M"] = "Rishi"
    mix, segs, _ = place([
        {"spk": "A", "text": "Everyone, this is my friend Marcus. He is visiting from Chicago."},
        {"spk": "M", "text": "Hello all, nice to meet you. Thanks for having me."},
        {"spk": "B", "text": "Welcome Marcus. Did you have a good flight?"},
        {"spk": "M", "text": "Long, but fine. I am a little tired now, honestly."},
        {"spk": "A", "text": "Let us get you a coffee then."},
    ])
    clips.append(write("introduced_marcus", mix, {
        "kind": "names", "description": "third-party introduction (expected: suggestion Marcus -> next different speaker M, "
        "not auto-applied); 'I am a little tired' is a negative (no name)",
        "speakers": {"A": VOICES["A"], "M": VOICES["M"], "B": VOICES["B"]},
        "name_events": [{"speaker": "M", "name": "Marcus", "kind": "introduced", "at_segment": 0}]}, segs=segs))

    manifest = {
        "_readme": "ALL CLIPS ARE SYNTHETIC: macOS `say` text-to-speech voices, mixed by backend/scripts/make_clips.py. "
                   "No real people, no real recordings. Times are seconds from clip start. Paths relative to eval/clips/. "
                   "Wavs are gitignored; regenerate with `cd backend && uv run python scripts/make_clips.py`.",
        "synthetic": True, "sample_rate": SR, "generator": "backend/scripts/make_clips.py",
        "voices": VOICES, "clips": clips}
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"wrote {len(clips)} clips to {OUT}")
    for c in clips:
        print(f"  {c['id']:32s} {c['duration_s']:6.1f}s ch={c['channels']} {c['kind']}")


if __name__ == "__main__":
    main()
