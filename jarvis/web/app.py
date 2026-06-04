"""FastAPI web application for Jarvis AI."""
import asyncio
import base64
import json
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

logger = logging.getLogger(__name__)

app = FastAPI(title="Jarvis AI", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_agent = None
_tts = None
_stt = None
_config = None


def init_app(agent, tts=None, stt=None, config=None):
    global _agent, _tts, _stt, _config
    _agent = agent
    _tts = tts
    _stt = stt
    _config = config


static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    tts: bool = False


@app.get("/", response_class=HTMLResponse)
async def root():
    return (Path(__file__).parent / "templates" / "index.html").read_text(encoding="utf-8")


@app.get("/api/status")
async def status():
    if not _agent:
        return {"status": "not_ready"}
    connected = await _agent.llm.check_connection()
    models = await _agent.llm.list_models() if connected else []
    stats = _agent.get_stats()
    return {
        "status": "ready" if connected else "no_ollama",
        "ollama_connected": connected,
        "models": models,
        "current_model": _agent.llm.default_model,
        "stats": stats,
        "tts_available": _tts is not None,
        "stt_available": _stt is not None,
    }


@app.post("/api/chat")
async def chat(req: ChatRequest):
    if not _agent:
        raise HTTPException(503, "Jarvis not initialized")
    response = await _agent.chat(req.message, req.session_id)
    return {"response": response, "session_id": _agent.current_session}


@app.get("/api/models")
async def list_models():
    if not _agent:
        return {"models": []}
    models = await _agent.llm.list_models()
    return {"models": models, "current": _agent.llm.default_model}


@app.post("/api/models/{model_name}")
async def set_model(model_name: str):
    if not _agent:
        raise HTTPException(503, "Not ready")
    _agent.llm.default_model = model_name
    return {"message": f"Modell auf {model_name} gesetzt"}


@app.post("/api/pull_model/{model_name}")
async def pull_model(model_name: str):
    if not _agent:
        raise HTTPException(503, "Not ready")

    async def generate():
        async for status in _agent.llm.pull_model(model_name):
            yield f"data: {json.dumps({'status': status})}\n\n"
        yield f"data: {json.dumps({'status': 'done', 'model': model_name})}\n\n"

    from fastapi.responses import StreamingResponse
    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/api/memory/stats")
async def memory_stats():
    if not _agent:
        return {}
    return _agent.get_stats()


@app.get("/api/memory/facts")
async def get_facts():
    if not _agent:
        return {"facts": []}
    return {"facts": _agent.episodic.get_facts(limit=50)}


@app.get("/api/memory/history")
async def get_history(session_id: Optional[str] = None, limit: int = 20):
    if not _agent:
        return {"history": []}
    sid = session_id or _agent.current_session
    history = _agent.episodic.get_history(sid, limit=limit) if sid else []
    return {"history": history, "session_id": sid}


@app.post("/api/new_session")
async def new_session():
    if not _agent:
        raise HTTPException(503, "Not ready")
    return {"session_id": _agent.new_session()}


@app.get("/api/todos")
async def get_todos():
    from tools.notes import list_todos
    return {"todos": list_todos()}


# ─── Sentence-streaming TTS helper ───────────────────────────────────────────

SENTENCE_END = re.compile(r'(?<=[.!?:»"\')\]])\s+|(?<=\n)\s*')


def split_into_sentences(text: str) -> list[str]:
    """Split text into sentences for progressive TTS."""
    # Split at sentence boundaries
    parts = re.split(r'(?<=[.!?])\s+(?=[A-ZÜÄÖ"\'])', text)
    # Filter: skip very short fragments and code blocks
    result = []
    for p in parts:
        p = p.strip()
        if len(p) >= 8 and not p.startswith("```") and not p.startswith("ACTION:"):
            result.append(p)
    return result if result else [text]


def clean_for_tts(text: str) -> str:
    """Remove markdown for TTS."""
    t = re.sub(r'```[\s\S]*?```', ' ', text)
    t = re.sub(r'`[^`]+`', '', t)
    t = re.sub(r'\*+([^*]+)\*+', r'\1', t)
    t = re.sub(r'#{1,6}\s+', '', t)
    t = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', t)
    t = re.sub(r'[-*•]\s+', '', t)
    t = re.sub(r'ACTION:.*', '', t)
    t = re.sub(r'THOUGHT:.*', '', t)
    t = re.sub(r'\s+', ' ', t)
    return t.strip()


async def stream_tts_sentences(websocket: WebSocket, text: str, tts):
    """Generate and send TTS audio sentence by sentence."""
    sentences = split_into_sentences(clean_for_tts(text))
    for i, sentence in enumerate(sentences):
        if not sentence.strip():
            continue
        try:
            audio_bytes = await tts.generate_audio_bytes(sentence)
            if audio_bytes:
                await websocket.send_json({
                    "type": "tts_chunk",
                    "audio": base64.b64encode(audio_bytes).decode(),
                    "format": "mp3",
                    "index": i,
                    "is_last": (i == len(sentences) - 1)
                })
                # Small pause between chunks to avoid overloading browser audio queue
                await asyncio.sleep(0.05)
        except Exception as e:
            logger.error(f"TTS chunk error: {e}")
    await websocket.send_json({"type": "tts_done"})


# ─── WebSocket endpoint ───────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    session_id = _agent.new_session() if _agent else None

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "chat")

            # ── Text- oder Voice-Chat ─────────────────────────────────
            if msg_type in ("chat", "voice_chat"):
                user_message = data.get("message", "").strip()
                use_tts = data.get("tts", False)
                if not user_message:
                    continue

                await websocket.send_json({"type": "start", "session_id": session_id})

                # Stream LLM response
                sentence_buffer = ""
                full_response = ""
                tts_queue: list[str] = []
                tts_task: Optional[asyncio.Task] = None

                async def flush_tts(text: str):
                    """Send one TTS sentence asynchronously."""
                    if not _tts or not use_tts:
                        return
                    cleaned = clean_for_tts(text).strip()
                    if len(cleaned) < 5:
                        return
                    try:
                        audio_bytes = await _tts.generate_audio_bytes(cleaned)
                        if audio_bytes:
                            await websocket.send_json({
                                "type": "tts_chunk",
                                "audio": base64.b64encode(audio_bytes).decode(),
                                "format": "mp3",
                            })
                    except Exception as e:
                        logger.error(f"TTS flush error: {e}")

                async for event in _agent.chat_stream(user_message, session_id):
                    if event["type"] == "token":
                        token = event["content"]
                        sentence_buffer += token
                        full_response += token

                        # Check for sentence boundary → flush TTS immediately
                        if use_tts and _tts:
                            match = re.search(r'([^.!?\n]{15,}[.!?])\s', sentence_buffer)
                            if match:
                                sentence = match.group(1)
                                sentence_buffer = sentence_buffer[match.end():]
                                # Fire-and-forget TTS for this sentence
                                asyncio.create_task(flush_tts(sentence))

                    await websocket.send_json(event)

                    if event["type"] == "done":
                        full_response = event.get("response", full_response)
                        # Flush remaining buffer as TTS
                        if use_tts and _tts and sentence_buffer.strip():
                            asyncio.create_task(flush_tts(sentence_buffer))

                # Send TTS-done signal after all chunks are dispatched
                if use_tts and _tts:
                    # Wait a bit for last TTS tasks to dispatch
                    await asyncio.sleep(0.3)
                    await websocket.send_json({"type": "tts_done"})

            # ── Spracheingabe: Audio → Whisper ────────────────────────
            elif msg_type == "voice_data":
                audio_b64 = data.get("audio", "")
                audio_format = data.get("format", "webm")
                if not audio_b64:
                    continue

                await websocket.send_json({"type": "stt_processing"})

                if _stt:
                    try:
                        audio_bytes = base64.b64decode(audio_b64)
                        suffix = f".{audio_format}"
                        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
                            f.write(audio_bytes)
                            tmp_path = f.name

                        text = await _stt.transcribe_file(tmp_path)
                        try:
                            os.unlink(tmp_path)
                        except Exception:
                            pass

                        if text and text.strip():
                            await websocket.send_json({"type": "transcription", "text": text.strip()})

                            # Auto-send: process as voice_chat immediately
                            use_tts = data.get("tts", True)
                            await websocket.send_json({"type": "start", "session_id": session_id, "from_voice": True})

                            sentence_buffer = ""
                            full_response = ""

                            async def flush_tts_voice(t: str):
                                cleaned = clean_for_tts(t).strip()
                                if not cleaned or len(cleaned) < 5:
                                    return
                                try:
                                    ab = await _tts.generate_audio_bytes(cleaned)
                                    if ab:
                                        await websocket.send_json({
                                            "type": "tts_chunk",
                                            "audio": base64.b64encode(ab).decode(),
                                            "format": "mp3",
                                        })
                                except Exception:
                                    pass

                            async for event in _agent.chat_stream(text.strip(), session_id):
                                if event["type"] == "token":
                                    token = event["content"]
                                    sentence_buffer += token
                                    full_response += token
                                    if use_tts and _tts:
                                        match = re.search(r'([^.!?\n]{15,}[.!?])\s', sentence_buffer)
                                        if match:
                                            sentence = match.group(1)
                                            sentence_buffer = sentence_buffer[match.end():]
                                            asyncio.create_task(flush_tts_voice(sentence))

                                await websocket.send_json(event)

                                if event["type"] == "done":
                                    full_response = event.get("response", full_response)
                                    if use_tts and _tts and sentence_buffer.strip():
                                        asyncio.create_task(flush_tts_voice(sentence_buffer))

                            if use_tts and _tts:
                                await asyncio.sleep(0.3)
                                await websocket.send_json({"type": "tts_done"})
                        else:
                            await websocket.send_json({"type": "transcription", "text": ""})

                    except Exception as e:
                        logger.error(f"STT error: {e}")
                        await websocket.send_json({"type": "stt_error", "message": str(e)})
                else:
                    await websocket.send_json({"type": "stt_unavailable"})

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
