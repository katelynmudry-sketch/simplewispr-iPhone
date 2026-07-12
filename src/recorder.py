"""Audio recording via sounddevice. Float32 capture → int16 WAV."""

import wave
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000
APP_SUPPORT = Path.home() / "Library" / "Application Support" / "MyWispr"
AUDIO_DIR = APP_SUPPORT / "audio"

MIN_DURATION_SEC = 0.3


class Recorder:
    def __init__(self):
        self._chunks: list[np.ndarray] = []
        self._stream: Optional[sd.InputStream] = None
        self._start_time: Optional[float] = None

    def start(self) -> None:
        self._chunks = []
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            callback=self._callback,
        )
        self._stream.start()
        import time
        self._start_time = time.monotonic()

    def _callback(self, indata, frames, time_info, status):
        self._chunks.append(indata.copy())

    def stop(self) -> Optional[str]:
        """Stop recording, save WAV, return path. Returns None if too short."""
        if self._stream is None:
            return None
        self._stream.stop()
        self._stream.close()
        self._stream = None

        import time
        duration = time.monotonic() - (self._start_time or 0)
        if duration < MIN_DURATION_SEC or not self._chunks:
            return None

        audio = np.concatenate(self._chunks, axis=0).flatten()
        return _save_wav(audio, duration)

    @property
    def is_recording(self) -> bool:
        return self._stream is not None


def _save_wav(audio: np.ndarray, duration: float) -> str:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = AUDIO_DIR / f"{ts}.wav"
    pcm = (audio * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm.tobytes())
    return str(path)
