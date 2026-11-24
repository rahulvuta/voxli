"""FastAPI entrypoint. Owner: pipeline agent."""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import JSONResponse, Response

from .asr.local_parakeet import warm_up
from .session import run_ws
from .tts import DEFAULT_VOICE, VOICE_IDS, VOICES, TTSError, synthesize


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load the on-device fallback in the background so a failover is instant (and weights are cached).
    task = asyncio.create_task(warm_up())
    task.add_done_callback(lambda t: t.cancelled() or t.exception())  # fallback is optional; never crash startup
    yield


app = FastAPI(title="Voxli", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    await run_ws(ws)


@app.get("/api/tts/voices")
def tts_voices() -> dict:
    return {"default": DEFAULT_VOICE, "voices": VOICES}


@app.post("/api/tts")
async def tts(request: Request):
    try:
        body = await request.json()
    except ValueError:
        body = None
    body = body if isinstance(body, dict) else {}
    text, voice = body.get("text"), body.get("voice") or DEFAULT_VOICE
    text = text.strip() if isinstance(text, str) else ""
    if not 1 <= len(text) <= 500:
        return JSONResponse({"error": "text must be 1-500 characters"}, 400)
    if voice not in VOICE_IDS:
        return JSONResponse({"error": "unknown voice"}, 400)
    try:
        return Response(await synthesize(text, voice), media_type="audio/mpeg")
    except TTSError as e:
        return JSONResponse({"error": str(e)}, e.status)
