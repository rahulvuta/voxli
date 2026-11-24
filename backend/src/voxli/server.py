"""FastAPI entrypoint. Owner: pipeline agent."""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket

from .asr.local_parakeet import warm_up
from .session import run_ws


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
