"""Standalone test script for src/scriptures/tts.py's voice registry and
path resolution. No test framework, no network, no Qt event loop, and no
real synthesis - the actual ~60MB voice models aren't committed to this
repo (see tts.py's module docstring), so these tests only exercise the
logic that doesn't need them present.

Run directly:

    python3 tests/test_tts.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from scriptures import tts  # noqa: E402


def test_voices_are_unique_and_well_formed() -> None:
    keys = [v.key for v in tts.VOICES]
    assert len(keys) == len(set(keys)), "duplicate voice keys"
    assert len(tts.VOICES) == 4, "expected exactly 4 bundled voices"
    for voice in tts.VOICES:
        assert voice.key, "empty voice key"
        assert voice.label, "empty voice label"
    print("test_voices_are_unique_and_well_formed: PASSED")


def test_default_voice_key_is_a_real_voice() -> None:
    assert tts.get_voice(tts.DEFAULT_VOICE_KEY) is not None
    print("test_default_voice_key_is_a_real_voice: PASSED")


def test_get_voice_returns_none_for_unknown_key() -> None:
    assert tts.get_voice("not-a-real-voice") is None
    print("test_get_voice_returns_none_for_unknown_key: PASSED")


def test_model_path_matches_voices_dir_and_key() -> None:
    import os
    import tempfile

    from scriptures import paths

    # A voice that isn't downloaded points at where its download would go.
    path = tts.model_path("not-downloaded-voice")
    assert path == paths.voices_dir() / "not-downloaded-voice.onnx", path
    # In the snap, voices go per user under $SNAP_USER_COMMON.
    saved = os.environ.get("SNAP_USER_COMMON")
    os.environ["SNAP_USER_COMMON"] = tempfile.gettempdir()
    try:
        assert paths.voices_dir() == Path(tempfile.gettempdir()) / "voices"
        assert tts.download_path("en_US-lessac-medium").parent == paths.voices_dir()
    finally:
        if saved is None:
            os.environ.pop("SNAP_USER_COMMON")
        else:
            os.environ["SNAP_USER_COMMON"] = saved
    # Every voice's download URL is in Piper's repository.
    assert all(v.url(".onnx").startswith(tts.VOICE_BASE_URL) for v in tts.VOICES)
    print("test_model_path_matches_voices_dir_and_key: PASSED")


def test_is_voice_installed_false_for_missing_file() -> None:
    # Regardless of whether this dev machine has actually run
    # scripts/download_tts_voices.py, a key that can never be a real
    # voice must always report as not installed.
    assert tts.is_voice_installed("definitely-not-a-real-voice-key") is False
    print("test_is_voice_installed_false_for_missing_file: PASSED")


if __name__ == "__main__":
    test_voices_are_unique_and_well_formed()
    test_default_voice_key_is_a_real_voice()
    test_get_voice_returns_none_for_unknown_key()
    test_model_path_matches_voices_dir_and_key()
    test_is_voice_installed_false_for_missing_file()
    print("All tts.py tests passed.")
