"""pywhispercpp wrapper + model discovery (six-step order from REQUIREMENTS §3)."""

from pathlib import Path
from typing import Optional, Callable

APP_SUPPORT = Path.home() / "Library" / "Application Support" / "MyWispr"
MACWHISPER_SUPPORT = Path.home() / "Library" / "Application Support" / "MacWhisper"

DISCOVERY_PATHS = [
    # Steps 2–5 from REQUIREMENTS §3 (step 1 is user-configured, handled in discover())
    APP_SUPPORT / "models" / "ggml-model-whisper-turbo.bin",
    MACWHISPER_SUPPORT / "models" / "ggml-model-whisper-turbo.bin",
    APP_SUPPORT / "models" / "ggml-model-whisper-base.bin",
    MACWHISPER_SUPPORT / "models" / "ggml-model-whisper-base.bin",
]

HF_BASE_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main"
MODEL_URLS = {
    "base": f"{HF_BASE_URL}/ggml-base.bin",
    "turbo": f"{HF_BASE_URL}/ggml-large-v3-turbo.bin",
}
MODEL_DEST_NAMES = {
    "base": "ggml-model-whisper-base.bin",
    "turbo": "ggml-model-whisper-turbo.bin",
}
MIN_MODEL_SIZE = 50 * 1024 * 1024  # 50 MB sanity check


def discover(
    user_model_path: Optional[str] = None,
    discovery_paths: Optional[list] = None,
) -> Optional[str]:
    """Return resolved model path or None (model-needed).

    discovery_paths overrides DISCOVERY_PATHS for testing.
    """
    if discovery_paths is None:
        discovery_paths = DISCOVERY_PATHS

    # Step 1: user-configured
    if user_model_path:
        p = Path(user_model_path)
        if p.exists() and p.stat().st_size > MIN_MODEL_SIZE:
            return str(p)

    # Steps 2–5
    for path in discovery_paths:
        if Path(path).exists() and Path(path).stat().st_size > MIN_MODEL_SIZE:
            return str(path)

    return None


def build_initial_prompt(vocab: list) -> Optional[str]:
    """Compose vocabulary list into a whisper initial_prompt string, or None if empty."""
    if not vocab:
        return None
    return "Glossary: " + ", ".join(vocab)


class Transcriber:
    def __init__(self):
        self._model = None
        self._model_path: Optional[str] = None

    def load(self, model_path: str) -> None:
        from pywhispercpp.model import Model
        if self._model_path != model_path:
            self._model = Model(
                model_path,
                redirect_whispercpp_logs_to=None,
                print_progress=False,
                print_realtime=False,
            )
            self._model_path = model_path

    def transcribe(
        self,
        wav_path: str,
        language: str = "auto",
        initial_prompt: Optional[str] = None,
    ) -> tuple[str, str]:
        """Return (raw_text, detected_language)."""
        if self._model is None:
            raise RuntimeError("Model not loaded")
        kwargs = {}
        if language != "auto":
            kwargs["language"] = language
        if initial_prompt:
            kwargs["initial_prompt"] = initial_prompt
        segments = self._model.transcribe(wav_path, **kwargs)
        raw = " ".join(seg.text for seg in segments).strip()
        lang = language if language != "auto" else "auto"
        return raw, lang

    def unload(self) -> None:
        self._model = None
        self._model_path = None


def download_model(
    model_key: str,
    progress_cb: Optional[Callable[[float], None]] = None,
) -> str:
    """Download model to MyWispr models dir. Returns dest path. Raises on error."""
    import ssl
    import certifi
    import urllib.request

    url = MODEL_URLS[model_key]
    dest_name = MODEL_DEST_NAMES[model_key]
    models_dir = APP_SUPPORT / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    dest = models_dir / dest_name
    part = models_dir / (dest_name + ".part")

    ssl_ctx = ssl.create_default_context(cafile=certifi.where())

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "MyWispr/1"})
        with urllib.request.urlopen(req, context=ssl_ctx) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            chunk = 65536
            with open(part, "wb") as f:
                while True:
                    data = resp.read(chunk)
                    if not data:
                        break
                    f.write(data)
                    downloaded += len(data)
                    if total > 0 and progress_cb:
                        progress_cb(min(downloaded / total, 1.0))

        if part.stat().st_size < MIN_MODEL_SIZE:
            part.unlink(missing_ok=True)
            raise ValueError("Downloaded file too small — likely an error page, not a model")

        part.rename(dest)
        return str(dest)
    except Exception:
        part.unlink(missing_ok=True)
        raise
