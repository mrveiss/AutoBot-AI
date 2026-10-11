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


def _parse_source(path, rel: str, unparsed: list[str]):
    """The AST of *path*, or ``None`` after recording *rel*: an unparsed file is a gap, never a pass."""
    try:
        return ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError as exc:
        unparsed.append(f"{rel}: {exc.msg}")
        return None


def _audio_mime_maps(unparsed: list[str]) -> list[tuple[str, int, int]]:
    """Every dict literal mapping ``audio/*`` keys to ``.ext`` values; unparsed files go to *unparsed*."""
    found: list[tuple[str, int, int]] = []
    root = repo_root()
    for tree in ("autobot-backend", "autobot_shared"):
        for path in (root / tree).rglob("*.py"):
            rel = path.relative_to(root).as_posix()
            if rel.endswith("_test.py") or "/tests/" in rel:
                continue
            mod = _parse_source(path, rel, unparsed)
            if mod is None:
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
    unparsed: list[str] = []
    maps = _audio_mime_maps(unparsed)
    assert not unparsed, f"Files the guard could not parse (it did not look at them): {unparsed}"
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
    # #17778: the load attempt lives in `_attempt_load`, called by `get_whisper_pipeline`.
    mod = _module(_PIPELINE)
    assert _mentions(_function(mod, "get_whisper_pipeline"), "_attempt_load"), "the loader no longer attempts a load"
    loader = _function(mod, "_attempt_load")
    calls = [n for n in ast.walk(loader) if isinstance(n, ast.Call)]

    verified = [c for c in calls if isinstance(c.func, ast.Name) and c.func.id == "load_verified"]
    assert verified, (
        "the Whisper pipeline is not loaded through load_verified, so the revision, the "
        "integrity check and their ORDER are each a separate thing to get right here "
        "(autobot_shared/pinned_model_registry.py; #17124 is why the order matters)"
    )

    pipeline_calls = [c for c in calls if isinstance(c.func, ast.Name) and c.func.id == "hf_pipeline"]
    assert pipeline_calls, "_attempt_load no longer calls hf_pipeline; this guard's premise moved"
    for call in pipeline_calls:
        assert "revision" in {kw.arg for kw in call.keywords}, (
            "the pipeline factory is called without revision=, so it resolves against whatever "
            "the hub serves today even though load_verified supplied a pinned one"
        )


def test_every_caller_reaches_the_same_inference_function() -> None:
    """One body, not two that look alike.

    #17778 removed the media ``AudioPipeline`` wrapper, the second caller this guard
    used to name: the pipeline module now only DEFINES ``transcribe_bytes``, and the
    voice route is the caller that must reach it instead of carrying its own copy.
    """
    defined = {n.name for n in ast.walk(_module(_PIPELINE)) if isinstance(n, ast.FunctionDef)}
    assert "transcribe_bytes" in defined, f"{_PIPELINE} no longer defines the shared transcribe_bytes"
    names = {
        node.func.id
        for node in ast.walk(_module(_VOICE))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "transcribe_bytes" in names, f"{_VOICE} does not call the shared transcribe_bytes"


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


# ── #17778: nothing outside the shared module runs Whisper itself ─────────────

_PROVIDER = "autobot-backend/voice_processing/providers/whisper_provider.py"
_MULTIMODAL_VOICE = "autobot-backend/multimodal_processor/processors/voice.py"


def _mentions(node: ast.AST, name: str) -> bool:
    return any(
        (isinstance(n, ast.Name) and n.id == name) or (isinstance(n, ast.Attribute) and n.attr == name)
        for n in ast.walk(node)
    )


def _bound_pipeline_names(tree: ast.AST) -> set[str]:
    """Source text of every name or attribute target bound from ``get_whisper_pipeline()``.

    Covers `p = ...`, `p: T = ...`, `(p := ...)` and `self._p = ...`; a call on any of
    them is a direct invocation, whatever the binding syntax.
    """
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        elif isinstance(node, ast.NamedExpr):
            targets, value = [node.target], node.value
        else:
            continue
        if _mentions(value, "get_whisper_pipeline"):
            bound.update(ast.unparse(t) for t in targets if isinstance(t, (ast.Name, ast.Attribute)))
    return bound


def direct_whisper_invocations(source: str) -> list[int]:
    """Line numbers where *source* runs Whisper itself instead of via the shared entry points.

    Three shapes: building an ASR pipeline (`pipeline("automatic-speech-recognition", ...)`),
    `<...whisper...>.generate(...)`, and calling a name or attribute that was bound from
    `get_whisper_pipeline()` (`pipe = get_whisper_pipeline(); pipe(...)`, also annotated,
    walrus and `self._pipe` bindings).
    """
    tree = ast.parse(source)
    bound = _bound_pipeline_names(tree)
    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        asr = (
            bool(node.args)
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == ("automatic-speech-recognition")
        )
        generate = (
            isinstance(func, ast.Attribute) and func.attr == "generate" and "whisper" in ast.unparse(func).lower()
        )
        bound_call = isinstance(func, (ast.Name, ast.Attribute)) and ast.unparse(func) in bound
        if asr or generate or bound_call:
            hits.append(node.lineno)
    return hits


def test_the_detector_fires_on_each_shape_and_not_on_the_shared_entry_points() -> None:
    assert direct_whisper_invocations("pipe = get_whisper_pipeline()\npipe(path)\n") == [2]
    assert direct_whisper_invocations("p = hf_pipeline('automatic-speech-recognition', model=m)\n") == [1]
    assert direct_whisper_invocations("ids = self.whisper_model.generate(x)\n") == [1]
    ok = "pipe = get_whisper_pipeline()\ntranscribe_path(pipe, path)\n"
    assert direct_whisper_invocations(ok) == []


def test_the_detector_follows_annotated_walrus_and_attribute_bindings() -> None:
    assert direct_whisper_invocations("pipe: Any = get_whisper_pipeline()\npipe(path)\n") == [2]
    assert direct_whisper_invocations("if (pipe := get_whisper_pipeline()):\n    pipe(path)\n") == [2]
    assert direct_whisper_invocations("self._pipe = get_whisper_pipeline()\nself._pipe(path)\n") == [2]
    assert direct_whisper_invocations("self._pipe = get_whisper_pipeline()\nother(path)\n") == []


def test_only_the_shared_module_runs_whisper_directly() -> None:
    root = repo_root()
    offenders: list[str] = []
    unparsed: list[str] = []
    for tree in ("autobot-backend", "autobot_shared"):
        for path in (root / tree).rglob("*.py"):
            rel = path.relative_to(root).as_posix()
            if rel == _PIPELINE or rel.endswith("_test.py") or "/tests/" in rel or "/test_" in rel:
                continue
            if _parse_source(path, rel, unparsed) is None:
                continue
            offenders += [
                f"{rel}:{ln}" for ln in direct_whisper_invocations(path.read_text(encoding="utf-8", errors="replace"))
            ]
    assert not unparsed, f"Files the guard could not parse (it did not look at them): {unparsed}"
    assert not offenders, f"Whisper is run directly outside media/audio/pipeline.py: {offenders}"


def test_provider_and_multimodal_voice_call_the_shared_entry_points() -> None:
    def called(rel: str) -> set[str]:
        return {
            n.func.id if isinstance(n.func, ast.Name) else n.func.attr
            for n in ast.walk(_module(rel))
            if isinstance(n, ast.Call) and isinstance(n.func, (ast.Name, ast.Attribute))
        }

    assert {"transcribe_path", "get_whisper_pipeline"} <= called(_PROVIDER)
    assert {"transcribe_array", "get_whisper_pipeline"} <= called(_MULTIMODAL_VOICE)


def test_an_unparsable_file_is_recorded_not_skipped(tmp_path) -> None:
    """Contrast pair: a SyntaxError is reported to the caller, a valid file is not."""
    broken, fine = tmp_path / "broken.py", tmp_path / "fine.py"
    broken.write_text("def (:\n", encoding="utf-8")
    fine.write_text("x = 1\n", encoding="utf-8")
    unparsed: list[str] = []
    assert _parse_source(broken, "broken.py", unparsed) is None
    assert _parse_source(fine, "fine.py", unparsed) is not None
    assert len(unparsed) == 1 and unparsed[0].startswith("broken.py")
