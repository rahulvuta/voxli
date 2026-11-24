import httpx
import pytest
from fastapi.testclient import TestClient

from voxli import tts
from voxli.server import app

Client = httpx.AsyncClient  # real class, captured before patching


@pytest.fixture
def provider(monkeypatch):
    """Mock Deepgram: provider.handler decides the response; provider.calls records requests."""
    tts._cache.clear()
    monkeypatch.setattr(tts, "DEEPGRAM_API_KEY", "test-key")
    monkeypatch.setattr(tts, "_client", None)
    state = type("P", (), {"calls": [], "handler": staticmethod(lambda r: httpx.Response(200, content=b"MP3"))})()

    def handle(request):
        state.calls.append(request)
        return state.handler(request)

    monkeypatch.setattr(tts.httpx, "AsyncClient", lambda **kw: Client(transport=httpx.MockTransport(handle), **kw))
    return state


c = TestClient(app)


def test_voices():
    j = c.get("/api/tts/voices").json()
    assert 8 <= len(j["voices"]) <= 12
    assert j["default"] in {v["id"] for v in j["voices"]}
    assert all(set(v) == {"id", "name", "description", "accent", "gender"} for v in j["voices"])


def test_ok_and_request_shape(provider):
    r = c.post("/api/tts", json={"text": "  Hello  ", "voice": "aura-2-draco-en"})
    assert r.status_code == 200 and r.headers["content-type"] == "audio/mpeg" and r.content == b"MP3"
    req = provider.calls[0]
    assert req.url.params["model"] == "aura-2-draco-en" and req.url.params["encoding"] == "mp3"
    assert req.headers["authorization"] == "Token test-key"
    assert b'"Hello"' in req.content  # trimmed


def test_null_voice_uses_default(provider):
    assert c.post("/api/tts", json={"text": "hi", "voice": None}).status_code == 200
    assert provider.calls[0].url.params["model"] == tts.DEFAULT_VOICE


@pytest.mark.parametrize("body", [{}, {"text": ""}, {"text": "   "}, {"text": "x" * 501}, {"text": 5}, {"text": "hi", "voice": "nope"}])
def test_bad_input_400(provider, body):
    r = c.post("/api/tts", json=body)
    assert r.status_code == 400 and "error" in r.json()
    assert not provider.calls


def test_500_chars_ok(provider):
    assert c.post("/api/tts", json={"text": "x" * 500}).status_code == 200


def test_cache(provider):
    for _ in range(3):
        c.post("/api/tts", json={"text": "Can you repeat that?"})
    assert len(provider.calls) == 1
    c.post("/api/tts", json={"text": "Can you repeat that?", "voice": "aura-2-aries-en"})
    assert len(provider.calls) == 2  # different voice, different entry


def test_cache_lru_bound(provider):
    for i in range(tts.CACHE_SIZE + 5):
        c.post("/api/tts", json={"text": f"phrase {i}"})
    assert len(tts._cache) == tts.CACHE_SIZE


def test_provider_error_502_not_cached(provider):
    provider.handler = lambda r: httpx.Response(401, json={"err": "bad key test-key"})
    r = c.post("/api/tts", json={"text": "hi"})
    assert r.status_code == 502 and "test-key" not in r.text
    assert not tts._cache


def test_timeout_503(provider):
    def boom(r):
        raise httpx.ReadTimeout("slow")
    provider.handler = boom
    assert c.post("/api/tts", json={"text": "hi"}).status_code == 503


def test_unreachable_503(provider):
    def boom(r):
        raise httpx.ConnectError("down")
    provider.handler = boom
    assert c.post("/api/tts", json={"text": "hi"}).status_code == 503


def test_no_key_503(provider, monkeypatch):
    monkeypatch.setattr(tts, "DEEPGRAM_API_KEY", "")
    assert c.post("/api/tts", json={"text": "hi"}).status_code == 503


def test_malformed_json_400(provider):
    assert c.post("/api/tts", content=b"{nope", headers={"content-type": "application/json"}).status_code == 400
