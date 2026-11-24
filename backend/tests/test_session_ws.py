import json

from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient

from voxli.session import Session, run_ws


class NoASR:
    name = "offline"

    async def start(self, on_result):
        pass

    async def feed(self, pcm=b""):
        pass

    async def stop(self):
        pass


def client():
    app = FastAPI()

    @app.websocket("/ws")
    async def ws(w: WebSocket):
        await w.accept()
        await run_ws(w, lambda send, channels: Session(send, channels, asr=NoASR()))
    return TestClient(app)


def drain_errors(ws, n):
    out = []
    while len(out) < n:
        m = json.loads(ws.receive_text())
        if m["type"] == "error":
            out.append(m["code"])
    return out


def test_malformed_messages_yield_errors_and_session_survives():
    with client().websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "hello", "sample_rate": 16000, "channels": 1}))
        assert json.loads(ws.receive_text())["type"] == "status"
        ws.send_text("not json {")
        ws.send_text("[1,2]")
        ws.send_text(json.dumps({"type": "rename_speaker"}))          # missing fields
        ws.send_text(json.dumps({"type": "nope"}))                    # unknown type
        ws.send_text(json.dumps({"type": "rename_speaker", "speaker_id": "S9", "name": "x"}))  # unknown speaker
        ws.send_bytes(b"\x00\x01\x02")                                # odd-length PCM
        assert drain_errors(ws, 6) == ["bad_message"] * 6
        ws.send_bytes(b"\x00\x00" * 160)                              # still alive afterwards
        ws.send_text(json.dumps({"type": "tts_start", "id": "1", "text": "hi"}))
        types = []
        while "utterance" not in types:
            types.append(json.loads(ws.receive_text())["type"])


def test_bad_hello_is_an_error_not_a_crash():
    for hello in ["garbage", json.dumps({"type": "hello", "sample_rate": 44100}), json.dumps({"type": "other"})]:
        with client().websocket_connect("/ws") as ws:
            ws.send_text(hello)
            assert json.loads(ws.receive_text())["code"] == "bad_hello"


def speaker_ids_before_first_utterance(ws):
    seen = []
    while True:
        m = json.loads(ws.receive_text())
        if m["type"] == "speaker":
            seen.append(m["speaker"]["id"])
        if m["type"] == "utterance":
            return seen, m


def test_you_speaker_is_announced_before_its_utterance():
    with client().websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "hello", "sample_rate": 16000, "channels": 1}))
        ws.send_text(json.dumps({"type": "tts_start", "id": "1", "text": "hi"}))
        seen, utt = speaker_ids_before_first_utterance(ws)
        assert "YOU" in seen and utt["utterance"]["speaker_id"] == "YOU"


def test_client_can_resume_a_dropped_session_by_id():
    c = client()
    hello = json.dumps({"type": "hello", "sample_rate": 16000, "channels": 1, "session_id": "abc"})
    with c.websocket_connect("/ws") as ws:
        ws.send_text(hello)
        assert json.loads(ws.receive_text())["session_id"] == "abc"
        ws.send_text(json.dumps({"type": "tts_start", "id": "1", "text": "hi"}))
        speaker_ids_before_first_utterance(ws)
    with c.websocket_connect("/ws") as ws:  # reconnect: speakers (YOU) come back without any new utterance
        ws.send_text(hello)
        types = [json.loads(ws.receive_text()) for _ in range(2)]
        assert types[0]["session_id"] == "abc"
        assert any(m["type"] == "speaker" and m["speaker"]["id"] == "YOU" for m in types)
