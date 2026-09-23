# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""An eighth module must not start deciding what a secret looks like (#16688).

WHAT THIS PINS, AND WHY IT IS NOT A CLONE COUNT
-----------------------------------------------
``jscpd -k 70 -l 8`` over the redaction modules finds **zero** clone lines: they
are *forks*, not copies, and a fork shares no 8-line run with its sibling. The
duplication guard is therefore structurally blind to this whole class of
problem (#17312) — ``MAX_DUP_LINES`` does not move when another redactor lands,
and it does not move when one is removed either.

So this guard counts *implementations of a concept*, not duplicated text. The
concept is *"deciding what a secret or a piece of PII looks like"*, and the
census is the set of modules that own a **detector** for it — a compiled
pattern or a vocabulary of credential nouns that the module itself declares.

CALLING A REDACTOR IS NOT IMPLEMENTING ONE
-------------------------------------------
``autobot-backend/security/chat_message_safety.py`` is 114 lines of redaction
policy on the chat path and is deliberately **not** in the census: it declares
no pattern and no vocabulary, it composes ``pii_pipeline.scrub_outbound`` and
``prompt_injection_detector``. That is the end state this guard exists to
protect — a new caller should look like that one. Counting it would punish the
shape we want.

``llm_shared/credential_redaction.py`` IS in the census, because it still
declares ``API_KEY_PATTERNS`` of its own on top of the shared vocabulary it now
derives ``SENSITIVE_KEYS`` from (#16688). If those patterns are folded into
``secret_redaction`` later, drop it from ``_CENSUS`` and the count falls to 3.

WHAT TO DO WHEN THIS TEST FAILS
--------------------------------
It means a module started declaring its own idea of a secret. Almost always the
fix is to call an existing redactor instead — ``docs/developer/REDACTION_BOUNDARY.md``
says which one owns which shape. Add to ``_CENSUS`` only if the new module owns
a genuinely new *shape* of the problem, and say so in that document in the same
PR. Raising the count to make a red test green is the failure this guard is
written against.

THE TWO-CANONICALS QUESTION IS OPEN
------------------------------------
``autobot_shared/secret_redaction.py`` and ``autobot_shared/security/redaction.py``
both answer "is this field name a credential" and disagree on 7 of 10 sampled
names — suffix matching vs substring matching, each a recorded ruling in its own
file. This guard pins that there are two and does not adjudicate which wins; see
REDACTION_BOUNDARY.md.
"""

from __future__ import annotations

import ast
import subprocess
from typing import List, Set

import pytest
from repo_tests._paths import repo_root

from autobot_shared.paths import scrubbed_git_env

REPO_ROOT = repo_root()

# The census, as of #16688 — MEASURED by running the rule below over all 3,392
# tracked production sources, not transcribed from the issue. #16688 and #17312
# both say "four"; the rule finds SEVEN. The three nobody had counted are
# cot_events, portability and config_revision_service, each carrying its own
# key-name vocabulary. They are pinned here so the count cannot grow, and
# collapsing them is tracked separately (see REDACTION_BOUNDARY.md).
_CENSUS: Set[str] = {
    # Named in #16688
    "autobot_shared/secret_redaction.py",  # CREDENTIAL_SUFFIXES, 19 nouns, suffix match
    "autobot-backend/a2a/pii_pipeline.py",  # PIIType x14 + policy table, regex detectors
    "autobot-backend/llm_shared/credential_redaction.py",  # API_KEY_PATTERNS (SENSITIVE_KEYS now derived)
    # Found while implementing #16688 — also declares itself canonical (#12242)
    "autobot_shared/security/redaction.py",  # _SECRET_KEY_FRAGMENTS, 8 nouns, substring match
    # Found by this guard; not named in any issue before it ran
    "autobot-backend/chat_workflow/cot_events.py",  # _SENSITIVE_KEY_FRAGMENTS, 13 nouns
    "autobot-backend/llc/services/portability.py",  # _SECRET_LIKE_KEYS, 13 nouns
    "autobot-backend/services/config_revision_service.py",  # _SECRET_SUBSTRINGS, 5 nouns
}

# A sweep that reads nothing reports clean over anything (MEASUREMENT_DISCIPLINE).
# Measured at 3,000+ tracked production sources on origin/main; the floor is set
# well below that so ordinary growth never trips it, but an empty or broken
# `git ls-files` does.
_MIN_SOURCE_FILES = 1500

# Verbs that make a module a redactor rather than a module that merely mentions
# one. Matched against top-level def/class names only.
_REDACTION_VERBS = ("redact", "scrub", "sanitiz", "mask")

# Nouns that make a compiled pattern or a literal collection a *secret detector*
# rather than an unrelated regex. Matched inside string literals.
_SECRET_NOUNS = (
    "secret",
    "token",
    "password",
    "passwd",
    "credential",
    "api_key",
    "api-key",
    "apikey",
    "authorization",
    "bearer",
    "private key",
    "private_key",
    "access_key",
    "ssn",
    "credit_card",
    "aws_access",
    "jwt",
    "-----begin",
    "eyj",
)

_SKIP_PREFIXES = (".worktrees/", "docs/", "repo_tests/")


def _tracked_sources() -> List[str]:
    """Repo-relative paths of every tracked, non-test production Python file."""
    completed = subprocess.run(
        ["git", "ls-files", "-z", "*.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
        env=scrubbed_git_env(),
    )
    kept: List[str] = []
    for name in completed.stdout.split("\0"):
        # Relative, never absolute: an absolute prefix does not match inside a
        # worktree, which is where this suite actually runs.
        if not name or name.startswith(_SKIP_PREFIXES):
            continue
        base = name.rsplit("/", 1)[-1]
        # A directory called tests/ may hold non-test helpers, so exclude by
        # file name rather than by directory (#15258).
        if base.startswith("test_") or base.endswith("_test.py") or base == "conftest.py":
            continue
        kept.append(name)
    return kept


def _mentions_secret(text: str) -> bool:
    lowered = text.lower()
    return any(noun in lowered for noun in _SECRET_NOUNS)


def _compiles_secret_pattern(node: ast.AST) -> bool:
    """A ``re.compile(...)`` whose pattern text names a secret.

    The pattern may be built from an f-string or concatenation, so every string
    constant reachable from the call's arguments is considered — not just a
    single literal first argument.
    """
    for call in ast.walk(node):
        if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr == "compile"):
            continue
        for arg in call.args:
            for const in ast.walk(arg):
                if isinstance(const, ast.Constant) and isinstance(const.value, str) and _mentions_secret(const.value):
                    return True
    return False


def _declares_secret_vocabulary(node: ast.AST) -> bool:
    """A collection literal of >=3 strings that are themselves secret nouns.

    The >=3 floor is what separates a vocabulary from an ordinary string. A
    scalar placeholder (``_REDACTED = "<redacted>"``), an event name
    (``CREDENTIAL_REDACTED = "credential_redacted"``) and a Redis key prefix
    (``"chat:tokens:"``) all mention a secret noun without deciding anything,
    and each produced a false positive before this floor existed.
    """
    for coll in ast.walk(node):
        if not isinstance(coll, (ast.Tuple, ast.List, ast.Set)):
            continue
        strings = [e.value for e in coll.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
        if len(strings) >= 3 and sum(1 for s in strings if _mentions_secret(s)) >= 3:
            return True
    return False


def _declares_secret_enum(tree: ast.Module) -> bool:
    """A class whose members are >=3 secret/PII type names.

    ``a2a/pii_pipeline.py`` keeps its vocabulary in ``PIIType`` and builds its
    regexes inside ``_build_detectors()``, so a module-level-assignment-only
    rule misses the single largest implementation in the tree.
    """
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        values = [
            stmt.value.value
            for stmt in node.body
            if isinstance(stmt, ast.Assign)
            and isinstance(stmt.value, ast.Constant)
            and isinstance(stmt.value.value, str)
        ]
        if sum(1 for v in values if _mentions_secret(v)) >= 3:
            return True
    return False


def _declares_own_detector(tree: ast.Module) -> bool:
    """True when the module declares a secret detector of its own.

    A detector is a compiled pattern naming a secret, a vocabulary of secret
    nouns, or an enum of secret/PII types — declared at module level or inside
    a module-level function (the detector-builder shape). Importing someone
    else's detector is not declaring one, which is the whole distinction this
    guard turns on.
    """
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            if node.value is not None and (
                _compiles_secret_pattern(node.value) or _declares_secret_vocabulary(node.value)
            ):
                return True
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if _compiles_secret_pattern(node) or _declares_secret_vocabulary(node):
                return True
    return _declares_secret_enum(tree)


def _defines_redaction_api(tree: ast.Module) -> bool:
    """True when the module exposes a top-level redact/scrub/mask entry point."""
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            lowered = node.name.lower()
            if any(verb in lowered for verb in _REDACTION_VERBS):
                return True
    return False


def is_redaction_implementation(source: str) -> bool:
    """Both decides *and* detects — the property the census counts.

    Pure function of the source text so the planted-fork test below can prove
    the rule fires on a module that shares no text with any real one.

    Raises ``SyntaxError`` rather than returning False on unparseable input.
    Swallowing it here would let a file the census *could not read* be reported
    as a file with *nothing to find* — the exact conflation
    MEASUREMENT_DISCIPLINE forbids. The sweep below catches it per file and
    fails with the path.
    """
    tree = ast.parse(source)
    return _defines_redaction_api(tree) and _declares_own_detector(tree)


_SOURCES = _tracked_sources()


def test_the_sweep_reached_the_tree() -> None:
    """Runs first: an empty file list would pass every assertion below vacuously."""
    assert len(_SOURCES) >= _MIN_SOURCE_FILES, (
        f"only {len(_SOURCES)} tracked production Python files found, floor is "
        f"{_MIN_SOURCE_FILES}. FIX THE SWEEP — a census that reads nothing "
        "reports 'no new implementations' over anything."
    )


def test_every_censused_module_still_exists() -> None:
    """A census entry that has been moved or deleted must fail loudly, not silently shrink."""
    missing = sorted(p for p in _CENSUS if not (REPO_ROOT / p).is_file())
    assert not missing, (
        f"census names {len(missing)} module(s) that no longer exist: {missing}. "
        "If one was consolidated away, remove it from _CENSUS and say so in "
        "docs/developer/REDACTION_BOUNDARY.md — do not leave the census stale."
    )


def test_no_new_redaction_implementation() -> None:
    """The count of modules deciding what a secret looks like may fall, never grow."""
    found: Set[str] = set()
    unreadable: List[str] = []
    for rel in _SOURCES:
        path = REPO_ROOT / rel
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:  # pragma: no cover - defensive
            unreadable.append(f"{rel}: {exc}")
            continue
        try:
            if is_redaction_implementation(source):
                found.add(rel)
        except SyntaxError as exc:  # pragma: no cover - defensive
            unreadable.append(f"{rel}: unparseable ({exc})")

    # A file the census could not read is NOT a file with nothing in it. Failing
    # here is the difference between "no new implementations" and "did not look"
    # (#17312 acceptance criterion 2).
    assert not unreadable, (
        f"census could not examine {len(unreadable)} file(s), so it cannot report " f"clean: {unreadable[:5]}"
    )

    new = sorted(found - _CENSUS)
    assert not new, (
        f"{len(new)} module(s) outside the census now declare their own secret "
        f"detector AND expose a redact/scrub entry point: {new}\n\n"
        "Call an existing redactor instead — docs/developer/REDACTION_BOUNDARY.md "
        "says which one owns which shape of the problem. "
        "autobot-backend/security/chat_message_safety.py is the worked example: "
        "it is redaction policy that declares no detector of its own, so it is "
        "not in the census.\n"
        "Adding the module to _CENSUS is correct ONLY if it owns a genuinely new "
        "shape, and that belongs in REDACTION_BOUNDARY.md in the same PR."
    )


def test_census_is_not_silently_over_counting() -> None:
    """Every censused module must still satisfy the rule that put it there.

    Without this, a module could be consolidated onto another and stay in
    ``_CENSUS`` forever, holding the count up and hiding the win.
    """
    no_longer: List[str] = []
    for rel in sorted(_CENSUS):
        # Deliberately unguarded: a censused module that will not parse is a
        # broken tree, and must fail loudly here rather than be scored.
        source = (REPO_ROOT / rel).read_text(encoding="utf-8")
        if not is_redaction_implementation(source):
            no_longer.append(rel)
    assert not no_longer, (
        f"{no_longer} no longer declare their own detector — the consolidation "
        "landed. Remove them from _CENSUS and update REDACTION_BOUNDARY.md."
    )


# ---------------------------------------------------------------------------
# The rule must fire on a DRIFTED fork, not only on an identical copy (#17312).
# ---------------------------------------------------------------------------

# Shares no 8-line run and no 70-token sequence with any module in the census —
# different names, different nouns, different structure. jscpd reports nothing
# for it; this guard must still catch it.
_PLANTED_DRIFTED_FORK = """
import re

_MY_OWN_PATTERNS = [
    re.compile(r"password\\s*=\\s*(\\S+)"),
    re.compile(r"x-authorization:\\s*(\\S+)"),
]


def sanitize_payload(blob: str) -> str:
    for rx in _MY_OWN_PATTERNS:
        blob = rx.sub("<gone>", blob)
    return blob
"""

# Redaction policy that declares nothing of its own — the shape we want.
_PLANTED_PURE_COMPOSITION = """
from a2a.pii_pipeline import scrub_outbound


def scrub_everything(text: str) -> str:
    return scrub_outbound(text).text
"""

# A detector vocabulary with no redaction entry point — e.g. an audit rule list.
_PLANTED_DETECTOR_ONLY = """
INTERESTING = ("password", "token")


def count_hits(text: str) -> int:
    return sum(text.count(word) for word in INTERESTING)
"""


@pytest.mark.parametrize(
    "label,source,expected",
    [
        ("drifted fork sharing no text with any censused module", _PLANTED_DRIFTED_FORK, True),
        ("pure composition, declares no detector", _PLANTED_PURE_COMPOSITION, False),
        ("detector vocabulary with no redaction API", _PLANTED_DETECTOR_ONLY, False),
    ],
)
def test_rule_fires_on_drift_not_on_similarity(label: str, source: str, expected: bool) -> None:
    assert is_redaction_implementation(source) is expected, label


def test_an_unparseable_file_is_a_failure_not_a_clean_report() -> None:
    """A census that cannot read a file must say so, never score it as empty."""
    with pytest.raises(SyntaxError):
        is_redaction_implementation("def broken(:\n")
