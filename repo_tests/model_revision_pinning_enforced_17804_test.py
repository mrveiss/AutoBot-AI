# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every load of a FIXED model repo is pinned, and cannot fail open (#17804).

`docs/developer/MODEL_REVISION_PINNING.md` prescribes `get_pinned_revision` ->
`from_pretrained(repo_id, revision=...)` -> `verify_cached_model(repo_id)`.
Nothing asserted any of it: no file under `repo_tests/` referenced
`get_pinned_revision`, and the only guard that scanned `from_pretrained` checked
an unrelated property. Every site that followed the rule did so voluntarily.

## Two discriminators, and both obvious ones are wrong

**Not `from_pretrained` alone.** Keying on it returns 20 calls, flags three
DELIBERATE exemptions -- `layer_inference.py` and `model_inspector.py` load a
caller-supplied `model_name` and say so with `# nosec B615` -- and MISSES the one
real omission, because that is `pipeline()`, the transformers factory. Three
false positives and one false negative at once, which is worse than no guard
because it would look like it had checked.

**Not "the model argument is a string literal" either.** That was my first
proposal and it exempts the very site this issue is about:
`hf_pipeline(..., model=_WHISPER_MODEL)` holds the repo id in a module constant
one line up, so a literal-only rule reports the tree clean. The property that
makes a repo pinnable is that its id is **knowable without running the program**,
so a name bound to a string literal at module *or* function scope counts. That
widening takes the population from 5 to 14.

## What "pinned" has to mean, because `revision=` is not enough

#17124 found a **fail-open** bug: assigning a model before `verify_cached_model`
ran left a tampered model reachable when a caller's broad `except` swallowed
`ModelIntegrityError`. So a load can pass `revision=`, call `verify_cached_model`,
and still fail open if the order is wrong and nothing distinguishes an integrity
failure from a generic one.

Two shapes satisfy the property, and this guard accepts both:

* `load_verified(repo_id, *loaders)` (`autobot_shared/pinned_model_registry.py`),
  which raises before returning anything;
* the inline form -- load into locals, verify, *then* assign -- paired with a
  **named** `except ModelIntegrityError`. `multimodal_processor/processors/`
  does this correctly at nine sites, each with a `SECURITY:` log.

The second is not a lesser state, and saying so was a mistake worth recording:
it is #17124's fix applied by hand at sites that predate the helper.

## Out of scope, with the reason

`knowledge/connectors/audio_connector.py` uses the `openai-whisper` pip package
(`import whisper`) with a caller-chosen model size. It is a **third** mechanism,
not a missed instance: the HuggingFace registry has nothing to say about it.
"""

from __future__ import annotations

import ast
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare

_TREES = ("autobot-backend", "autobot_shared", "autobot-slm-backend")

#: The helper that makes the order safe by construction.
_HELPER = "load_verified"

#: The named handler that makes the inline form safe.
_INTEGRITY_ERROR = "ModelIntegrityError"


def _production_files(root: Path) -> list[Path]:
    """Every production `.py` under the backends. The declared population."""
    files: list[Path] = []
    for tree in _TREES:
        directory = root / tree
        if not directory.is_dir():
            continue
        for path in directory.rglob("*.py"):
            rel = path.relative_to(root).as_posix()
            if rel.endswith("_test.py") or "/tests/" in rel:
                continue
            files.append(path)
    return files


#: **3,027** production modules today, measured by the declaration mechanism
#: rather than estimated -- my own ad-hoc count said ~2,705, and the difference
#: is why the floor is pinned to a measurement and not to a guess. The band is
#: 2,900..3,100; beyond it the floor is ratcheted deliberately.
REACH = declare(
    "model-revision-pinning-sweep",
    discover=_production_files,
    floor=2900,
    growth=200,
    skips=0,
    what="production Python modules that could load a model",
)


def _string_constants(scope: ast.AST) -> dict[str, str]:
    """Names bound to a string literal directly in *scope*'s body."""
    found: dict[str, str] = {}
    for node in getattr(scope, "body", []):
        targets = (
            node.targets if isinstance(node, ast.Assign) else ([node.target] if isinstance(node, ast.AnnAssign) else [])
        )
        value = getattr(node, "value", None)
        if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                found[target.id] = value.value
    return found


def _factory_aliases(module: ast.Module) -> set[str]:
    """Local names bound to the transformers `pipeline` factory, however aliased."""
    names: set[str] = set()
    for node in ast.walk(module):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("transformers"):
            names |= {alias.asname or alias.name for alias in node.names if alias.name == "pipeline"}
    return names


def _model_argument(call: ast.Call, *, is_factory: bool) -> ast.AST | None:
    """The argument naming the repo, for either loader API."""
    kwargs = {kw.arg: kw.value for kw in call.keywords}
    named = kwargs.get("model") if is_factory else kwargs.get("pretrained_model_name_or_path")
    if named is not None:
        return named
    index = 1 if is_factory else 0
    return call.args[index] if len(call.args) > index else None


def _fixed_repo_loads(path: Path, rel: str) -> list[tuple[int, bool]]:
    """`(lineno, passes_revision)` for each load whose repo id is knowable statically."""
    try:
        module = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return []
    aliases = _factory_aliases(module)
    module_constants = _string_constants(module)
    scopes: list[tuple[ast.AST, dict[str, str]]] = [(module, module_constants)]
    for node in ast.walk(module):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            scopes.append((node, {**module_constants, **_string_constants(node)}))

    found: dict[int, bool] = {}
    for scope, constants in scopes:
        for call in ast.walk(scope):
            if not isinstance(call, ast.Call):
                continue
            from_pretrained = isinstance(call.func, ast.Attribute) and call.func.attr == "from_pretrained"
            factory = isinstance(call.func, ast.Name) and call.func.id in aliases
            if not (from_pretrained or factory):
                continue
            model = _model_argument(call, is_factory=factory)
            literal = isinstance(model, ast.Constant) and isinstance(model.value, str)
            named_constant = isinstance(model, ast.Name) and model.id in constants
            if not (literal or named_constant):
                continue  # caller-supplied: exempt BY THE RULE, not by a list
            found[call.lineno] = "revision" in {kw.arg for kw in call.keywords}
    del rel
    return sorted(found.items())


def _module_is_order_safe(path: Path) -> bool:
    """True when this module either uses the helper or names the integrity error."""
    try:
        module = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return False
    for node in ast.walk(module):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == _HELPER:
            return True
        if isinstance(node, ast.ExceptHandler):
            names = node.type
            candidates = names.elts if isinstance(names, ast.Tuple) else [names]
            for candidate in candidates:
                if isinstance(candidate, ast.Name) and candidate.id == _INTEGRITY_ERROR:
                    return True
                if isinstance(candidate, ast.Attribute) and candidate.attr == _INTEGRITY_ERROR:
                    return True
    return False


def _sweep() -> list[tuple[str, int, bool, bool]]:
    """`(rel, lineno, passes_revision, module_is_order_safe)` per fixed-repo load."""
    root = repo_root()
    rows: list[tuple[str, int, bool, bool]] = []
    for path in _production_files(root):
        rel = path.relative_to(root).as_posix()
        loads = _fixed_repo_loads(path, rel)
        if not loads:
            continue
        safe = _module_is_order_safe(path)
        rows.extend((rel, lineno, pinned, safe) for lineno, pinned in loads)
    return rows


def test_the_sweep_finds_the_loads_we_know_exist() -> None:
    """Non-vacuity beyond the reach floor: the population must be recognisable."""
    rows = _sweep()
    assert len(rows) >= 10, (
        f"only {len(rows)} fixed-repo model load(s) found; the tree has at least ten across "
        "multimodal_processor and ai_hardware_accelerator, so the discriminator has stopped "
        "recognising them"
    )


def test_every_fixed_repo_load_passes_a_revision() -> None:
    unpinned = [f"{rel}:{lineno}" for rel, lineno, pinned, _ in _sweep() if not pinned]
    assert not unpinned, (
        "these loads name a repo that is knowable statically, so they CAN be pinned, and are not:\n  "
        + "\n  ".join(unpinned)
        + "\n\nWithout revision= the load resolves against whatever the hub serves today "
        "(docs/developer/MODEL_REVISION_PINNING.md). A caller-supplied model is exempt by the "
        "rule; a module constant is not."
    )


def test_every_module_that_pins_cannot_fail_open() -> None:
    """`revision=` is not enough -- #17124's bug was the ORDER, not the argument."""
    unsafe = sorted({rel for rel, _, _, safe in _sweep() if not safe})
    assert not unsafe, (
        "these modules load a pinned model but neither use load_verified nor handle "
        f"{_INTEGRITY_ERROR} by name:\n  "
        + "\n  ".join(unsafe)
        + f"\n\n#17124: assigning before verify_cached_model ran left a tampered model reachable "
        "when a broad except swallowed the integrity error. Either route the load through "
        "load_verified, which raises before returning anything, or keep the inline form and "
        f"catch {_INTEGRITY_ERROR} separately from a generic failure."
    )
