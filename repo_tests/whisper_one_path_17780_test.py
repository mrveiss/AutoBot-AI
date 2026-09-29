# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One Whisper inference path, one MIME map, and that path is pinned (#17780).

`api/voice.py` and `media/audio/pipeline.py` each held the same transformers
Whisper inference -- same model, same loader, same temp-file-plus-`to_thread`
dance -- differing only in the MIME map and the result dict. The voice route even
imported the **private** `_get_whisper_pipeline` out of the other module, so one
loader served two features while only one of them was pinned.

The two MIME maps had already drifted: 8 entries against 6, the shorter one
missing `audio/aac` and `audio/flac`. **The same mapping in two places is one
mapping that disagrees with itself**, which is what makes a duplicate worth a
guard rather than a tidy-up.

Scope note: this asserts the pin for **this** call site only. The general rule --
every loader of a registry-known model passes `revision=` -- is #17804, which
needs its own contrast pairs and must cover the `pipeline()` factory as well as
`from_pretrained`. Keying on `from_pretrained` alone finds 19 sites, flags three
DELIBERATE exemptions (a caller-supplied `model_name` cannot be pinned) and
misses this one, which is a `pipeline()` call.
"""

from __future__ import annotations

import ast

from repo_tests._paths import repo_root

_PIPELINE = "autobot-backend/media/audio/pipeline.py"
_VOICE = "autobot-backend/api/voice.py"


def _module(rel: str) -> ast.Module:
    return ast.parse((repo_root() / rel).read_text(encoding="utf-8"))


def _audio_mime_maps() -> list[tuple[str, int, int]]:
    """Every dict literal mapping ``audio/*`` keys to ``.ext`` values."""
    found: list[tuple[str, int, int]] = []
    root = repo_root()
    for tree in ("autobot-backend", "autobot_shared"):
        for path in (root / tree).rglob("*.py"):
            rel = path.relative_to(root).as_posix()
            if rel.endswith("_test.py") or "/tests/" in rel:
                continue
            try:
                mod = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
            except SyntaxError:
                continue
            for node in ast.walk(mod):
                if not isinstance(node, ast.Dict) or not node.keys:
                    continue
                keys = [k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)]
                values = [v.value for v in node.values if isinstance(v, ast.Constant)]
                if len(keys) != len(node.keys) or not keys or not all(k.startswith("audio/") for k in keys):
                    continue
                if values and all(isinstance(v, str) and v.startswith(".") for v in values):
                    found.append((rel, node.lineno, len(keys)))
    return found


def test_exactly_one_audio_mime_map_exists() -> None:
    """Two of these drifted before anyone noticed; a third would drift again."""
    maps = _audio_mime_maps()
    assert len(maps) == 1, (
        "expected one audio MIME -> suffix map, found "
        f"{len(maps)}: {[f'{rel}:{ln} ({n} entries)' for rel, ln, n in maps]}"
    )
    rel, _, entries = maps[0]
    assert rel == _PIPELINE, f"the shared map moved to {rel}; update this guard or move it back"
    assert entries >= 8, (
        f"the shared map has {entries} entries; it was the SUPERSET of the two that drifted "
        "(8 vs 6), so losing one is losing a format the pipeline used to accept"
    )


def test_the_voice_route_imports_no_private_symbol_from_the_pipeline() -> None:
    """A private name crossing a module boundary is how one loader served two features."""
    offenders = [
        f"{node.module}.{alias.name}"
        for node in ast.walk(_module(_VOICE))
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("media.audio")
        for alias in node.names
        if alias.name.startswith("_")
    ]
    assert not offenders, (
        "api/voice.py imports private symbol(s) from the media pipeline: "
        + ", ".join(offenders)
        + " -- use the public entry point, or the private one becomes a second public API"
    )


def _function(mod: ast.Module, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    for node in mod.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{name} is not defined at module level; this guard's premise moved")


def test_the_whisper_loader_goes_through_load_verified() -> None:
    """The canonical path, not the three steps by hand.

    `load_verified` exists because writing them out has a **fail-open** failure
    mode: #17124 found that assigning the model before `verify_cached_model` ran
    left a tampered model reachable when a caller's broad `except` swallowed
    `ModelIntegrityError`. `get_whisper_pipeline` has exactly such an `except
    Exception`, so the hand-written form -- which is what the first version of
    #17780's fix used -- would have reproduced that bug while looking pinned.

    Asserting the helper rather than its three ingredients is therefore the
    stronger check: it pins the ORDER, which is the part that failed open.

    Scoped to this call site on purpose -- #17804 owns the general rule.
    """
    loader = _function(_module(_PIPELINE), "get_whisper_pipeline")
    calls = [n for n in ast.walk(loader) if isinstance(n, ast.Call)]

    verified = [c for c in calls if isinstance(c.func, ast.Name) and c.func.id == "load_verified"]
    assert verified, (
        "the Whisper pipeline is not loaded through load_verified, so the revision, the "
        "integrity check and their ORDER are each a separate thing to get right here "
        "(autobot_shared/pinned_model_registry.py; #17124 is why the order matters)"
    )

    pipeline_calls = [c for c in calls if isinstance(c.func, ast.Name) and c.func.id == "hf_pipeline"]
    assert pipeline_calls, "get_whisper_pipeline no longer calls hf_pipeline; this guard's premise moved"
    for call in pipeline_calls:
        assert "revision" in {kw.arg for kw in call.keywords}, (
            "the pipeline factory is called without revision=, so it resolves against whatever "
            "the hub serves today even though load_verified supplied a pinned one"
        )


def test_both_features_reach_the_same_inference_function() -> None:
    """The point of the consolidation: one body, not two that look alike."""
    for rel in (_PIPELINE, _VOICE):
        names = {
            node.func.id
            for node in ast.walk(_module(rel))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "transcribe_bytes" in names, f"{rel} does not call the shared transcribe_bytes"


def test_the_route_keeps_the_behaviour_the_pipeline_does_not_have() -> None:
    """Consolidation must not have quietly unified the two CONTRACTS.

    `/voice/transcribe` applies the silence-hallucination filter (#13104) and
    floors empty-text confidence at 0.0; the media pipeline applies no filter and
    floors at 0.5. Those are different promises about what "no words" means, and
    collapsing them would have changed one feature to match the other.
    """
    voice = _module(_VOICE)
    sync = _function(voice, "_whisper_sync")
    called = {n.func.id for n in ast.walk(sync) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "_drop_silence_hallucination" in called, (
        "the voice route no longer applies the silence-hallucination filter (#13104) -- the "
        "consolidation was supposed to share the inference, not the result shaping"
    )
    source = (repo_root() / _PIPELINE).read_text(encoding="utf-8")
    assert "_drop_silence_hallucination" not in source, (
        "the media pipeline has acquired the voice route's hallucination filter; it had no such "
        "filter before #17780 and gaining one is a behaviour change, not a consolidation"
    )
