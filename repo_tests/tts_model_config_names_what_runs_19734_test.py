# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#19734: the configured TTS model is what the engine runs, and the predownload is not skipped for a token."""

from __future__ import annotations

import ast
import re

import pytest
import yaml
from repo_tests._paths import repo_root

from tools.lint import _parse_cache as parse_cache

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


def _as_python(template: str) -> str:
    """The template's Python with its Jinja tags rendered out: blocks dropped, expressions a placeholder."""
    text = re.sub(r"{#.*?#}", "", template, flags=re.S)
    text = re.sub(r"^[ \t]*{%-?.*?-?%}[ \t]*\n", "", text, flags=re.M | re.S)
    text = re.sub(r"{%-?.*?-?%}", "", text, flags=re.S)
    return re.sub(r"{{.*?}}", "None", text, flags=re.S)


def _calls_load_model(source: str) -> bool:
    """True only for an active ``TTSModel.load_model()`` call: comments and string literals don't count (#20759)."""
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "load_model"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "TTSModel"
        for node in ast.walk(parse_cache.parse(_as_python(source)))
    )


def test_worker_and_predownload_load_the_same_way() -> None:
    for template in ("templates/tts-worker.py.j2", "templates/predownload-model.py.j2"):
        assert _calls_load_model(_read(template)), template


@pytest.mark.parametrize(
    "source, active",
    [
        ("model = TTSModel.load_model()\n", True),
        ("{% if x %}\nmodel = TTSModel.load_model()\n{% endif %}\n", True),
        ("# model = TTSModel.load_model()\nmodel = None\n", False),
        ('note = "TTSModel.load_model()"\n', False),
        ("model = OtherModel.load_model()\n", False),
    ],
    ids=["active", "inside-a-jinja-block", "comment-only", "string-only", "another-class"],
)
def test_the_loader_check_counts_only_an_active_call(source: str, active: bool) -> None:
    """Contrast pair: the check would pass a comment or a string if it matched text (#20759)."""
    assert _calls_load_model(source) is active


def test_the_startup_log_labels_the_configured_id_as_configured() -> None:
    assert "Pocket TTS model loaded (configured TTS_MODEL_ID=%s" in _read("templates/tts-worker.py.j2")
