"""Local LLM interface via Ollama."""
import asyncio
import json
import logging
from typing import AsyncGenerator, Optional
import httpx

logger = logging.getLogger(__name__)


class OllamaLLM:
    def __init__(self, base_url: str = "http://localhost:11434",
                 default_model: str = "llama3.2:3b",
                 powerful_model: str = "llama3.1:8b",
                 temperature: float = 0.7,
                 max_tokens: int = 4096):
        self.base_url = base_url
        self.default_model = default_model
        self.powerful_model = powerful_model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._client = httpx.AsyncClient(timeout=120.0)

    async def check_connection(self) -> bool:
        try:
            resp = await self._client.get(f"{self.base_url}/api/tags")
            return resp.status_code == 200
        except Exception:
            return False

    async def list_models(self) -> list[str]:
        try:
            resp = await self._client.get(f"{self.base_url}/api/tags")
            data = resp.json()
            return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []

    async def pull_model(self, model: str) -> AsyncGenerator[str, None]:
        async with self._client.stream(
            "POST",
            f"{self.base_url}/api/pull",
            json={"name": model},
            timeout=600.0
        ) as resp:
            async for line in resp.aiter_lines():
                if line:
                    try:
                        data = json.loads(line)
                        status = data.get("status", "")
                        if "completed" in data and "total" in data:
                            pct = int(data["completed"] / data["total"] * 100)
                            yield f"{status}: {pct}%"
                        else:
                            yield status
                    except Exception:
                        pass

    async def _check_chat_api(self) -> bool:
        """Check if /api/chat is available (Ollama >= 0.1.14)."""
        try:
            resp = await self._client.post(
                f"{self.base_url}/api/chat",
                json={"model": self.default_model, "messages": [], "stream": False},
                timeout=5.0
            )
            return resp.status_code != 404
        except Exception:
            return False

    def _messages_to_prompt(self, messages: list[dict], system: Optional[str] = None) -> str:
        """Convert messages list to a single prompt string for /api/generate fallback."""
        parts = []
        if system:
            parts.append(f"System: {system}\n")
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role == "system":
                parts.append(f"System: {content}")
            elif role == "user":
                parts.append(f"User: {content}")
            elif role == "assistant":
                parts.append(f"Assistant: {content}")
        parts.append("Assistant:")
        return "\n\n".join(parts)

    async def chat(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        stream: bool = False,
        system: Optional[str] = None,
    ) -> str:
        model = model or self.default_model

        # Try /api/chat first (modern Ollama)
        try:
            payload = {
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": self.temperature,
                    "num_predict": self.max_tokens,
                }
            }
            if system:
                payload["system"] = system

            resp = await self._client.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=120.0
            )
            if resp.status_code == 404:
                raise ValueError("api/chat not available")
            resp.raise_for_status()
            return resp.json()["message"]["content"]
        except httpx.TimeoutException:
            return "Fehler: Zeitüberschreitung beim LLM. Läuft Ollama?"
        except ValueError:
            pass
        except Exception as e:
            if "404" not in str(e):
                logger.error(f"LLM chat error: {e}")
                return f"Fehler: {e}"

        # Fallback: /api/generate (older Ollama versions)
        try:
            prompt = self._messages_to_prompt(messages, system)
            resp = await self._client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": self.temperature, "num_predict": self.max_tokens}
                },
                timeout=120.0
            )
            resp.raise_for_status()
            return resp.json().get("response", "")
        except httpx.TimeoutException:
            return "Fehler: Zeitüberschreitung. Läuft Ollama? (ollama serve)"
        except Exception as e:
            logger.error(f"LLM generate fallback error: {e}")
            return f"Fehler: {e} — Starte Ollama: 'ollama serve'"

    async def chat_stream(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        system: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        model = model or self.default_model

        # Try /api/chat stream first
        try:
            payload = {
                "model": model,
                "messages": messages,
                "stream": True,
                "options": {"temperature": self.temperature, "num_predict": self.max_tokens}
            }
            if system:
                payload["system"] = system

            used_chat = False
            async with self._client.stream(
                "POST", f"{self.base_url}/api/chat", json=payload, timeout=120.0
            ) as resp:
                if resp.status_code == 404:
                    raise ValueError("api/chat not available")
                used_chat = True
                async for line in resp.aiter_lines():
                    if line:
                        try:
                            data = json.loads(line)
                            if "message" in data:
                                token = data["message"].get("content", "")
                                if token:
                                    yield token
                            if data.get("done"):
                                break
                        except json.JSONDecodeError:
                            pass
            return
        except ValueError:
            pass  # fall through to /api/generate
        except Exception as e:
            if "404" not in str(e):
                yield f"\n[Fehler: {e}]"
                return

        # Fallback: /api/generate stream
        try:
            prompt = self._messages_to_prompt(messages, system)
            async with self._client.stream(
                "POST",
                f"{self.base_url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": True,
                    "options": {"temperature": self.temperature, "num_predict": self.max_tokens}
                },
                timeout=120.0
            ) as resp:
                async for line in resp.aiter_lines():
                    if line:
                        try:
                            data = json.loads(line)
                            token = data.get("response", "")
                            if token:
                                yield token
                            if data.get("done"):
                                break
                        except json.JSONDecodeError:
                            pass
        except Exception as e:
            yield f"\n[Fehler: {e}] — Starte Ollama mit: ollama serve"

    async def embed(self, text: str, model: str = "nomic-embed-text") -> list[float]:
        try:
            resp = await self._client.post(
                f"{self.base_url}/api/embeddings",
                json={"model": model, "prompt": text},
                timeout=30.0
            )
            return resp.json().get("embedding", [])
        except Exception as e:
            logger.error(f"Embedding error: {e}")
            return []

    async def close(self):
        await self._client.aclose()
