"""Settings loaded from the repo-root .env. Never log these values."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
load_dotenv(ROOT / ".env")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")
SAMPLE_RATE = 16000
CONTEXT_MODEL = os.getenv("VOXLI_CONTEXT_MODEL", "anthropic/claude-haiku-5.5")
VOICE_MEMORY_PATH = ROOT / "backend" / "voice_memory.json"
