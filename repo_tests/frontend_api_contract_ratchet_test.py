# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The frontend's backend-contract sprawl may shrink, never grow (#12363).

The frontend has no single source of truth for talking to the backend. Eight
HTTP-client classes reimplement request, error, auth and URL handling, **none
of them extending any other**; seventeen files call `fetch` directly; and a
172k-line generated contract is bypassed by 187 hand-written `*Response`
interfaces.

That is the root cause under #12313 (port/CSP), #12317 (`/api` prefix) and
#12326 (dead buttons): when every caller builds its own URL and declares its
own response shape, nothing enforces that a path exists or that a response
matches, so one config error lands in some clients and not others and features
break inconsistently.

Consolidating all of it is a long job spanning many PRs. This guard exists so
the job is finite — it pins today's counts so the sprawl cannot grow while the
consolidation proceeds. It is deliberately not a style rule: it says nothing
about any individual file, only that the totals must move one way.

**This ratchet fails in BOTH directions**, matching
`repo_tests/python_file_size_ratchet_baseline.py`. Growth is a regression.
An unrecorded *shrink* is also a failure, because a baseline that silently
drifts below the real number stops being evidence of anything — the fix is to
lower the constant in the same commit that does the work, so the number stays
a claim someone made on purpose.

Counting is deliberately textual rather than AST- or type-aware. These files
are `.ts` and `.vue`, so a Python guard cannot parse them without pulling in a
TypeScript toolchain that CI would then have to keep working; a regex that is
slightly over-inclusive but *stable* is worth more here than an exact count
that breaks. What matters is the direction of the number, not its absolute
truth.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_FRONTEND_SRC = _REPO_ROOT / "autobot-frontend" / "src"

# --- The ratchet ---------------------------------------------------------
#
# Lower these as consolidation lands. Never raise one to make a new file pass:
# extend an existing client, or import the generated contract instead.

# Distinct HTTP-client classes, none sharing a base (#12363). Test mocks are
# excluded — a mock is not a transport.
MAX_CLIENT_CLASSES = 8

# Files calling `fetch(` directly instead of going through a client.
MAX_RAW_FETCH_FILES = 17

# Direct `axios` importers. Already zero; pinned so it stays that way.
MAX_AXIOS_IMPORTERS = 0

# Hand-written `interface *Response` declarations that bypass the generated
# contract at `src/types/generated/api.ts`.
MAX_HAND_TYPED_RESPONSES = 187

_SOURCE_SUFFIXES = (".ts", ".vue")

_CLIENT_CLASS_RE = re.compile(r"\bclass\s+([A-Za-z]+(?:ApiClient|ApiService|Client))\b")
# No `\s*` before the paren: prose such as "a failed fetch (#14064)" or a test
# name like "share ONE voices fetch (no self-aborting race)" matches with it, and
# three such comments were counted as transport sites on the first pass. A real
# call is always written `fetch(`.
_RAW_FETCH_RE = re.compile(r"(?<![.\w])(?:window\.)?fetch\(")
_AXIOS_IMPORT_RE = re.compile(r"""from\s+['"]axios['"]""")
_RESPONSE_INTERFACE_RE = re.compile(r"^\s*(?:export\s+)?interface\s+\w+Response\b", re.MULTILINE)


def _is_test(path: Path) -> bool:
    """Test scaffolding is not contract surface.

    A spec that stubs `fetch` or declares a fixture response is not a caller
    bypassing the client — counting it would make the ratchet grow whenever
    someone adds coverage, which is the opposite of the incentive intended.
    """
    return "__tests__" in path.parts or ".test." in path.name or ".spec." in path.name


def _source_files() -> list[Path]:
    return [
        path
        for path in sorted(_FRONTEND_SRC.rglob("*"))
        if path.suffix in _SOURCE_SUFFIXES
        and path.is_file()
        and "node_modules" not in path.parts
        and not _is_test(path)
    ]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _client_class_names() -> set[str]:
    """Every HTTP-client class name, excluding test mocks."""
    names: set[str] = set()
    for path in _source_files():
        for name in _CLIENT_CLASS_RE.findall(_read(path)):
            if "Mock" not in name:
                names.add(name)
    return names


def _raw_fetch_files() -> list[str]:
    return [
        path.relative_to(_REPO_ROOT).as_posix()
        for path in _source_files()
        if _RAW_FETCH_RE.search(_read(path))
    ]


def _axios_importers() -> list[str]:
    return [
        path.relative_to(_REPO_ROOT).as_posix()
        for path in _source_files()
        if _AXIOS_IMPORT_RE.search(_read(path))
    ]


def _hand_typed_response_count() -> int:
    return sum(len(_RESPONSE_INTERFACE_RE.findall(_read(path))) for path in _source_files())


def test_the_tree_this_guard_reads_is_present() -> None:
    """A moved frontend would make every count below zero, and zero passes."""
    assert _FRONTEND_SRC.is_dir(), f"{_FRONTEND_SRC} is missing — this guard is pinned to the wrong path"
    assert len(_source_files()) > 500, (
        f"only {len(_source_files())} source file(s) found — the walk has stopped reaching the frontend, "
        "which would make every ratchet below pass by counting nothing"
    )


def test_client_classes_do_not_multiply() -> None:
    """Each new client is another copy of request/error/auth/URL handling."""
    names = sorted(_client_class_names())

    assert len(names) <= MAX_CLIENT_CLASSES, (
        f"{len(names)} HTTP-client classes, ratchet allows {MAX_CLIENT_CLASSES} (#12363):\n"
        f"  {', '.join(names)}\n"
        "Extend an existing client rather than adding another that shares no base with the others."
    )
    assert len(names) == MAX_CLIENT_CLASSES, (
        f"only {len(names)} client classes remain but MAX_CLIENT_CLASSES is still {MAX_CLIENT_CLASSES} — "
        "lower it in the commit that removed one, so the number stays a deliberate claim"
    )


def test_raw_fetch_sites_do_not_multiply() -> None:
    """A direct fetch builds its own URL, so no config fix can reach it."""
    files = _raw_fetch_files()

    assert len(files) <= MAX_RAW_FETCH_FILES, (
        f"{len(files)} files call fetch() directly, ratchet allows {MAX_RAW_FETCH_FILES} (#12363). "
        f"New since the baseline (or newly matching):\n  " + "\n  ".join(files[:20])
    )
    assert len(files) == MAX_RAW_FETCH_FILES, (
        f"only {len(files)} raw-fetch file(s) remain but MAX_RAW_FETCH_FILES is still "
        f"{MAX_RAW_FETCH_FILES} — lower it in the commit that removed one"
    )


def test_no_module_imports_axios_directly() -> None:
    """Already zero. Pinned so a reintroduction is a failure, not a drift."""
    importers = _axios_importers()

    assert len(importers) <= MAX_AXIOS_IMPORTERS, (
        f"{len(importers)} module(s) import axios directly, ratchet allows {MAX_AXIOS_IMPORTERS} "
        f"(#12363):\n  " + "\n  ".join(importers)
    )


def test_hand_typed_responses_do_not_multiply() -> None:
    """Every hand-typed response is a contract nothing checks against the backend."""
    count = _hand_typed_response_count()

    assert count <= MAX_HAND_TYPED_RESPONSES, (
        f"{count} hand-written `interface *Response` declarations, ratchet allows "
        f"{MAX_HAND_TYPED_RESPONSES} (#12363). Import the generated contract at "
        "`src/types/generated/api.ts` instead of declaring another response shape by hand."
    )
    assert count == MAX_HAND_TYPED_RESPONSES, (
        f"only {count} hand-typed response(s) remain but MAX_HAND_TYPED_RESPONSES is still "
        f"{MAX_HAND_TYPED_RESPONSES} — lower it in the commit that removed one"
    )
