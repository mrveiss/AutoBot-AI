# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The backend's sentence models are code-pinned: one name each, one loader, a pinned revision (#19430).

Owner decision (2026-10-24): the chunker's sentence model and its fallbacks have no config
override. Before this, the name was a literal in three chunker classes and a config-overridable
default in the entity resolver; complete.yaml carried an unread key naming a different model; and
every SentenceTransformer load resolved the Hub's moving default revision.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from repo_tests._paths import repo_root

from autobot_shared.pinned_model_registry import get_pinned_revision

_BASE = repo_root() / "autobot-backend" / "utils" / "semantic_chunker_base.py"
_SCOPES = ("autobot-backend", "autobot_shared")
_NAME_LITERAL = re.compile(r"""["'](?:sentence-transformers/)?all-(?:MiniLM-L6|mpnet-base|MiniLM-L12)-v2["']""")


def _production_sources() -> list[Path]:
    files = [p for scope in _SCOPES for p in (repo_root() / scope).rglob("*.py")]
    return sorted(
        p for p in files if not (p.name.endswith("_test.py") or p.name.startswith("test_") or "tests" in p.parts)
    )


def _constructions(tree: ast.AST) -> list[int]:
    """Line numbers of every ``SentenceTransformer(...)`` call."""
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and getattr(node.func, "id", getattr(node.func, "attr", None)) == "SentenceTransformer"
    ]


def _base_constants() -> dict[str, object]:
    tree = ast.parse(_BASE.read_text(encoding="utf-8"))
    wanted = {"SENTENCE_EMBEDDING_MODEL", "SENTENCE_EMBEDDING_FALLBACKS"}
    return {
        t.id: ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        for t in node.targets
        if isinstance(t, ast.Name) and t.id in wanted
    }


def test_the_detectors_see_a_construction_and_a_name_literal() -> None:
    assert _constructions(ast.parse("m = SentenceTransformer('x')\nn = st.SentenceTransformer('y')\n")) == [1, 2]
    assert _constructions(ast.parse("m = load_sentence_transformer('x')\n")) == []
    assert _NAME_LITERAL.search('model = "all-MiniLM-L6-v2"')
    assert not _NAME_LITERAL.search("Local semantic chunker (all-MiniLM-L6-v2) - fallback")


def test_one_loader_constructs_every_sentence_transformer() -> None:
    files = _production_sources()
    assert len(files) > 500, f"only {len(files)} production files scanned"
    sites = {
        f"{p.relative_to(repo_root()).as_posix()}:{line}"
        for p in files
        for line in _constructions(ast.parse(p.read_text(encoding="utf-8")))
    }
    assert len(sites) == 1 and next(iter(sites)).startswith("autobot-backend/utils/semantic_chunker_base.py:"), sites


def test_each_model_name_is_written_once() -> None:
    """Once outside the pin table, which is keyed by repo id for every model it pins."""
    registry = repo_root() / "autobot_shared" / "pinned_model_registry.py"
    hits = [
        f"{p.relative_to(repo_root()).as_posix()}: {m.group(0)}"
        for p in _production_sources()
        if p != registry
        for m in _NAME_LITERAL.finditer(p.read_text(encoding="utf-8"))
    ]
    assert len(hits) == 3 and all(h.startswith("autobot-backend/utils/semantic_chunker_base.py") for h in hits), hits


def _is_pin(revision: str) -> bool:
    """A full lowercase commit SHA -- never a branch, a tag, or a short or upper-case id."""
    return re.fullmatch(r"[0-9a-f]{40}", revision) is not None


def _loader_is_verified(source: str) -> bool:
    """``load_sentence_transformer`` loads through ``load_verified(model_name, lambda revision: ...)``
    and passes that ``revision`` on, so the pin is used and the digests are checked before return."""
    loader = next(
        (n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == "load_sentence_transformer"),
        None,
    )
    if loader is None:
        return False
    for call in (
        n for n in ast.walk(loader) if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "load_verified"
    ):
        if len(call.args) != 2 or ast.unparse(call.args[0]) != "model_name" or not isinstance(call.args[1], ast.Lambda):
            continue
        fn = call.args[1]
        body = fn.body
        if [a.arg for a in fn.args.args] == ["revision"] and isinstance(body, ast.Call):
            if getattr(body.func, "id", "") == "SentenceTransformer":
                return any(k.arg == "revision" and ast.unparse(k.value) == "revision" for k in body.keywords)
    return False


def test_the_pin_detector_refuses_anything_but_a_full_sha() -> None:
    sha = "ab" * 20  # commit-shaped, low entropy: a real-looking hex literal trips detect-secrets
    assert _is_pin(sha)
    for bad in ("main", "", sha[:-1], sha.upper(), sha + "c", "v1.0"):
        assert not _is_pin(bad), bad


def test_the_loader_detector_refuses_an_unverified_or_unpinned_loader() -> None:
    head = "def load_sentence_transformer(model_name, **kwargs):\n"
    good = (
        head
        + "    (m,) = load_verified(model_name, lambda revision: SentenceTransformer(model_name, revision=revision))\n"
    )
    assert _loader_is_verified(good)
    for bad in (
        head
        + "    return SentenceTransformer(model_name, revision=get_pinned_revision(model_name))\n",  # no digest check
        head
        + "    (m,) = load_verified(model_name, lambda revision: SentenceTransformer(model_name))\n",  # pin dropped
        head
        + "    (m,) = load_verified(model_name, lambda revision: SentenceTransformer(model_name, revision=None))\n",
        head + "    (m,) = load_verified('x', lambda revision: SentenceTransformer(model_name, revision=revision))\n",
        "def other(model_name):\n    return None\n",
    ):
        assert not _loader_is_verified(bad), bad


def test_every_sentence_model_has_a_pinned_revision() -> None:
    constants = _base_constants()
    names = [constants["SENTENCE_EMBEDDING_MODEL"], *constants["SENTENCE_EMBEDDING_FALLBACKS"]]
    assert len(names) == 3
    for name in names:
        assert _is_pin(get_pinned_revision(name)), name


def test_the_loader_loads_at_the_pin_and_verifies_the_digests() -> None:
    assert _loader_is_verified(_BASE.read_text(encoding="utf-8"))
