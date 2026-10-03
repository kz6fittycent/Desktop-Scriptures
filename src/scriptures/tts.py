"""Text-to-speech voice registry and synthesis (see
ui/tts_playback.py for the background-thread controller that drives
this from the reading view, and ui/reading_view.py for the Listen
controls and verse highlighting).

Uses Piper (https://github.com/OHF-Voice/piper1-gpl) - a small, fast,
fully offline neural TTS engine, entirely local like the rest of this
app's core reading experience: no network access, no server involved.

Voice models are NOT committed to this repo - each is ~60MB, and
snapcraft.yaml's "tts-voices" part downloads them at build time
straight from Piper's own model repository on Hugging Face (the same
upstream source these voices already come from). For local development,
run scripts/download_tts_voices.py once to fetch them into
data/tts_voices/.
"""

from __future__ import annotations

import io
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from scriptures.paths import DATA_DIR

if TYPE_CHECKING:
    from piper.voice import PiperVoice

VOICES_DIR = DATA_DIR / "tts_voices"


@dataclass(frozen=True)
class Voice:
    key: str  # matches the bundled <key>.onnx / <key>.onnx.json filenames
    label: str


# One male and one female voice per accent, per the choice made when this
# feature was scoped - see MODEL_SOURCES in scripts/download_tts_voices.py
# for exactly where each of these comes from.
VOICES: list[Voice] = [
    Voice("en_US-lessac-medium", "American English (Male)"),
    Voice("en_US-hfc_female-medium", "American English (Female)"),
    Voice("en_GB-alan-medium", "British English (Male)"),
    Voice("en_GB-cori-medium", "British English (Female)"),
]

DEFAULT_VOICE_KEY = VOICES[0].key


def get_voice(key: str) -> Voice | None:
    return next((v for v in VOICES if v.key == key), None)


def model_path(key: str) -> Path:
    return VOICES_DIR / f"{key}.onnx"


def is_voice_installed(key: str) -> bool:
    return model_path(key).exists()


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
