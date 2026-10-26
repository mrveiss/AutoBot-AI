# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No hosted provider module writes its own default-model literal (#15501).

Each provider carried one; two went stale for years (#18210). The table in
autobot_shared/ssot_hosted_models.py is the one place a hosted default is written. This
reads every string literal in the provider modules and fails on one that equals a model name
from the table or from autobot_shared/ssot_constants.py.
"""

from __future__ import annotations

import ast

from repo_tests._paths import repo_root

_PROVIDERS = ["openai", "anthropic", "groq", "mistral", "vertexai", "openrouter", "huggingface", "bedrock", "bootstrap"]
_VENDOR_PREFIXES = ("OPENAI_", "ANTHROPIC_", "GOOGLE_", "GROQ_", "MISTRAL_", "DEEPSEEK_")


def _model_names() -> set[str]:
    from autobot_shared.ssot_hosted_models import HOSTED_PROVIDER_DEFAULT_MODELS

    names = {m for models in HOSTED_PROVIDER_DEFAULT_MODELS.values() for m in models.values()}
    tree = ast.parse((repo_root() / "autobot_shared" / "ssot_constants.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            if any(isinstance(t, ast.Name) and t.id.startswith(_VENDOR_PREFIXES) for t in node.targets):
                names.add(node.value.value)
    from autobot_shared.ssot_hosted_models import HUGGINGFACE_KNOWN_CHAT_MODELS

    names.update(HUGGINGFACE_KNOWN_CHAT_MODELS)
    return names


def _literals(source: str) -> list[tuple[int, str]]:
    tree = ast.parse(source)
    doc_nodes = {
        id(n.body[0].value)
        for n in ast.walk(tree)
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and n.body
        and isinstance(n.body[0], ast.Expr)
        and isinstance(n.body[0].value, ast.Constant)
    }
    return [
        (n.lineno, n.value)
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in doc_nodes
    ]


def _offenders(sources: dict[str, str], names: set[str]) -> list[str]:
    return [
        f"{path}:{line}: {value!r}" for path, src in sources.items() for line, value in _literals(src) if value in names
    ]


def test_no_provider_module_writes_a_default_model_literal():
    names = _model_names()
    assert len(names) > 30, "the model-name set did not load"
    root = repo_root() / "autobot-backend" / "llm_shared" / "providers"
    sources = {f"{p}.py": (root / f"{p}.py").read_text(encoding="utf-8") for p in _PROVIDERS}
    sources["provider_registry.py"] = (root.parent / "provider_registry.py").read_text(encoding="utf-8")
    offenders = _offenders(sources, names)
    assert not offenders, "use autobot_shared.ssot_hosted_models.hosted_default_model (#15501):\n  " + "\n  ".join(
        offenders
    )


def test_the_detector_catches_a_planted_literal_and_skips_docstrings():
    planted = '"""Uses "gpt-4o-mini" in prose."""\nDEFAULT = "gpt-4o-mini"\n'
    assert _offenders({"x.py": planted}, {"gpt-4o-mini"}) == ["x.py:2: 'gpt-4o-mini'"]


# ---------------------------------------------------------------------------
# #15501 review: the exact-name check above missed `"default_model": "claude-3-5-sonnet"` in
# bootstrap.py -- a model name in neither the table nor the constants. This second check reads
# EVERY non-test module under llm_shared/ for a model-shaped literal in a DEFAULT position:
# a `default_model` key or keyword, a name containing DEFAULT, or `_get_setting("default_model",
# ...)`'s fallback. Catalogs (model lists, pricing tables, fallback chains, Bedrock's id map)
# are out of scope on purpose: they enumerate models, they do not choose one.
# ---------------------------------------------------------------------------

import re

_MODEL_SHAPE = re.compile(
    r"^(?:[\w.-]+/)?(?:claude|gpt|gemini|llama|mistral|mixtral|qwen|phi|gemma|deepseek|codestral|devstral|o[1-9])"
    r"[-.:]?\d",
    re.IGNORECASE,
)


def _default_position_literals(source: str) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []

    def check(node: ast.AST) -> None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and _MODEL_SHAPE.match(node.value):
            found.append((node.lineno, node.value))

    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and key.value == "default_model":
                    check(value)
        elif isinstance(node, ast.keyword) and node.arg == "default_model":
            check(node.value)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any("default" in getattr(t, "id", getattr(t, "attr", "")).lower() for t in targets):
                check(node.value)
        elif isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "_get_setting" and len(node.args) == 2:
            if isinstance(node.args[0], ast.Constant) and node.args[0].value == "default_model":
                check(node.args[1])
    return found


def test_no_llm_shared_module_puts_a_model_literal_in_a_default_position():
    root = repo_root() / "autobot-backend" / "llm_shared"
    files = [p for p in root.rglob("*.py") if not p.name.endswith("_test.py") and "tests" not in p.parts]
    assert any(p.name == "bootstrap.py" for p in files) and len(files) > 30
    hits = [
        f"{p.relative_to(root)}:{line}: {value!r}"
        for p in files
        for line, value in _default_position_literals(p.read_text(encoding="utf-8"))
    ]
    assert not hits, "use autobot_shared.ssot_hosted_models (#15501):\n  " + "\n  ".join(hits)


def test_the_default_position_check_has_contrast():
    flagged = (
        'X = {"default_model": "claude-3-5-sonnet"}\nf(default_model="gpt-4o")\n_DEFAULT_MODEL = "gemini-2.5-flash"\n'
    )
    flagged += 'self._get_setting("default_model", "qwen3.5:9b")\n'
    ignored = 'X = {"default_model": "hello"}\nCATALOG = ["claude-3-5-sonnet", "gpt-4o"]\ny = {"model": "gpt-4o"}\n'
    assert sorted(v for _, v in _default_position_literals(flagged)) == sorted(
        ["claude-3-5-sonnet", "gpt-4o", "gemini-2.5-flash", "qwen3.5:9b"]
    )
    assert _default_position_literals(ignored) == []
