"""Speech-to-Text using faster-whisper (local, no API)."""
import asyncio
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class WhisperSTT:
    def __init__(self, model_size: str = "base", language: str = "de",
                 device: str = "cpu"):
        self.model_size = model_size
        self.language = language
        self.device = device
        self._model = None
        self._available = False

    def _load_model(self):
        if self._model is not None:
            return True
        try:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type="int8" if self.device == "cpu" else "float16"
            )
            self._available = True
            logger.info(f"Whisper model '{self.model_size}' loaded on {self.device}")
            return True
        except ImportError:
            logger.warning("faster-whisper nicht installiert. Spracherkennung deaktiviert.")
            return False
        except Exception as e:
            logger.error(f"Whisper Ladefehler: {e}")
            return False

    async def transcribe_file(self, audio_path: str) -> Optional[str]:
        """Transcribe an audio file."""
        if not self._load_model():
            return None
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, self._do_transcribe, audio_path
            )
            return result
        except Exception as e:
            logger.error(f"Transkriptionsfehler: {e}")
            return None

    def _do_transcribe(self, audio_path: str) -> str:
        segments, info = self._model.transcribe(
            audio_path,
            language=self.language,
            beam_size=5,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500}
        )
        text = " ".join(segment.text for segment in segments)
        return text.strip()

    async def record_and_transcribe(self, duration: float = 5.0) -> Optional[str]:
        """Record from microphone and transcribe."""
        try:
            import sounddevice as sd
            import soundfile as sf
            import numpy as np

            sample_rate = 16000
            logger.info(f"Aufnahme läuft {duration}s...")
            recording = sd.rec(
                int(duration * sample_rate),
                samplerate=sample_rate,
                channels=1,
                dtype="float32"
            )
            sd.wait()

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                tmp_path = f.name
            sf.write(tmp_path, recording, sample_rate)

            result = await self.transcribe_file(tmp_path)
            os.unlink(tmp_path)
            return result

        except ImportError:
            logger.warning("sounddevice/soundfile nicht installiert.")
            return None
        except Exception as e:
            logger.error(f"Aufnahmefehler: {e}")
            return None

    @property
    def is_available(self) -> bool:
        return self._load_model()
