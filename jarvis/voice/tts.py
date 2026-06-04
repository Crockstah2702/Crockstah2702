"""Text-to-Speech using Edge-TTS with emotional SSML support."""
import asyncio
import logging
import os
import re
import tempfile
from typing import Optional

logger = logging.getLogger(__name__)

# Emotion marker patterns → SSML express-as style
# de-DE-AmalaNeural supported styles: cheerful, empathetic, sad
EMOTION_PATTERNS = {
    "cheerful": [
        r"\*lacht[\s\w]*\*", r"\*haha\*", r"\*kichert\*", r"\*strahlend\*",
        r"\[begeistert\]", r"\[aufgeregt\]", r"\[freudig\]", r"\[freu\]",
        r"\[amüsiert\]", r"\[witzig\]", r"\[lustig\]",
        r"\(lacht\)", r"\(haha\)", r"\(hehe\)",
    ],
    "sad": [
        r"\[traurig\]", r"\[besorgt\]", r"\(seufzt[\s\w]*\)", r"\*seufzt\*",
        r"\[schade\]", r"\[bedauerlich\]", r"\[betroffen\]",
    ],
    "empathetic": [
        r"\[mitfühlend\]", r"\[einfühlsam\]", r"\[warm\]", r"\[empathisch\]",
        r"\[verständnisvoll\]",
    ],
}

# Markers to strip from spoken text (keep only the surrounding text)
ALL_EMOTION_MARKERS = re.compile(
    r"\*[^*]+\*|"
    r"\[[^\]]+\]|"
    r"\([^)]+\)"
)


class EdgeTTS:
    def __init__(self, voice: str = "de-DE-AmalaNeural",
                 rate: str = "+5%", volume: str = "+0%"):
        self.voice = voice
        self.rate = rate
        self.volume = volume
        self._available = None

    async def check_available(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            import edge_tts  # noqa: F401
            self._available = True
        except ImportError:
            self._available = False
        return self._available

    def _detect_emotion_style(self, text: str) -> Optional[str]:
        """Detect dominant emotion style from markers in text."""
        for style, patterns in EMOTION_PATTERNS.items():
            for pat in patterns:
                if re.search(pat, text, re.IGNORECASE):
                    return style
        return None

    def _build_ssml(self, text: str, style: Optional[str] = None) -> str:
        """Wrap text in SSML, optionally with express-as emotion style."""
        lang = self.voice[:5] if len(self.voice) >= 5 else "de-DE"
        clean = self._clean_text(text)
        # Escape XML special chars
        clean = clean.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        prosody = f'<prosody rate="{self.rate}" volume="{self.volume}">'

        if style:
            inner = (
                f'<mstts:express-as style="{style}">'
                f"{prosody}{clean}</prosody>"
                f"</mstts:express-as>"
            )
        else:
            inner = f"{prosody}{clean}</prosody>"

        return (
            f'<speak version="1.0" '
            f'xmlns="http://www.w3.org/2001/10/synthesis" '
            f'xmlns:mstts="http://www.w3.org/2001/mstts" '
            f'xml:lang="{lang}">'
            f'<voice name="{self.voice}">{inner}</voice>'
            f'</speak>'
        )

    async def generate_audio_bytes(self, text: str) -> Optional[bytes]:
        """Generate TTS audio, using SSML with emotion when markers are present."""
        if not await self.check_available():
            return None
        if not text or not text.strip():
            return None
        try:
            import edge_tts

            style = self._detect_emotion_style(text)
            if style:
                ssml = self._build_ssml(text, style)
                communicate = edge_tts.Communicate(ssml, self.voice)
            else:
                clean = self._clean_text(text)
                if not clean:
                    return None
                communicate = edge_tts.Communicate(clean, self.voice,
                                                    rate=self.rate, volume=self.volume)

            audio_data = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data += chunk["data"]

            if not audio_data and style:
                # SSML failed — fallback to plain text
                clean = self._clean_text(text)
                communicate = edge_tts.Communicate(clean, self.voice,
                                                    rate=self.rate, volume=self.volume)
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
        """Remove markdown formatting and emotion markers for clean TTS output."""
        # Strip emotion markers (keep surrounding speech context)
        text = ALL_EMOTION_MARKERS.sub(" ", text)
        # Strip markdown
        text = re.sub(r"\*+([^*]+)\*+", r"\1", text)
        text = re.sub(r"#{1,6}\s+", "", text)
        text = re.sub(r"`[^`]+`", "", text)
        text = re.sub(r"```.*?```", " Code-Block. ", text, flags=re.DOTALL)
        text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
        text = re.sub(r"[-*•]\s+", "", text)
        text = re.sub(r"\s+", " ", text)
        if len(text) > 1000:
            text = text[:1000] + "... und mehr."
        return text.strip()

    async def get_voices(self) -> list[str]:
        try:
            import edge_tts
            voices = await edge_tts.list_voices()
            return [v["Name"] for v in voices if "de-" in v["Name"] or "en-" in v["Name"]]
        except Exception:
            return ["de-DE-AmalaNeural", "de-DE-KillianNeural", "de-DE-KatjaNeural"]
