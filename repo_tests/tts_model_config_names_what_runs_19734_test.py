# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#19734: the configured TTS model is what the engine runs, and the predownload is not skipped for a token."""

from __future__ import annotations

import re

import yaml
from repo_tests._paths import repo_root

_ROLE = "autobot-slm-backend/ansible/roles/tts-worker"


def _read(rel: str) -> str:
    return (repo_root() / _ROLE / rel).read_text(encoding="utf-8")


def _default() -> str:
    return yaml.safe_load(_read("defaults/main.yml"))["tts_model_id"]


def test_the_default_is_the_engine_s_own_model() -> None:
    assert _default().startswith("kyutai/pocket-tts")


def test_the_worker_s_fallback_renders_from_the_one_setting() -> None:
    assert 'os.getenv("TTS_MODEL_ID", "{{ tts_model_id }}")' in _read("templates/tts-worker.py.j2")


def test_the_default_is_not_treated_as_gated_in_either_place() -> None:
    for template in ("templates/tts-worker.py.j2", "templates/predownload-model.py.j2"):
        block = re.search(r"GATED[A-Z_]*\b[^=]*=\s*\((.*?)\)", _read(template), re.S)
        assert block, f"{template} has no gated-model prefix tuple"
        prefixes = re.findall(r'"([^"]+)"', block.group(1))
        assert prefixes and not any(_default().startswith(prefix) for prefix in prefixes), template


def test_worker_and_predownload_load_the_same_way() -> None:
    for template in ("templates/tts-worker.py.j2", "templates/predownload-model.py.j2"):
        assert "TTSModel.load_model()" in _read(template), template


def test_the_startup_log_labels_the_configured_id_as_configured() -> None:
    assert "Pocket TTS model loaded (configured TTS_MODEL_ID=%s" in _read("templates/tts-worker.py.j2")
