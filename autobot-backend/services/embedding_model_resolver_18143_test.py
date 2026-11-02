# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One embedding-model resolver for generator and cache keys (#18143)."""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from autobot_shared import embedding_model
from knowledge.embedding_cache import EmbeddingCache

_SERVICES = Path(__file__).resolve().parent
_BACKEND = _SERVICES.parent


def _generator_model() -> str:
    """Drive the real generator (no model passed); return the model it used."""
    from services import npu_client

    client = MagicMock()
    client.is_available = AsyncMock(return_value=True)
    client.generate_embedding = AsyncMock(return_value=[0.1])
    with patch.object(npu_client, "get_npu_client", return_value=client):
        asyncio.run(npu_client.generate_embedding_with_fallback("text"))
    return client.generate_embedding.await_args.args[1]


def _cache_key_model_and_generator_model(configured: str) -> tuple[str, str, str]:
    with patch("autobot_shared.ssot_config.config.llm") as llm:
        llm.embedding_model = configured
        key = EmbeddingCache.make_key(embedding_model.active_embedding_model(), "text")
        return key, embedding_model.active_embedding_model(), _generator_model()


def test_changing_configured_model_moves_key_and_generator_together() -> None:
    key_a, keyed_a, gen_a = _cache_key_model_and_generator_model("model-a:latest")
    key_b, keyed_b, gen_b = _cache_key_model_and_generator_model("model-b:latest")
    assert (keyed_a, gen_a) == ("model-a:latest", "model-a:latest")
    assert (keyed_b, gen_b) == ("model-b:latest", "model-b:latest")
    assert key_a != key_b


def test_search_cache_key_model_is_the_resolver_value() -> None:
    # #19379: search keys the cache by the bound space's model, which the binding resolves via the
    # resolver whenever the KB carries none -- so the key is still the resolver value.
    source = (_BACKEND / "knowledge" / "search.py").read_text(encoding="utf-8")
    assert "model = model or snapshot(self).model" in source
    binding = (_BACKEND / "knowledge" / "embedding_space_binding.py").read_text(encoding="utf-8")
    assert 'getattr(kb, "embedding_model_name", None) or active_embedding_model()' in binding


def _str_defaults_on_model_name(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    bad = []
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = fn.args.args + fn.args.kwonlyargs
            defaults = [None] * (len(fn.args.args) - len(fn.args.defaults)) + list(fn.args.defaults)
            defaults += list(fn.args.kw_defaults)
            for arg, default in zip(args, defaults):
                if arg.arg == "model_name" and isinstance(default, ast.Constant) and isinstance(default.value, str):
                    bad.append(f"{path.name}:{fn.name}")
    return bad


def test_generator_declares_no_literal_model_default() -> None:
    assert _str_defaults_on_model_name(_SERVICES / "npu_client.py") == []


def test_guard_contrast_pair(tmp_path: Path) -> None:
    forked = tmp_path / "forked.py"
    forked.write_text('def f(text, model_name: str = "nomic-embed-text"): ...\n', encoding="utf-8")
    clean = tmp_path / "clean.py"
    clean.write_text("def f(text, model_name: str | None = None): ...\n", encoding="utf-8")
    assert _str_defaults_on_model_name(forked) == ["forked.py:f"]
    assert _str_defaults_on_model_name(clean) == []
