"""Text-to-speech voice registry and synthesis (see
ui/tts_playback.py for the background-thread controller that drives
this from the reading view, and ui/reading_view.py for the Listen
controls and verse highlighting).

Uses Piper (https://github.com/OHF-Voice/piper1-gpl) - a small, fast,
fully offline neural TTS engine: synthesis is entirely local.

Voices are opt-in downloads, not part of the app (each is ~60 MB): the
user picks which to fetch in Menu → Voice → Download Voices... (see
ui/voices_dialog.py and voice_download.py). They come straight from
Piper's own model repository on Hugging Face and are checked against the
SHA-256 pinned below, then stored per user (paths.voices_dir()). A voice
found in the app's own data/tts_voices - a source checkout after
scripts/download_tts_voices.py, or an older build that bundled them - is
used too.
"""

from __future__ import annotations

import io
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from scriptures.paths import DATA_DIR, voices_dir

if TYPE_CHECKING:
    from piper.voice import PiperVoice

BUNDLED_VOICES_DIR = DATA_DIR / "tts_voices"
VOICE_BASE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en"


@dataclass(frozen=True)
class Voice:
    key: str  # the <key>.onnx / <key>.onnx.json filenames
    label: str
    source: str  # its folder under VOICE_BASE_URL
    model_sha256: str  # pinned from Hugging Face's own LFS record
    model_size: int
    config_sha256: str
    config_size: int
    dataset_license: str  # the recordings it was trained on - see THIRD_PARTY_LICENSES.md

    def url(self, suffix: str) -> str:
        return f"{VOICE_BASE_URL}/{self.source}/{self.key}{suffix}"


# One male and one female voice per accent, per the choice made when this
# feature was scoped.
VOICES: list[Voice] = [
    Voice("en_US-lessac-medium", "American English (Male)", "en_US/lessac/medium",
          "5efe09e69902187827af646e1a6e9d269dee769f9877d17b16b1b46eeaaf019f", 63201294,
          "efe19c417bed055f2d69908248c6ba650fa135bc868b0e6abb3da181dab690a0", 4885,
          "Lessac/Blizzard 2013 recordings, under a research license"),
    Voice("en_US-hfc_female-medium", "American English (Female)", "en_US/hfc_female/medium",
          "914c473788fc1fa8b63ace1cdcdb44588f4ae523d3ab37df1536616835a140b7", 63201294,
          "03f1fa0622b80463283592d97aca9f6e89aec345a5c56b7257723e0093c58b6c", 5033,
          "Hi-Fi CAPTAIN recordings, CC BY-NC-SA 4.0 (non-commercial)"),
    Voice("en_GB-alan-medium", "British English (Male)", "en_GB/alan/medium",
          "0a309668932205e762801f1efc2736cd4b0120329622adf62be09e56339d3330", 63201294,
          "c0f0d124e5895c00e7c03b35dcc8287f319a6998a365b182deb5c8e752ee8c1e", 4888,
          "Mycroft AI's recordings of Alan Pope"),
    Voice("en_GB-cori-medium", "British English (Female)", "en_GB/cori/medium",
          "1899f98e5fb8310154f3c2973f4b8a929ba7245e722b3d3a85680b833d95f10d", 63531379,
          "e262c16d7f192f69d4edd6b4ef8a5915379e67495fcc402f1ab15eeb33da3d36", 4966,
          "LibriVox recordings, public domain"),
]

DEFAULT_VOICE_KEY = VOICES[0].key


def get_voice(key: str) -> Voice | None:
    return next((v for v in VOICES if v.key == key), None)


def download_path(key: str) -> Path:
    """Where a downloaded voice's model lives (its .onnx.json beside it)."""
    return voices_dir() / f"{key}.onnx"


def model_path(key: str) -> Path:
    """The voice's model - downloaded, or else bundled with the app."""
    downloaded = download_path(key)
    if downloaded.exists() and downloaded.with_suffix(".onnx.json").exists():
        return downloaded
    bundled = BUNDLED_VOICES_DIR / f"{key}.onnx"
    return bundled if bundled.exists() else downloaded


def is_voice_installed(key: str) -> bool:
    path = model_path(key)
    return path.exists() and path.with_suffix(".onnx.json").exists()


def is_removable(key: str) -> bool:
    """Downloaded by the user (not part of the app), so it can be removed."""
    return download_path(key).exists()


def remove_voice(key: str) -> None:
    _loaded_voices.pop(key, None)
    for path in (download_path(key), download_path(key).with_suffix(".onnx.json")):
        path.unlink(missing_ok=True)


# Loading a ~60MB onnx model takes the better part of a second - cached
# per voice for the lifetime of the process rather than reloaded for
# every verse.
_loaded_voices: dict[str, "PiperVoice"] = {}


def _load(key: str) -> "PiperVoice":
    from piper.voice import PiperVoice

    voice = _loaded_voices.get(key)
    if voice is None:
        voice = PiperVoice.load(model_path(key))
        _loaded_voices[key] = voice
    return voice


def synthesize(key: str, text: str) -> bytes:
    """A complete WAV file's bytes for `text`, spoken in the given voice.
    Raises FileNotFoundError if that voice isn't installed (see
    is_voice_installed) - callers should check that first so they can
    show a real message instead of a raw traceback. Meant to be called
    from a background thread (see ui/tts_playback.py) - this is a
    blocking, CPU-bound call."""
    if not is_voice_installed(key):
        raise FileNotFoundError(f"Voice model not found: {model_path(key)}")
    voice = _load(key)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        voice.synthesize_wav(text, wav_file)
    return buf.getvalue()
