"""Text-to-Speech using Edge-TTS (Microsoft, free, local quality)."""
import asyncio
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

GERMAN_VOICES = {
    "male": "de-DE-KillianNeural",
    "female": "de-DE-KatjaNeural",
    "male2": "de-AT-JonasNeural",
    "female2": "de-CH-LeniNeural",
}

ENGLISH_VOICES = {
    "male": "en-US-GuyNeural",
    "female": "en-US-JennyNeural",
}


class EdgeTTS:
    def __init__(self, voice: str = "de-DE-KillianNeural",
                 rate: str = "+10%", volume: str = "+0%"):
        self.voice = voice
        self.rate = rate
        self.volume = volume
        self._available = None

    async def check_available(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            import edge_tts
            self._available = True
            return True
        except ImportError:
            self._available = False
            return False

    async def generate_audio_bytes(self, text: str) -> Optional[bytes]:
        """Generate TTS audio and return raw MP3 bytes (for browser playback)."""
        if not await self.check_available():
            return None
        clean = self._clean_text(text)
        if not clean:
            return None
        try:
            import edge_tts
            communicate = edge_tts.Communicate(clean, self.voice,
                                                rate=self.rate, volume=self.volume)
            audio_data = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data += chunk["data"]
            return audio_data if audio_data else None
        except Exception as e:
            logger.error(f"TTS Fehler: {e}")
            return None

    async def speak(self, text: str, blocking: bool = True) -> bool:
        """Generate and play TTS locally (server-side fallback)."""
        audio_bytes = await self.generate_audio_bytes(text)
        if not audio_bytes:
            return False
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(audio_bytes)
            tmp_path = f.name
        if blocking:
            await self._play_audio(tmp_path)
        else:
            asyncio.create_task(self._play_and_cleanup(tmp_path))
        return True

    async def _play_audio(self, path: str):
        """Play audio file via system player."""
        try:
            import pygame
            pygame.mixer.init()
            pygame.mixer.music.load(path)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                await asyncio.sleep(0.1)
            pygame.mixer.music.stop()
            pygame.mixer.quit()
        except ImportError:
            for player in [["mpg123", "-q"], ["aplay"], ["afplay"]]:
                try:
                    proc = await asyncio.create_subprocess_exec(
                        *player, path,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL
                    )
                    await proc.wait()
                    break
                except FileNotFoundError:
                    continue
        finally:
            try:
                os.unlink(path)
            except Exception:
                pass

    async def _play_and_cleanup(self, path: str):
        await self._play_audio(path)

    def _clean_text(self, text: str) -> str:
        """Remove markdown and special chars for TTS."""
        import re
        text = re.sub(r"\*+([^*]+)\*+", r"\1", text)   # bold/italic
        text = re.sub(r"#{1,6}\s+", "", text)           # headers
        text = re.sub(r"`[^`]+`", "", text)             # code
        text = re.sub(r"```.*?```", " Code-Block. ", text, flags=re.DOTALL)
        text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)  # links
        text = re.sub(r"[-*•]\s+", "", text)            # bullets
        text = re.sub(r"\s+", " ", text)                # whitespace
        # Limit length for TTS
        if len(text) > 1000:
            text = text[:1000] + "... und mehr."
        return text.strip()

    async def get_voices(self) -> list[str]:
        """List available voices."""
        try:
            import edge_tts
            voices = await edge_tts.list_voices()
            return [v["Name"] for v in voices if "de-" in v["Name"] or "en-" in v["Name"]]
        except Exception:
            return list(GERMAN_VOICES.values()) + list(ENGLISH_VOICES.values())
