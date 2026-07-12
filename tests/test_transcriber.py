"""M2 tests: model discovery covering all six branches."""

import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from transcriber import build_initial_prompt, discover, MIN_MODEL_SIZE


def _make_model(directory: Path, name: str, size: int = MIN_MODEL_SIZE + 1) -> Path:
    """Create a fake model file of the given size."""
    directory.mkdir(parents=True, exist_ok=True)
    p = directory / name
    p.write_bytes(b"\x00" * size)
    return p


# Branch 1: user-configured path wins over everything else
def test_branch1_user_configured_path(tmp_path):
    user_model = _make_model(tmp_path / "custom", "my-model.bin")
    # Even with valid discovery paths, user path is returned first
    decoy = _make_model(tmp_path / "decoy", "ggml-model-whisper-turbo.bin")
    result = discover(
        user_model_path=str(user_model),
        discovery_paths=[decoy],
    )
    assert result == str(user_model)


# Branch 1 miss: user path exists but too small → falls through
def test_branch1_user_path_too_small(tmp_path):
    tiny = tmp_path / "tiny.bin"
    tiny.write_bytes(b"\x00" * 100)
    fallback = _make_model(tmp_path / "models", "ggml-model-whisper-turbo.bin")
    result = discover(
        user_model_path=str(tiny),
        discovery_paths=[fallback],
    )
    assert result == str(fallback)


# Branch 1 miss: user path doesn't exist → falls through
def test_branch1_user_path_missing(tmp_path):
    fallback = _make_model(tmp_path / "models", "ggml-model-whisper-turbo.bin")
    result = discover(
        user_model_path=str(tmp_path / "nonexistent.bin"),
        discovery_paths=[fallback],
    )
    assert result == str(fallback)


# Branch 2: MyWispr turbo (first in discovery list)
def test_branch2_mywispr_turbo(tmp_path):
    mywispr_turbo = _make_model(tmp_path / "mywispr" / "models", "ggml-model-whisper-turbo.bin")
    macwhisper_turbo = _make_model(tmp_path / "macwhisper" / "models", "ggml-model-whisper-turbo.bin")
    mywispr_base = _make_model(tmp_path / "mywispr" / "models", "ggml-model-whisper-base.bin")
    macwhisper_base = _make_model(tmp_path / "macwhisper" / "models", "ggml-model-whisper-base.bin")

    result = discover(
        discovery_paths=[mywispr_turbo, macwhisper_turbo, mywispr_base, macwhisper_base],
    )
    assert result == str(mywispr_turbo)


# Branch 3: MacWhisper turbo (MyWispr turbo absent)
def test_branch3_macwhisper_turbo(tmp_path):
    macwhisper_turbo = _make_model(tmp_path / "macwhisper" / "models", "ggml-model-whisper-turbo.bin")
    mywispr_base = _make_model(tmp_path / "mywispr" / "models", "ggml-model-whisper-base.bin")
    macwhisper_base = _make_model(tmp_path / "macwhisper" / "models", "ggml-model-whisper-base.bin")

    absent = tmp_path / "mywispr" / "models" / "ggml-model-whisper-turbo.bin"
    result = discover(
        discovery_paths=[absent, macwhisper_turbo, mywispr_base, macwhisper_base],
    )
    assert result == str(macwhisper_turbo)


# Branch 4: MyWispr base (both turbo paths absent)
def test_branch4_mywispr_base(tmp_path):
    mywispr_base = _make_model(tmp_path / "mywispr" / "models", "ggml-model-whisper-base.bin")
    macwhisper_base = _make_model(tmp_path / "macwhisper" / "models", "ggml-model-whisper-base.bin")

    absent_turbo_1 = tmp_path / "mywispr" / "models" / "ggml-model-whisper-turbo.bin"
    absent_turbo_2 = tmp_path / "macwhisper" / "models" / "ggml-model-whisper-turbo.bin"
    result = discover(
        discovery_paths=[absent_turbo_1, absent_turbo_2, mywispr_base, macwhisper_base],
    )
    assert result == str(mywispr_base)


# Branch 5: MacWhisper base (all others absent)
def test_branch5_macwhisper_base(tmp_path):
    macwhisper_base = _make_model(tmp_path / "macwhisper" / "models", "ggml-model-whisper-base.bin")

    absent = [
        tmp_path / "mywispr" / "models" / "ggml-model-whisper-turbo.bin",
        tmp_path / "macwhisper" / "models" / "ggml-model-whisper-turbo.bin",
        tmp_path / "mywispr" / "models" / "ggml-model-whisper-base.bin",
    ]
    result = discover(
        discovery_paths=absent + [macwhisper_base],
    )
    assert result == str(macwhisper_base)


# Branch 6: model-needed — nothing found
def test_branch6_no_model(tmp_path):
    absent = [tmp_path / f"absent_{i}.bin" for i in range(4)]
    result = discover(discovery_paths=absent)
    assert result is None


# Branch 6: model-needed — all paths exist but all too small (HTML error pages)
def test_branch6_all_too_small(tmp_path):
    tiny_paths = []
    for i in range(4):
        p = tmp_path / f"small_{i}.bin"
        p.write_bytes(b"\x00" * 1000)
        tiny_paths.append(p)
    result = discover(discovery_paths=tiny_paths)
    assert result is None


# --- build_initial_prompt ---

def test_build_initial_prompt_empty_list():
    assert build_initial_prompt([]) is None


def test_build_initial_prompt_none_equivalent():
    assert build_initial_prompt(None or []) is None


def test_build_initial_prompt_single_term():
    assert build_initial_prompt(["MyWispr"]) == "Glossary: MyWispr"


def test_build_initial_prompt_multiple_terms():
    result = build_initial_prompt(["MyWispr", "Dropbox", "Wispr"])
    assert result == "Glossary: MyWispr, Dropbox, Wispr"


def test_build_initial_prompt_preserves_case():
    result = build_initial_prompt(["iPhone", "MacBook", "WiFi"])
    assert result == "Glossary: iPhone, MacBook, WiFi"


# Dev machine: discovery resolves to MacWhisper turbo with no user config
def test_dev_machine_finds_macwhisper_turbo():
    """On this machine, no user config → should resolve to MacWhisper turbo."""
    result = discover()
    assert result is not None, "Expected a model on the dev machine"
    assert "whisper-turbo" in result or "turbo" in result.lower(), (
        f"Expected turbo model, got: {result}"
    )
