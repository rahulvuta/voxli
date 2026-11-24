"""Generate SYNTHETIC identity test clips with macOS `say` (not real human speech).

Writes eval/clips/identity/<voice>_<n>.wav (16 kHz mono) for every voice x sentence.
"""
import subprocess
import tempfile
from pathlib import Path

OUT = Path(__file__).resolve().parents[2] / "eval" / "clips" / "identity"
# Eddy/Reed (both US male) and Flo/Shelley (both US female) are the deliberately similar pairs.
VOICES = ["Samantha", "Daniel", "Karen", "Rishi", "Moira", "Tessa", "Fred", "Eddy", "Reed", "Flo", "Shelley", "Kathy", "Ralph", "Albert", "Sandy", "Junior", "Grandpa", "Rocko"]
SENTENCES = [
    "Okay.",  # very short
    "Yeah, I think that works for me.",
    "So when are we meeting tomorrow morning?",
    "I was reading about the new bus schedule, and apparently the route downtown changes next week.",
    "Can you pass the menu over here, please?",
    "Honestly, I did not expect the coffee shop to be this crowded on a Tuesday afternoon.",
    "Let me check my calendar and I will get back to you by tonight.",
    "That sounds great, thank you so much for helping me out with this.",
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for v in VOICES:
        for i, text in enumerate(SENTENCES):
            wav = OUT / f"{v}_{i}.wav"
            if wav.exists():
                continue
            with tempfile.NamedTemporaryFile(suffix=".aiff") as t:
                subprocess.run(["say", "-v", v, "-o", t.name, text], check=True)
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", t.name, "-ar", "16000", "-ac", "1", str(wav)], check=True)
    print(f"{len(list(OUT.glob('*.wav')))} clips in {OUT}")


if __name__ == "__main__":
    main()
