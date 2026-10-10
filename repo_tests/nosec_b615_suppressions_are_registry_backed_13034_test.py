# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every live B615 suppression is enumerated, reasoned, and registry-backed (#13034).

`autobot_shared/pinned_model_registry.py` pins every **fixed** repo id, and
`model_revision_pinning_enforced_17804_test.py` asserts that those call sites
pass `revision=`. Neither looks at the other half of #13034: the bandit
suppressions themselves. Nothing stopped a new `from_pretrained` from landing
with a fresh `# nosec B615` and the same "revision pinning managed
operationally" comment the issue was filed about -- a sentence that described
an intention nothing implemented.

## The discriminator, and why `grep` is the wrong one

#13034's AC1 is literally ``grep -rn "nosec B615"`` returning zero. That text
match is satisfied -- and violated -- by **prose**. This very docstring would
break it, as would `docs/developer/MODEL_REVISION_PINNING.md`, the changelog
fragment, and the module docstring of the registry, all of which must name the
string to explain it. A guard keyed on text would therefore either forbid
documenting the thing it enforces, or be silenced by a comment discussing it.

So the population here is built with :mod:`tokenize`, not with a substring
search over file text: a `# nosec B615` is a **`COMMENT` token**, and every
occurrence in a docstring, an f-string or a test fixture is a `STRING` token.
The distinction is not hypothetical -- three files in this tree carry the
string only inside a string literal today (`pinned_model_registry.py`,
`model_revision_pinning_enforced_17804_test.py`, and this file), and
:func:`test_prose_occurrences_in_the_tree_are_not_counted` names them, so the
contrast is live tree evidence rather than only a synthetic fixture.

## What an entry in `_SUPPRESSED` claims

A suppression is allowed only where the model id is **not knowable without
running the program**, which is the same rule
`model_revision_pinning_enforced_17804_test.py` applies to `revision=`. Each
entry records the count, the reason, and whether the site must still consult
the registry:

* `registry_backed=True` -- the call takes a caller-supplied name, so no static
  pin fits, but it must still call
  :func:`autobot_shared.pinned_model_registry.pinned_revision_kwargs`, and
  each suppressed call must itself pass the result (AST-checked, per call),
  which pins the name whenever it *is* a registered model. The suppression then
  covers only the genuinely unregistered remainder.
* `registry_backed=False` -- the call resolves nothing from the Hub at all, so
  a `revision=` would be a no-op rather than a guarantee. One site qualifies
  (the NPU worker loads a local directory its downloader already verified).

## What this does NOT assert

It does not claim the remaining suppressions are safe. They are the residual
scope `docs/developer/MODEL_REVISION_PINNING.md` states: an unregistered,
caller-supplied repo id still resolves against a mutable default branch. The
guard's job is that the set cannot grow, cannot lose its reasons, and cannot be
quietly widened -- not that it is empty.
"""

from __future__ import annotations

import ast
import tokenize
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pytest
from repo_tests._nosec_b615_scan import MARKER
from repo_tests._nosec_b615_scan import RESOLVER as _RESOLVER
from repo_tests._nosec_b615_scan import calls_resolver as _calls_resolver
from repo_tests._nosec_b615_scan import comment_markers, unpinned_suppressed_calls
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths


@dataclass(frozen=True)
class Suppression:
    """One allowlisted file: how many suppressions, why, and whether it must pin."""

    count: int
    registry_backed: bool
    reason: str


#: Measured on `origin/main` at 0a4cffce: **4** live suppressions in 3 files.
#: The issue text says 16 hits in 10 files and the registry docstring says 18 --
#: both are historical. 11 further occurrences in the tree are prose (docs,
#: changelog, docstrings) and are not suppressions at all.
_SUPPRESSED: dict[str, Suppression] = {
    "autobot-backend/llm_shared/optimization/layer_inference.py": Suppression(
        count=2,
        registry_backed=True,
        reason=(
            "AutoConfig/AutoTokenizer load `model_name`, which reaches this module from a routing "
            "request and may be a local path or a non-HuggingFace tag. No static pin fits; the "
            "registry is consulted so a registered id IS pinned (#13034 remaining scope)."
        ),
    ),
    "autobot-backend/llm_shared/optimization/model_inspector.py": Suppression(
        count=1,
        registry_backed=True,
        reason=(
            "`inspect_model(model_name)` is called by the complexity router and hardware sizing "
            "with whatever model the caller routed to. Same dynamic shape as layer_inference.py."
        ),
    ),
    "autobot-npu-worker/resources/windows-npu-worker/app/model_manager.py": Suppression(
        count=2,
        registry_backed=False,
        reason=(
            "`str(model_path)` is a LOCAL directory ensure_model_downloaded() already populated "
            "and verified against its pin (#17087). No Hub resolution happens, so `revision=` "
            "would be a no-op, not a guarantee. The second occurrence is the explanatory comment "
            "immediately above the call."
        ),
    ),
}


def _python_files(root: Path) -> list[str]:
    """Every tracked `.py` path, repo-relative. Empty tree -> empty list.

    Deliberately wider than bandit's own scan set (`autobot-backend/`,
    `autobot-slm-backend/`, `autobot_shared/`, `autobot-npu-worker/`): a marker
    outside those trees suppresses nothing, so it is a false claim rather than a
    harmless one, and this guard should see it.
    """
    try:
        return tracked_paths(root, "*.py")
    except EmptyEnumeration:
        return []


REACH = declare(
    "nosec-b615-suppression-sweep",
    discover=_python_files,
    # Population IS every tracked `.py` (shape of `conflict-marker-scanned-files`): a fraction,
    # not a floor the tree walks into; 0.99 allows legitimately unreadable files.
    min_fraction=0.99,
    reference=lambda root: len(_python_files(root)),
    what="tracked Python files searched for a live B615 suppression comment",
)


def _parse(path: Path) -> ast.Module | None:
    """The parsed module, or ``None`` when it could not be read as Python.

    ``None`` is not ``[]``: a file that will not parse was *not examined*, and
    :func:`test_every_tracked_python_file_parses` turns that into a named
    failure instead of a silent contribution of zero findings.
    """
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError, ValueError, OSError):
        return None


@lru_cache(maxsize=1)
def _sweep() -> tuple[dict[str, int], dict[str, list[int]], tuple[str, ...]]:
    """`(suppressions, unpinned_calls, unreadable)` over every tracked `.py`.

    Cached: four assertions consume this and each would otherwise tokenize and
    parse the whole tree again.
    """
    root = repo_root()
    suppressions: dict[str, int] = {}
    unpinned: dict[str, list[int]] = {}
    unreadable: list[str] = []
    for rel in _python_files(root):
        path = root / rel
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            unreadable.append(rel)
            continue
        try:
            markers = comment_markers(source)
        except (tokenize.TokenError, IndentationError, SyntaxError):
            unreadable.append(rel)
            continue
        if markers:
            suppressions[rel] = len(markers)
        module = _parse(path)
        if module is None:
            unreadable.append(rel)
            continue
        if markers:
            lines = unpinned_suppressed_calls(source)
            if lines:
                unpinned[rel] = lines
    return suppressions, unpinned, tuple(sorted(unreadable))


def test_no_unrecorded_suppression_exists() -> None:
    """A new `# nosec` for B615 must be argued for here, not landed quietly."""
    suppressions, _, _ = _sweep()
    unrecorded = sorted(set(suppressions) - set(_SUPPRESSED))
    assert not unrecorded, (
        f"these files suppress bandit {MARKER.split()[1]} without an entry in _SUPPRESSED:\n  "
        + "\n  ".join(f"{rel} ({suppressions[rel]} occurrence(s))" for rel in unrecorded)
        + "\n\nEach suppression is a model loaded at whatever the hub serves that day. Pin it via "
        "autobot_shared/pinned_model_registry.py (docs/developer/MODEL_REVISION_PINNING.md has the "
        "bump procedure), or record here WHY no static pin fits."
    )


def test_every_recorded_suppression_still_exists() -> None:
    """The allowlist only shrinks by someone deleting a suppression, not by drift.

    A stale entry is not cosmetic: it is a reason kept alive for a call site
    that no longer exists, which makes the list read as larger and more
    considered than the tree it describes.
    """
    suppressions, _, _ = _sweep()
    stale = sorted(rel for rel in _SUPPRESSED if rel not in suppressions)
    assert (
        not stale
    ), "these _SUPPRESSED entries no longer match any suppression in the tree -- delete them:\n  " + "\n  ".join(stale)
    miscounted = sorted(
        f"{rel}: recorded {_SUPPRESSED[rel].count}, found {suppressions[rel]}"
        for rel in _SUPPRESSED
        if rel in suppressions and suppressions[rel] != _SUPPRESSED[rel].count
    )
    assert not miscounted, (
        "the number of suppressions in an already-allowlisted file changed:\n  "
        + "\n  ".join(miscounted)
        + "\n\nA file on this list is not a licence to add more; update the count only with a reason."
    )


def test_every_dynamic_suppression_consults_the_registry() -> None:
    """`registry_backed=True` is a claim about the code, checked against the code.

    Without this, "no static pin fits" degrades into the exact sentence #13034
    was filed about -- an assertion of operational pinning with nothing behind
    it. A dynamic site may not be statically pinnable, but it can still pin the
    names the registry DOES know, and that is enforced here rather than trusted.
    """
    _, unpinned, _ = _sweep()
    missing = sorted(
        f"{rel}: line(s) {unpinned[rel]}"
        for rel, entry in _SUPPRESSED.items()
        if entry.registry_backed and rel in unpinned
    )
    assert not missing, (
        f"these registry-backed suppressed from_pretrained calls do not pass a {_RESOLVER}() pin "
        "(revision= or **<name> bound from the resolver in the same function):\n  "
        + "\n  ".join(missing)
        + f"\n\nEither pass the {_RESOLVER}() result into the call itself, or change the entry to "
        "registry_backed=False and say why nothing can be resolved."
    )


def test_every_recorded_entry_states_a_reason() -> None:
    """A reasonless entry is an allowlist row, which is what the issue is about."""
    thin = sorted(rel for rel, entry in _SUPPRESSED.items() if len(entry.reason.split()) < 12)
    assert not thin, "these _SUPPRESSED entries carry no real reason:\n  " + "\n  ".join(thin)


def test_prose_occurrences_in_the_tree_are_not_counted() -> None:
    """Live tree contrast: files naming the marker only inside a string literal.

    The trap this guard exists to avoid, measured against the tree rather than
    only against a fixture. Each file below contains the marker text and must
    contribute **zero** suppressions; if the tokenizer discriminator is ever
    replaced by a substring search, this fails before the allowlist does.
    """
    root = repo_root()
    prose_only = [
        "autobot_shared/pinned_model_registry.py",
        "repo_tests/model_revision_pinning_enforced_17804_test.py",
        "repo_tests/nosec_b615_suppressions_are_registry_backed_13034_test.py",
    ]
    for rel in prose_only:
        source = (root / rel).read_text(encoding="utf-8")
        assert MARKER in source, f"{rel} no longer mentions the marker; pick another prose witness"
        assert comment_markers(source) == [], (
            f"{rel} mentions the marker only in prose, yet the sweep counted it as a suppression -- "
            "the discriminator has degraded to a text match (#13034 AC1's literal grep has exactly "
            "this defect)."
        )


def test_every_tracked_python_file_parses() -> None:
    """A file that cannot be tokenized is not a file with no suppressions in it."""
    _, _, unreadable = _sweep()
    assert not unreadable, (
        f"{len(unreadable)} tracked Python file(s) could not be read, tokenized or parsed, so this "
        "guard examined none of them while the reach floor still counted them:\n  " + "\n  ".join(unreadable)
    )


# ---------------------------------------------------------------------------
# Contrast fixtures. Each states a shape and the verdict it must produce, so a
# narrowing of the discriminator fails HERE rather than quietly shrinking the
# population swept over the tree (#15826: a check that cannot fail is the
# defect). Every fixture holds the marker inside a STRING, which is itself the
# property under test.
# ---------------------------------------------------------------------------

_TRAILING_COMMENT = """
from transformers import AutoModel
def go(name):
    return AutoModel.from_pretrained(name)  # nosec B615
"""

_DOCSTRING_ONLY = """
\"\"\"This module explains why a # nosec B615 suppression was removed.\"\"\"
def go():
    return 1
"""

_FSTRING_ONLY = """
def describe(n):
    return f"{n} remaining # nosec B615 suppressions"
"""

_ERROR_MESSAGE_ONLY = """
def go():
    raise RuntimeError("do not add a # nosec B615 here")
"""

_STANDALONE_COMMENT = """
# nosec B615 -- explaining the call below
x = 1
"""

_NO_MARKER = """
from transformers import AutoModel
def go():
    return AutoModel.from_pretrained("openai/whisper-base", revision="abc1234")
"""


def test_a_trailing_suppression_comment_is_counted() -> None:
    """The positive control: the guard must actually find a real suppression."""
    assert comment_markers(_TRAILING_COMMENT) == [4], "a real trailing suppression was not found"


def test_a_docstring_mentioning_the_marker_is_not_counted() -> None:
    """The trap, as a fixture: prose carrying the string is not a suppression."""
    assert comment_markers(_DOCSTRING_ONLY) == []


def test_an_fstring_mentioning_the_marker_is_not_counted() -> None:
    """An f-string tokenizes differently on 3.12+ (FSTRING_MIDDLE), still not a comment."""
    assert comment_markers(_FSTRING_ONLY) == []


def test_an_error_message_mentioning_the_marker_is_not_counted() -> None:
    assert comment_markers(_ERROR_MESSAGE_ONLY) == []


def test_a_standalone_explanatory_comment_is_counted() -> None:
    """Counted deliberately: it is a COMMENT, and the allowlist counts it.

    `model_manager.py` has exactly this shape -- an explanation on its own line
    above the call -- which is why its recorded count is 2 for one load. Scoring
    it zero would make the recorded count unverifiable against the file.
    """
    assert comment_markers(_STANDALONE_COMMENT) == [2]


def test_a_pinned_load_with_no_marker_is_not_counted() -> None:
    """The negative control: the guard must not report a marker that is absent."""
    assert comment_markers(_NO_MARKER) == []


def test_the_resolver_is_recognised_called_by_name_and_by_attribute() -> None:
    """Regression guard on `_calls_resolver`: keying on `.id` alone misses `mod.f()`.

    `model_revision_pinning_enforced_17804_test.py` records this exact defect --
    its helper check scored `registry.load_verified(...)` as absent because an
    `ast.Attribute` has no `.id`. The same shape, so the same pair here.
    """
    by_name = f"from autobot_shared.pinned_model_registry import {_RESOLVER}\nk = {_RESOLVER}('a')\n"
    by_attribute = f"import autobot_shared.pinned_model_registry as r\nk = r.{_RESOLVER}('a')\n"
    absent = "k = {}\n"
    assert _calls_resolver(ast.parse(by_name)) is True
    assert _calls_resolver(ast.parse(by_attribute)) is True, "an attribute-style resolver call was not recognised"
    assert _calls_resolver(ast.parse(absent)) is False


_RESOLVER_BUT_PIN_DROPPED = """
from autobot_shared.pinned_model_registry import pinned_revision_kwargs
from transformers import AutoConfig
def go(name):
    pin = pinned_revision_kwargs(name)
    return AutoConfig.from_pretrained(name)  # nosec B615
"""

_RESOLVER_PIN_PASSED = """
from autobot_shared.pinned_model_registry import pinned_revision_kwargs
from transformers import AutoConfig
def go(name):
    pin = pinned_revision_kwargs(name)
    return AutoConfig.from_pretrained(name, **pin)  # nosec B615
"""

_PIN_FROM_OTHER_FUNCTION = """
from autobot_shared.pinned_model_registry import pinned_revision_kwargs
from transformers import AutoConfig
def a(name):
    pin = pinned_revision_kwargs(name)
    return pin
def b(name, pin):
    return AutoConfig.from_pretrained(name, **pin)  # nosec B615
"""

_PIN_IN_DICT_LITERAL = """
from autobot_shared.pinned_model_registry import pinned_revision_kwargs
from transformers import AutoTokenizer
def go(name):
    kwargs = {"use_fast": True, **pinned_revision_kwargs(name)}
    return AutoTokenizer.from_pretrained(name, **kwargs)  # nosec B615
"""


def test_a_resolver_call_whose_pin_is_dropped_from_the_load_fails() -> None:
    """Contrast pair, failing half: the file calls the resolver, the load ignores it."""
    assert unpinned_suppressed_calls(_RESOLVER_BUT_PIN_DROPPED) == [6]


def test_a_load_passing_the_resolver_pin_passes() -> None:
    """Contrast pair, passing half: `**pin` bound from the resolver in the same function."""
    assert unpinned_suppressed_calls(_RESOLVER_PIN_PASSED) == []
    assert unpinned_suppressed_calls(_PIN_IN_DICT_LITERAL) == []


def test_a_pin_bound_in_a_different_function_does_not_count() -> None:
    """The name must be resolver-bound in the call's own function, not elsewhere in the file."""
    assert unpinned_suppressed_calls(_PIN_FROM_OTHER_FUNCTION) == [8]


_INLINE_RESOLVER = """
from autobot_shared.pinned_model_registry import pinned_revision_kwargs
from transformers import AutoConfig
def go(name):
    return AutoConfig.from_pretrained(name, **pinned_revision_kwargs(name))  # nosec B615
"""

_EXPLICIT_REVISION = """
from transformers import AutoConfig
def go(name):
    return AutoConfig.from_pretrained(name, revision="abc1234")  # nosec B615
"""

_BARE_PARAM_KWARGS = """
from transformers import AutoConfig
def go(name, kwargs):
    return AutoConfig.from_pretrained(name, **kwargs)  # nosec B615
"""

_EMPTY_DICT_KWARGS = """
from transformers import AutoConfig
def go(name):
    kwargs = {}
    return AutoConfig.from_pretrained(name, **kwargs)  # nosec B615
"""

_REVISION_NONE = """
from transformers import AutoConfig
def go(name):
    return AutoConfig.from_pretrained(name, revision=None)  # nosec B615
"""


def test_an_inline_resolver_call_in_the_load_passes() -> None:
    """Exercises the `supplies_pin(kw.value)` branch directly."""
    assert unpinned_suppressed_calls(_INLINE_RESOLVER) == []


def test_an_explicit_revision_passes() -> None:
    assert unpinned_suppressed_calls(_EXPLICIT_REVISION) == []


def test_a_bare_kwargs_parameter_fails() -> None:
    """`**kwargs` that is a function parameter is not resolver-bound."""
    assert unpinned_suppressed_calls(_BARE_PARAM_KWARGS) == [4]


def test_an_empty_dict_kwargs_fails() -> None:
    assert unpinned_suppressed_calls(_EMPTY_DICT_KWARGS) == [5]


def test_revision_none_fails() -> None:
    """`revision=None` is the default branch spelled out, not a pin."""
    assert unpinned_suppressed_calls(_REVISION_NONE) == [4]


_PIN_HEADER = (
    "from autobot_shared.pinned_model_registry import pinned_revision_kwargs\n"
    "from transformers import AutoConfig\n"
    "def go(m, c, e, items):\n"
)
_LOAD = "    return AutoConfig.from_pretrained(m, **kwargs)  # nosec B615\n"
_PIN = "    kwargs = pinned_revision_kwargs(m)\n"

#: (label, body lines before the load, unpinned?) -- any second binding of the
#: splatted name, in any form, unpins it; a binding in a nested def never counts.
_BINDING_CASES = [
    ("single binding", _PIN, False),
    ("another constant key set", _PIN + "    kwargs['cache_dir'] = c\n", False),
    ("dict splatting the resolver", "    kwargs = {'use_fast': True, **pinned_revision_kwargs(m)}\n", False),
    ("resolver nested as a value", "    kwargs = {'metadata': pinned_revision_kwargs(m)}\n", True),
    ("resolver in one arm only", "    kwargs = pinned_revision_kwargs(m) if c else {}\n", True),
    ("revision key popped by name", _PIN + "    kwargs.pop('revision', None)\n", True),
    ("key from a variable", _PIN + "    kwargs[c] = None\n", True),
    ("nested-def binding", "    kwargs = {}\n    def h():\n        kwargs = pinned_revision_kwargs(m)\n", True),
    ("conditional second binding", "    kwargs = {}\n    if c:\n        kwargs = pinned_revision_kwargs(m)\n", True),
    ("rebound to empty", _PIN + "    kwargs = {}\n", True),
    ("tuple unpack", _PIN + "    kwargs, x = {}, 1\n", True),
    ("augmented assignment", _PIN + "    kwargs |= {'revision': None}\n", True),
    ("item assignment", _PIN + "    kwargs['revision'] = None\n", True),
    ("del", _PIN + "    del kwargs\n    kwargs = {}\n", True),
    ("except-as", _PIN + "    try:\n        pass\n    except e as kwargs:\n        pass\n", True),
    ("for target", _PIN + "    for kwargs in items:\n        pass\n", True),
    ("with-as", _PIN + "    with e as kwargs:\n        pass\n", True),
    ("same-line rebind", "    kwargs = pinned_revision_kwargs(m); kwargs = {}\n", True),
    ("binding after the load", _PIN + _LOAD + "    kwargs = {}\n", True),
]


@pytest.mark.parametrize(("label", "body", "unpinned"), _BINDING_CASES, ids=[c[0] for c in _BINDING_CASES])
def test_a_splatted_pin_counts_only_with_exactly_one_binding(label: str, body: str, unpinned: bool) -> None:
    """Exactly one binding, from the resolver, before the load -- position cannot follow control flow."""
    source = _PIN_HEADER + body + ("" if _LOAD in body else _LOAD)
    load_line = source.splitlines().index(_LOAD.rstrip("\n")) + 1
    assert unpinned_suppressed_calls(source) == ([load_line] if unpinned else []), label
