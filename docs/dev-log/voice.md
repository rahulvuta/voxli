# Voice (Aura-2 TTS) dev log

Format: what AI produced -> how it was checked -> what the check found -> kept / changed / rejected.

1. **API details.** AI fetched the current Deepgram docs instead of using memory: `POST https://api.deepgram.com/v1/speak?model=aura-2-<voice>-en&encoding=mp3`, header `Authorization: Token <key>`, body `{"text": ...}`, mp3 has no container option. Checked by real calls. Found: all work, response starts with an MP3 frame header. Kept.
2. **`backend/src/voxli/tts.py`.** AI wrote an httpx async client (6 s total timeout), a 64-entry LRU keyed by (voice, text), and a `TTSError` carrying 502 (provider status/empty body) or 503 (timeout, network, missing key). Error text never includes the key or provider body. Failures are not cached. Kept.
3. **Voice list (11).** AI picked from Deepgram's model table for variety in gender, accent (American, British, Australian, Filipino) and age feel, with the warm/friendly "Luna" as default. Checked by a real synthesis call per id: all 11 returned MP3 (13-20 KB for a 47-char sentence). Not checked: how they actually sound to a listener (I cannot listen); the default is chosen from Deepgram's descriptions. Kept.
4. **Routes in `server.py`.** `GET /api/tts/voices`, `POST /api/tts` (trim, 1-500 chars, unknown voice 400, malformed JSON 400). Initial version typed the body as `dict`, so bad JSON gave FastAPI's 422 rather than the contract's 400; changed to parse the request manually. Kept after fix.
5. **Tests (`tests/test_tts.py`, 17 cases, mocked HTTP via `httpx.MockTransport`).** Cover validation, request shape/auth header, default voice, cache hit and LRU bound, 401 -> 502 without leaking the key, timeout/connect error -> 503, missing key -> 503. Full suite: 74 passed.
6. **Latency (real call, 57-59 char sentences, new connection each call).** 1.19 s and 1.29 s; a 47-char sentence across all voices 0.79-1.11 s. Cache hit: microseconds. Kept as is; a shared keep-alive client would likely save the TLS handshake but was not measured.

- Lead review: each reply opened a new HTTPS connection (agent measured 1.19–1.29 s) → reused one `httpx.AsyncClient` → re-measured warm calls 0.75–0.79 s, cached replies instant; tests updated to reset the client → **changed**.
