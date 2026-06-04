"""FastAPI web application for Jarvis AI."""
import asyncio
import base64
import json
import logging
import os
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

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


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    session_id = _agent.new_session() if _agent else None

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "chat")

            # ── Text-Chat ──────────────────────────────────────────────
            if msg_type == "chat":
                user_message = data.get("message", "").strip()
                use_tts = data.get("tts", False)
                if not user_message:
                    continue

                await websocket.send_json({"type": "start", "session_id": session_id})

                final_response = ""
                async for event in _agent.chat_stream(user_message, session_id):
                    await websocket.send_json(event)
                    if event["type"] == "done":
                        final_response = event.get("response", "")

                # TTS: generate audio on server, send base64 to browser
                if use_tts and _tts and final_response:
                    await websocket.send_json({"type": "tts_start"})
                    try:
                        audio_bytes = await _tts.generate_audio_bytes(final_response)
                        if audio_bytes:
                            audio_b64 = base64.b64encode(audio_bytes).decode()
                            await websocket.send_json({
                                "type": "tts_audio",
                                "audio": audio_b64,
                                "format": "mp3"
                            })
                        else:
                            await websocket.send_json({"type": "tts_fallback", "text": final_response})
                    except Exception as e:
                        logger.error(f"TTS error: {e}")
                        await websocket.send_json({"type": "tts_fallback", "text": final_response})

            # ── Spracheingabe: Audio → Whisper → Text ──────────────────
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
                            await websocket.send_json({
                                "type": "transcription",
                                "text": text.strip()
                            })

                            # Auto-send: direkt als Chat weiterverarbeiten
                            if data.get("auto_send", True):
                                use_tts = data.get("tts", True)
                                await websocket.send_json({
                                    "type": "start",
                                    "session_id": session_id,
                                    "from_voice": True
                                })
                                final_response = ""
                                async for event in _agent.chat_stream(text.strip(), session_id):
                                    await websocket.send_json(event)
                                    if event["type"] == "done":
                                        final_response = event.get("response", "")

                                # TTS-Antwort zurück an Browser
                                if use_tts and _tts and final_response:
                                    await websocket.send_json({"type": "tts_start"})
                                    try:
                                        audio_bytes = await _tts.generate_audio_bytes(final_response)
                                        if audio_bytes:
                                            await websocket.send_json({
                                                "type": "tts_audio",
                                                "audio": base64.b64encode(audio_bytes).decode(),
                                                "format": "mp3"
                                            })
                                        else:
                                            await websocket.send_json({
                                                "type": "tts_fallback",
                                                "text": final_response
                                            })
                                    except Exception as e:
                                        logger.error(f"TTS error: {e}")
                        else:
                            await websocket.send_json({"type": "transcription", "text": ""})

                    except Exception as e:
                        logger.error(f"STT error: {e}")
                        await websocket.send_json({
                            "type": "stt_error",
                            "message": f"Spracherkennung fehlgeschlagen: {e}"
                        })
                else:
                    # Kein Whisper → Web Speech API hat schon transkribiert, Text kommt direkt
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
