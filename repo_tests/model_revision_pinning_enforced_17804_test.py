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

## Three shapes this guard could not see, and the review that found them

Review of the first version caught it committing its own subject three times --
a check reporting clean over what it had not examined. Each is now a fixture
pair below, because each would have been caught by one:

* **A parse failure vanished.** `_fixed_repo_loads` returned `[]` on
  `SyntaxError`, indistinguishable from "parsed fine, found nothing", while the
  reach floor counted the file as examined because `declare(discover=...)` is
  enforced over what was *listed*. Now `_parse` returns `None`, `_sweep`
  collects those separately, and :func:`test_every_production_module_parses`
  names them. Measured 2026-09-29: 3,027 listed, **0** unparseable, so this
  costs nothing today and stops costing the guard its eyesight tomorrow.
* **`registry.load_verified(...)` read as absent.** The helper check keyed on
  `node.func.id`, which only exists on `ast.Name`. Called the ordinary way
  through its module it is an `ast.Attribute`, so the canonical safe path --
  the one thing this guard exists to recognise -- scored unsafe. The exception
  check four lines below already handled both node types; the helper check did
  not.
* **A repo id one block deep escaped entirely.** `_string_constants` walked only
  `scope.body`, so `MODEL = "..."` inside an `if`/`try`/`with` was invisible --
  and because the id then resolved to neither a literal nor a known constant,
  the *load itself* dropped out of the sweep. Not a missed annotation: a missed
  finding, on the primary assertion.

## Known limitation, stated rather than implied (#17819)

:func:`test_every_module_that_pins_cannot_fail_open` is **module-scoped, and its
name says so**: `_module_is_order_safe` computes one verdict per module and
`_sweep` attaches it to every load in that module. A module with two loads, one
routed through the helper and one not, therefore reads safe. No current call
site has that shape, so nothing is being excused today, but the assertion does
not enforce per-load what the module docstring's first line claims. The correct
property is per-load and needs real dataflow analysis -- is *this* call the
helper, or inside a `try` whose handler names the integrity error, with verify
before assign -- which is more than this PR should carry. Filed as #17819.
"""

from __future__ import annotations

import ast
from functools import lru_cache
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


def _parse(path: Path) -> ast.Module | None:
    """The parsed module, or ``None`` when this file could not be read as Python.

    ``None`` is NOT ``[]``. The first version conflated them and that is the
    defect this guard is about: a file that fails to parse is *not examined*,
    while the reach floor -- enforced over what `_production_files` listed --
    still reads satisfied. :func:`test_every_production_module_parses` turns the
    `None` into a named failure. ``UnicodeDecodeError`` is caught for the same
    reason rather than papered over with ``errors="replace"``, which can yield
    mojibake that parses.
    """
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError, ValueError):
        return None


def _scope_statements(scope: ast.AST) -> list[ast.stmt]:
    """Every statement in *scope*, descending into blocks but not into scopes.

    An `if`, `try`, `with`, `for` or `while` does not introduce a scope in
    Python, so a name bound inside one is bound in the enclosing scope and is
    just as statically knowable. Walking only ``scope.body`` missed those and
    dropped the whole load; recursion stops at `FunctionDef`, `AsyncFunctionDef`
    and `ClassDef`, which DO introduce scopes and are handled separately.
    """
    statements: list[ast.stmt] = []
    pending = list(getattr(scope, "body", []))
    while pending:
        node = pending.pop()
        statements.append(node)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        for field in ("body", "orelse", "finalbody", "handlers"):
            pending.extend(getattr(node, field, []) or [])
    return statements


def _string_constants(scope: ast.AST) -> dict[str, str]:
    """Names bound to a string literal anywhere in *scope*, blocks included."""
    found: dict[str, str] = {}
    for node in _scope_statements(scope):
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


def _called_name(func: ast.AST) -> str | None:
    """The trailing name of a call target, for `f(...)` and `mod.f(...)` alike.

    Keying on `.id` alone scored `registry.load_verified(...)` as not-the-helper.
    """
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _model_argument(call: ast.Call, *, is_factory: bool) -> ast.AST | None:
    """The argument naming the repo, for either loader API."""
    kwargs = {kw.arg: kw.value for kw in call.keywords}
    named = kwargs.get("model") if is_factory else kwargs.get("pretrained_model_name_or_path")
    if named is not None:
        return named
    index = 1 if is_factory else 0
    return call.args[index] if len(call.args) > index else None


def _fixed_repo_loads(module: ast.Module) -> list[tuple[int, bool]]:
    """`(lineno, passes_revision)` for each load whose repo id is knowable statically."""
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
    return sorted(found.items())


def _module_is_order_safe(module: ast.Module) -> bool:
    """True when this module either uses the helper or names the integrity error.

    Module-scoped by construction -- see the limitation note in the module
    docstring and #17819.
    """
    for node in ast.walk(module):
        if isinstance(node, ast.Call) and _called_name(node.func) == _HELPER:
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


@lru_cache(maxsize=1)
def _sweep() -> tuple[tuple[tuple[str, int, bool, bool], ...], tuple[str, ...]]:
    """`(rows, unparsed)` -- findings, and the files no finding could come from.

    Cached: three assertions consume this and each one used to re-parse all
    3,027 modules, twice per file. One parse per file, once per session.
    """
    root = repo_root()
    rows: list[tuple[str, int, bool, bool]] = []
    unparsed: list[str] = []
    for path in _production_files(root):
        rel = path.relative_to(root).as_posix()
        module = _parse(path)
        if module is None:
            unparsed.append(rel)
            continue
        loads = _fixed_repo_loads(module)
        if not loads:
            continue
        safe = _module_is_order_safe(module)
        rows.extend((rel, lineno, pinned, safe) for lineno, pinned in loads)
    return tuple(rows), tuple(unparsed)


def _rows() -> tuple[tuple[str, int, bool, bool], ...]:
    return _sweep()[0]


def test_the_sweep_finds_the_loads_we_know_exist() -> None:
    """Non-vacuity beyond the reach floor: the population must be recognisable."""
    rows = _rows()
    assert len(rows) >= 10, (
        f"only {len(rows)} fixed-repo model load(s) found; the tree has at least ten across "
        "multimodal_processor and ai_hardware_accelerator, so the discriminator has stopped "
        "recognising them"
    )


def test_every_fixed_repo_load_passes_a_revision() -> None:
    unpinned = [f"{rel}:{lineno}" for rel, lineno, pinned, _ in _rows() if not pinned]
    assert not unpinned, (
        "these loads name a repo that is knowable statically, so they CAN be pinned, and are not:\n  "
        + "\n  ".join(unpinned)
        + "\n\nWithout revision= the load resolves against whatever the hub serves today "
        "(docs/developer/MODEL_REVISION_PINNING.md). A caller-supplied model is exempt by the "
        "rule; a module constant is not."
    )


def test_every_module_that_pins_cannot_fail_open() -> None:
    """`revision=` is not enough -- #17124's bug was the ORDER, not the argument."""
    unsafe = sorted({rel for rel, _, _, safe in _rows() if not safe})
    assert not unsafe, (
        "these modules load a pinned model but neither use load_verified nor handle "
        f"{_INTEGRITY_ERROR} by name:\n  "
        + "\n  ".join(unsafe)
        + f"\n\n#17124: assigning before verify_cached_model ran left a tampered model reachable "
        "when a broad except swallowed the integrity error. Either route the load through "
        "load_verified, which raises before returning anything, or keep the inline form and "
        f"catch {_INTEGRITY_ERROR} separately from a generic failure."
    )


def test_every_production_module_parses() -> None:
    """A file that cannot be parsed is NOT a file with nothing to find.

    The distinction the whole module is about, applied to itself: without this,
    an unparseable module contributes no findings while the reach floor counts
    it as examined, so the guard reports clean over a file it never read.
    """
    _, unparsed = _sweep()
    assert not unparsed, (
        f"{len(unparsed)} production module(s) could not be parsed, so this guard examined "
        "neither their loads nor their order safety while the reach floor still counted them:\n  "
        + "\n  ".join(unparsed)
        + "\n\nFix the file, or exempt it here deliberately with a reason -- but do not let it "
        "fail silently, which is the defect this guard exists to catch."
    )


# ---------------------------------------------------------------------------
# Contrast fixtures. Every one of the three evasions found in review would have
# been caught by a pair here, which is why they exist (#15826: a check that
# cannot fail is the defect). Each case states the shape and the verdict it must
# produce, so a future narrowing of a discriminator fails HERE, loudly, instead
# of quietly shrinking the population in the tree sweep.
# ---------------------------------------------------------------------------

_UNPINNED_LITERAL = """
from transformers import AutoModel
def go():
    return AutoModel.from_pretrained("openai/whisper-base")
"""

_PINNED_LITERAL = """
from transformers import AutoModel
def go():
    return AutoModel.from_pretrained("openai/whisper-base", revision="abc123")
"""

_CALLER_SUPPLIED = """
from transformers import AutoModel
def go(model_name):
    return AutoModel.from_pretrained(model_name)
"""

_MODULE_CONSTANT = """
from transformers import pipeline
MODEL = "openai/whisper-base"
def go():
    return pipeline("automatic-speech-recognition", model=MODEL)
"""

_CONSTANT_IN_A_BLOCK = """
from transformers import pipeline
try:
    MODEL = "openai/whisper-base"
except ImportError:
    MODEL = ""
def go():
    return pipeline("automatic-speech-recognition", model=MODEL)
"""

_FUNCTION_LOCAL_CONSTANT = """
from transformers import AutoModel
def go():
    model = "openai/whisper-base"
    return AutoModel.from_pretrained(model)
"""


def test_an_unpinned_literal_is_found_and_reported_unpinned() -> None:
    loads = _fixed_repo_loads(ast.parse(_UNPINNED_LITERAL))
    assert [pinned for _, pinned in loads] == [False], f"expected one unpinned load, got {loads}"


def test_a_pinned_literal_is_found_and_reported_pinned() -> None:
    """The positive control: the guard must not simply call everything unpinned."""
    loads = _fixed_repo_loads(ast.parse(_PINNED_LITERAL))
    assert [pinned for _, pinned in loads] == [True], f"expected one pinned load, got {loads}"


def test_a_caller_supplied_model_is_exempt_by_the_rule() -> None:
    """Exempt because the id is unknowable without running the program."""
    assert _fixed_repo_loads(ast.parse(_CALLER_SUPPLIED)) == []


def test_a_module_constant_is_not_exempt() -> None:
    """The site #17804 was filed for: the id is one line up, so it is knowable."""
    loads = _fixed_repo_loads(ast.parse(_MODULE_CONSTANT))
    assert [pinned for _, pinned in loads] == [False], f"expected one unpinned load, got {loads}"


def test_a_constant_bound_inside_a_block_is_still_found() -> None:
    """Regression: `scope.body` alone lost the constant AND the load with it.

    `if`/`try`/`with` do not introduce a scope, so this id is exactly as
    statically knowable as a top-level one. Before the fix this returned `[]` --
    a false negative on the primary assertion, not a missed annotation.
    """
    loads = _fixed_repo_loads(ast.parse(_CONSTANT_IN_A_BLOCK))
    assert [pinned for _, pinned in loads] == [
        False
    ], f"a repo id bound inside a try block escaped the sweep entirely: {loads}"


def test_a_function_local_constant_is_found() -> None:
    loads = _fixed_repo_loads(ast.parse(_FUNCTION_LOCAL_CONSTANT))
    assert [pinned for _, pinned in loads] == [False], f"expected one unpinned load, got {loads}"


_HELPER_BY_NAME = """
from autobot_shared.pinned_model_registry import load_verified
def go():
    return load_verified("openai/whisper-base", lambda rev: None)
"""

_HELPER_BY_ATTRIBUTE = """
import autobot_shared.pinned_model_registry as registry
def go():
    return registry.load_verified("openai/whisper-base", lambda rev: None)
"""

_NAMED_INTEGRITY_HANDLER = """
def go():
    try:
        pass
    except ModelIntegrityError:
        raise
"""

_BROAD_EXCEPT_ONLY = """
def go():
    try:
        pass
    except Exception:
        pass
"""


def test_the_helper_is_recognised_called_by_name() -> None:
    assert _module_is_order_safe(ast.parse(_HELPER_BY_NAME)) is True


def test_the_helper_is_recognised_called_through_its_module() -> None:
    """Regression: keying on `node.func.id` scored the canonical path unsafe.

    `registry.load_verified(...)` is an `ast.Attribute` and has no `.id`, so the
    one helper this guard exists to recognise read as absent when called the
    ordinary way.
    """
    assert (
        _module_is_order_safe(ast.parse(_HELPER_BY_ATTRIBUTE)) is True
    ), "an attribute-style call to the helper was not recognised"


def test_a_named_integrity_handler_is_the_other_safe_shape() -> None:
    assert _module_is_order_safe(ast.parse(_NAMED_INTEGRITY_HANDLER)) is True


def test_a_broad_except_alone_is_not_order_safe() -> None:
    """The negative control: #17124's bug was a broad `except` swallowing it."""
    assert _module_is_order_safe(ast.parse(_BROAD_EXCEPT_ONLY)) is False


def test_an_unparseable_file_is_reported_not_skipped(tmp_path: Path) -> None:
    """Regression: `except SyntaxError: return []` made a broken file look clean."""
    broken = tmp_path / "broken.py"
    broken.write_text("def broken(:\n", encoding="utf-8")
    assert _parse(broken) is None, "an unparseable file must be distinguishable from an empty one"

    fine = tmp_path / "fine.py"
    fine.write_text("x = 1\n", encoding="utf-8")
    assert _parse(fine) is not None, "a parseable file must not be reported as unparseable"


# The factory API's four shapes (#17804 AC3, #17819). Every fixture above drives
# `from_pretrained`, or drives `pipeline()` only as `model=MODULE_CONSTANT` -- so
# the factory half of `_model_argument` was reached by exactly one of its paths.
# Untested were the bare literal, the caller-supplied exemption, and the
# positional branch where `index = 1 if is_factory` does its work.
_FACTORY_BARE_LITERAL = """
from transformers import pipeline
def go():
    return pipeline("automatic-speech-recognition", model="openai/whisper-base")
"""

_FACTORY_CALLER_SUPPLIED = """
from transformers import pipeline
def go(name):
    return pipeline("automatic-speech-recognition", model=name)
"""

_FACTORY_POSITIONAL_LITERAL = """
from transformers import pipeline
def go():
    return pipeline("automatic-speech-recognition", "openai/whisper-base")
"""

_FACTORY_POSITIONAL_CALLER_SUPPLIED = """
from transformers import pipeline
def go(name):
    return pipeline("automatic-speech-recognition", name)
"""


def test_a_factory_bare_literal_is_found_unpinned() -> None:
    """`model="repo/id"` with no module constant in sight: the keyword path, literal."""
    loads = _fixed_repo_loads(ast.parse(_FACTORY_BARE_LITERAL))
    assert [pinned for _, pinned in loads] == [False], f"expected one unpinned factory load, got {loads}"


def test_a_factory_caller_supplied_model_is_exempt() -> None:
    """Exempt BY THE RULE on the factory side too, not only for `from_pretrained`."""
    assert _fixed_repo_loads(ast.parse(_FACTORY_CALLER_SUPPLIED)) == []


def test_a_factory_positional_repo_id_is_found_unpinned() -> None:
    """`pipeline(task, "repo/id")` -- the repo id is args[1], not a keyword."""
    loads = _fixed_repo_loads(ast.parse(_FACTORY_POSITIONAL_LITERAL))
    assert [pinned for _, pinned in loads] == [False], f"expected one unpinned factory load, got {loads}"


def test_the_factory_positional_index_reads_the_repo_not_the_task() -> None:
    """What makes `index = 1 if is_factory` load-bearing rather than merely present.

    The test above cannot do it: with `index` mutated to 0, `_model_argument`
    returns the TASK string, which is also a `str` Constant, so the load is still
    recorded unpinned and the assertion still passes. Reading the wrong argument
    and reading the right one are indistinguishable when both are literals.

    Here the task is a literal and the repo id is caller-supplied, so the two
    readings disagree about the VERDICT: at `index = 1` the model is a bare `Name`
    and the load is exempt, while at `index = 0` the task literal is scored as a
    fixed repo id and the guard invents a finding. Empty list or one entry --
    the mutation cannot hide in a shared answer.
    """
    assert _fixed_repo_loads(ast.parse(_FACTORY_POSITIONAL_CALLER_SUPPLIED)) == []
