"""FastAPI web application for Jarvis AI."""
import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
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

# Global agent reference (set by main.py)
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


# Serve static files
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    tts: bool = False


@app.get("/", response_class=HTMLResponse)
async def root():
    template_path = Path(__file__).parent / "templates" / "index.html"
    return template_path.read_text(encoding="utf-8")


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
        "stats": stats
    }


@app.post("/api/chat")
async def chat(req: ChatRequest):
    if not _agent:
        raise HTTPException(503, "Jarvis not initialized")
    response = await _agent.chat(req.message, req.session_id)
    if req.tts and _tts:
        asyncio.create_task(_tts.speak(response, blocking=False))
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
    """Pull a model from Ollama registry."""
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
    facts = _agent.episodic.get_facts(limit=50)
    return {"facts": facts}


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
    session_id = _agent.new_session()
    return {"session_id": session_id}


@app.get("/api/notes")
async def get_notes(search: str = ""):
    from jarvis.tools.notes import list_notes
    return {"notes": list_notes(search)}


@app.get("/api/todos")
async def get_todos():
    from jarvis.tools.notes import list_todos
    return {"todos": list_todos()}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    session_id = _agent.new_session() if _agent else None
    logger.info(f"WebSocket connected, session: {session_id}")

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "chat")

            if msg_type == "chat":
                user_message = data.get("message", "")
                use_tts = data.get("tts", False)

                if not user_message.strip():
                    continue

                await websocket.send_json({
                    "type": "start",
                    "session_id": session_id
                })

                async for event in _agent.chat_stream(user_message, session_id):
                    await websocket.send_json(event)

                # TTS for final response
                if use_tts and _tts:
                    # Get last done event
                    pass

            elif msg_type == "voice_data":
                # Receive base64 audio data and transcribe
                if _stt:
                    import base64
                    import tempfile
                    audio_b64 = data.get("audio", "")
                    audio_bytes = base64.b64decode(audio_b64)
                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                        f.write(audio_bytes)
                        tmp_path = f.name
                    text = await _stt.transcribe_file(tmp_path)
                    os.unlink(tmp_path)
                    await websocket.send_json({"type": "transcription", "text": text or ""})

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
