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
from repo_tests._reach import declare

from tools.lint import _parse_cache as parse_cache
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_PROVIDERS = ["openai", "anthropic", "groq", "mistral", "vertexai", "openrouter", "huggingface", "bedrock", "bootstrap"]
_VENDOR_PREFIXES = ("OPENAI_", "ANTHROPIC_", "GOOGLE_", "GROQ_", "MISTRAL_", "DEEPSEEK_")


def _model_names() -> set[str]:
    from autobot_shared.ssot_hosted_models import HOSTED_PROVIDER_DEFAULT_MODELS

    names = {m for models in HOSTED_PROVIDER_DEFAULT_MODELS.values() for m in models.values()}
    tree = parse_cache.parse((repo_root() / "autobot_shared" / "ssot_constants.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            if any(isinstance(t, ast.Name) and t.id.startswith(_VENDOR_PREFIXES) for t in node.targets):
                names.add(node.value.value)
    from autobot_shared.ssot_hosted_models import HUGGINGFACE_KNOWN_CHAT_MODELS

    names.update(HUGGINGFACE_KNOWN_CHAT_MODELS)
    return names


def _literals(source: str) -> list[tuple[int, str]]:
    tree = parse_cache.parse(source)
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

    for node in ast.walk(parse_cache.parse(source)):
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


# ---------------------------------------------------------------------------
# #20884: a pinned Claude ID is written once, in autobot_shared/ssot_claude_models.py. Pinned IDs
# had spread through code, config, templates, the frontend and the docs, all a generation stale.
# This extends the guards above from "provider modules" to every tracked file of the types below.
#
# SCOPE (declared, #15897): tracked *.py *.ts *.vue *.json *.yml *.yaml *.j2 *.toml *.sh *.env.example under _SCAN_ROOTS, and docs/**/*.md. Tests,
# node_modules and the historical areas in _HISTORICAL are not read. A ratchet: each file below holds
# at most the count recorded, and a count that fell must be lowered here (the number only falls).
# ---------------------------------------------------------------------------

#: A pinned id (``claude-sonnet-5-5``, or the version-first ``claude-3-opus-20240229``) or a quoted tier-only literal (``'claude-sonnet'``): the latter is how a
#: frontend or table once mapped every model of a tier to one window or price (#20884).
_CLAUDE_ID = re.compile(
    r"""claude-(?:opus|sonnet|haiku|fable)-\d|claude-\d(?:-\d)?-(?:opus|sonnet|haiku)|['"`]claude-(?:opus|sonnet|haiku|fable)['"`]"""
)
_SCAN_ROOTS = (
    "autobot-backend",
    "autobot-frontend",
    "autobot-slm-backend",
    "autobot-slm-frontend",
    "autobot-infrastructure",
    "autobot-npu-worker",
    "autobot-plugins",
    "autobot_shared",
    "plugins",
    "libs",
    "docs",
)
_SCAN_EXTS = ("*.py", "*.ts", "*.vue", "*.json", "*.yml", "*.yaml", "*.j2", "*.toml", "*.sh", "*.env.example")
_SCAN_PATTERNS = (*(f"{r}/{e}" for r in _SCAN_ROOTS if r != "docs" for e in _SCAN_EXTS), "docs/*.md")
_TEST_PART = re.compile(
    r"(^|/)(tests?|test_[^/]*|[^/]*_test\.py|[^/]*\.(test|spec)\.ts|conftest\.py|node_modules|__tests__)(/|$)"
)
_HISTORICAL = ("docs/reports/", "docs/design/mockups/")
_PRICING = "pricing data: rows keyed by model id, not a default"
_CLAUDE_HOMES: dict[str, str] = {
    "autobot_shared/ssot_claude_models.py": "the SSOT",
    "autobot_shared/ssot_constants.py": "model-name constants for every vendor (history, pricing keys)",
    "autobot_shared/model_pricing.py": _PRICING,
    "autobot-backend/config/llm_models.yaml": "the per-model parameter registry",
    "autobot-backend/config/context_windows.yaml": "the per-model context-window table",
}
#: file -> (most instances allowed, why they remain). Each is a follow-up, not a decision to keep.
_CLAUDE_BASELINE: dict[str, tuple[int, str]] = {
    "autobot-backend/llm_shared/model_param_registry.py": (1, "docstring usage example"),
    "autobot-backend/services/llm_cost_tracker.py": (
        5,
        "substring keys of the price fallback (each maps to a current SSOT row, none states a price or window) and a docstring example",
    ),
    "docs/api/USAGE_METERING_API.md": (1, "prose naming the substring-pattern heuristic"),
    "autobot-backend/llm_shared/pricing/crosscheck.py": (2, "prose: describes how external catalogues spell a model"),
    "autobot-backend/llm_shared/pricing/anthropic_source.py": (
        8,
        "older 3.x/4.x baseline rows keyed by literal; the current generation is read from model_pricing",
    ),
    "autobot-backend/llm_shared/pricing/vertexai_source.py": (
        5,
        "Vertex versioned ids; the 5.x Vertex ids are not known",
    ),
    "autobot-backend/llm_shared/providers/vertexai.py": (5, "Vertex versioned ids; the 5.x Vertex ids are not known"),
    "autobot-backend/llm_shared/providers/bedrock.py": (
        9,
        "Bedrock's own ids (anthropic.claude-3-...), a catalogue of that vendor",
    ),
    "autobot-backend/migrations/versions/20260525_042_agent_org_nodes_haiku_tier.py": (2, "migration history, frozen"),
    "autobot_shared/ssot_hosted_models.py": (
        4,
        "Bedrock's own ids (anthropic.claude-...-v1:0), not the first-party ids",
    ),
    "autobot-frontend/src/types/generated/api.ts": (2, "generated from the OpenAPI text; regenerated, not edited"),
    # Version-first (Claude 3.x) ids, counted since the matcher learned that order (#20884 review); each is a follow-up.
    "autobot-frontend/src/components/analytics/LLMPatternDashboard.vue": (
        3,
        "a model <select> listing Claude 3 values",
    ),
    "autobot-frontend/src/constants/providerFallbackEvents.ts": (1, "doc-comment example"),
    "autobot_shared/ssot_config.py": (2, "docstring examples"),
    "docs/api/COMPREHENSIVE_API_DOCUMENTATION.md": (2, "prose/examples naming a Claude 3 id"),
    "docs/api/public-api-reference.md": (2, "prose/examples naming a Claude 3 id"),
    "docs/architecture/DISTRIBUTED_ARCHITECTURE.md": (3, "prose/examples naming a Claude 3 id"),
    "docs/architecture/SSOT_CONFIGURATION_ARCHITECTURE.md": (1, "prose/examples naming a Claude 3 id"),
    "docs/developer/04-configuration.md": (2, "prose/examples naming a Claude 3 id"),
    "docs/developer/DEVELOPER_SETUP.md": (1, "prose/examples naming a Claude 3 id"),
    "docs/developer/HARDCODING_PREVENTION.md": (1, "prose/examples naming a Claude 3 id"),
    "docs/guides/chat-ollama-configuration.md": (1, "prose/examples naming a Claude 3 id"),
    "docs/developer/CLAUDE_WORKFLOW.md": (3, "model-tier table; edited in a separate PR that also touches this file"),
}


def _claude_scan_files(root) -> list[str]:
    try:
        paths = tracked_paths(root, *_SCAN_PATTERNS)
    except EmptyEnumeration:
        return []
    return [p for p in paths if not _TEST_PART.search(p) and not p.startswith(_HISTORICAL)]


REACH_CLAUDE_IDS = declare(
    "claude-model-id-literal-sites",
    discover=_claude_scan_files,
    what="tracked py/ts/vue/json/yml/yaml/j2/toml/sh/env.example and docs md files, scanned for a pinned Claude model id",
    roots=_SCAN_ROOTS,
    floor=6834,  # mid-window: population 7034, window [6634, 7034]
    growth=400,
)


def claude_id_counts(sources: dict[str, str]) -> dict[str, int]:
    """path -> number of pinned Claude ids in its text (only paths with at least one)."""
    counts = {path: len(_CLAUDE_ID.findall(text)) for path, text in sources.items()}
    return {path: n for path, n in counts.items() if n}


def _claude_tree_counts() -> dict[str, int]:
    root = repo_root()
    sources = {
        rel: (root / rel).read_text(encoding="utf-8", errors="replace") for rel in REACH_CLAUDE_IDS.examined(root)
    }
    return claude_id_counts(sources)


def _claude_violations(counts: dict[str, int]) -> list[str]:
    out = []
    for path, n in sorted(counts.items()):
        if path in _CLAUDE_HOMES:
            continue
        allowed = _CLAUDE_BASELINE.get(path, (0, ""))[0]
        if n > allowed:
            out.append(f"{path}: {n} pinned Claude id(s), {allowed} allowed")
    return out


def test_no_file_outside_the_ssot_homes_pins_a_claude_model_id():
    violations = _claude_violations(_claude_tree_counts())
    assert not violations, (
        "read the id from autobot_shared.ssot_claude_models (or write a tier alias: opus/sonnet/haiku/fable) (#20884):\n  "
        + "\n  ".join(violations)
    )


def test_the_claude_baseline_only_falls():
    counts = _claude_tree_counts()
    stale = [
        f"{p}: baseline {n}, now {counts.get(p, 0)}" for p, (n, _) in _CLAUDE_BASELINE.items() if counts.get(p, 0) < n
    ]
    assert not stale, "lower these baseline entries, the ratchet only falls (#20884):\n  " + "\n  ".join(stale)


def test_claude_homes_are_all_real_files():
    root = repo_root()
    assert all((root / p).is_file() for p in _CLAUDE_HOMES), "a home path in _CLAUDE_HOMES no longer exists"


def test_the_claude_matcher_catches_a_planted_second_definition_and_ignores_aliases():
    control = {"autobot-backend/x.py": 'MODEL = "claude-sonnet-5-5"\n', "docs/y.md": "use `claude-opus-9`"}
    assert _claude_violations(claude_id_counts(control)) == [
        "autobot-backend/x.py: 1 pinned Claude id(s), 0 allowed",
        "docs/y.md: 1 pinned Claude id(s), 0 allowed",
    ]
    tier_only = {"f.ts": "const W = { 'claude-sonnet': 200_000, \"claude-opus\": 1 }"}
    assert claude_id_counts(tier_only) == {"f.ts": 2}
    legacy_order = {"g.py": 'M = "claude-3-opus-20240229"\nN = "claude-3-5-sonnet-20241022"\n'}
    assert claude_id_counts(legacy_order) == {"g.py": 2}
    clean = {"a.py": 'MODEL = "sonnet"\nx = CLAUDE_SONNET\n', "b.md": "claude-sonnet (no digit) and claude-code"}
    assert claude_id_counts(clean) == {}
    # the sweep sees real files: the SSOT itself must register, or the matcher/enumeration is broken
    assert "autobot_shared/ssot_claude_models.py" in _claude_tree_counts()
