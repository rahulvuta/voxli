"""Deepgram Aura-2 text-to-speech. Returns MP3 bytes; never logs or returns the API key."""
from collections import OrderedDict

import httpx

from .config import DEEPGRAM_API_KEY

URL = "https://api.deepgram.com/v1/speak"
TIMEOUT_S = 6.0
CACHE_SIZE = 64
DEFAULT_VOICE = "aura-2-luna-en"

# (id, name, accent, gender, description)
_VOICES = [
    ("aura-2-luna-en", "Luna", "American", "feminine", "Friendly and natural, a young adult voice that sounds like a chat with a friend."),
    ("aura-2-vesta-en", "Vesta", "American", "feminine", "Natural, patient and empathetic, easy to listen to."),
    ("aura-2-athena-en", "Athena", "American", "feminine", "Calm, smooth and mature, unhurried."),
    ("aura-2-aries-en", "Aries", "American", "masculine", "Warm, energetic and caring."),
    ("aura-2-orion-en", "Orion", "American", "masculine", "Approachable, calm and polite."),
    ("aura-2-atlas-en", "Atlas", "American", "masculine", "Mature, friendly and confident, with an approachable feel."),
    ("aura-2-draco-en", "Draco", "British", "masculine", "Warm, trustworthy baritone with a British accent."),
    ("aura-2-pandora-en", "Pandora", "British", "feminine", "Smooth, calm and melodic with a British accent."),
    ("aura-2-hyperion-en", "Hyperion", "Australian", "masculine", "Caring, warm and empathetic with an Australian accent."),
    ("aura-2-theia-en", "Theia", "Australian", "feminine", "Expressive, polite and sincere with an Australian accent."),
    ("aura-2-amalthea-en", "Amalthea", "Filipino", "feminine", "Cheerful, engaging and natural, a young adult voice."),
]
VOICES = [dict(zip(("id", "name", "accent", "gender", "description"), v)) for v in _VOICES]
VOICE_IDS = {v["id"] for v in VOICES}

_cache: OrderedDict[tuple[str, str], bytes] = OrderedDict()


class TTSError(Exception):
    """Provider failed; `status` is the HTTP status to return (502 or 503)."""

    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


_client: httpx.AsyncClient | None = None  # reused: a fresh TLS connection per reply cost ~0.3-0.5 s


def _http() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=TIMEOUT_S)
    return _client


async def synthesize(text: str, voice: str) -> bytes:
    key = (voice, text)
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]
    if not DEEPGRAM_API_KEY:
        raise TTSError("text-to-speech is not configured", 503)
    try:
        r = await _http().post(
            URL,
            params={"model": voice, "encoding": "mp3"},
            headers={"Authorization": f"Token {DEEPGRAM_API_KEY}"},
            json={"text": text},
        )
    except httpx.TimeoutException:
        raise TTSError("text-to-speech timed out", 503) from None
    except httpx.HTTPError:
        raise TTSError("text-to-speech provider unreachable", 503) from None
    if r.status_code != 200 or not r.content:
        raise TTSError(f"text-to-speech provider error ({r.status_code})", 502)
    _cache[key] = r.content
    if len(_cache) > CACHE_SIZE:
        _cache.popitem(last=False)
    return r.content
