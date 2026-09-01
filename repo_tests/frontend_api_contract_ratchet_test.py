# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Backend-contract sprawl in BOTH frontends may shrink, never grow (#12363, #12420, #14062).

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

The SLM frontend (#12420) had the same problem in a worse form — no client
abstraction and no type generation at all. Steps 1 and 2 of that issue have
since landed: `gen:types` is wired and `src/types/generated/api.ts` carries 305
paths against a 306-endpoint backend, and `SlmApiClient` has 39 importers. What
remains there is what remains here — hand-typed responses bypassing the
generated contract, which have grown in both apps (74 -> 78 files in the main
frontend, 23 -> 31 declarations in SLM) while the structural work was going on.

This guard is step 4 of #12420's plan, applied to both frontends at once: forbid
new raw transport and new hand-typed responses. Consolidating the rest is a long
job spanning many PRs, and this exists so the job is finite. It is deliberately
not a style rule: it says nothing about any individual file, only that the
totals must move one way.

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

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent

_MAIN_SRC = _REPO_ROOT / "autobot-frontend" / "src"
_SLM_SRC = _REPO_ROOT / "autobot-slm-frontend" / "src"

# --- The ratchet ---------------------------------------------------------
#
# Lower these as consolidation lands. Never raise one to make a new file pass:
# extend an existing client, or import the generated contract instead.

# Per app, because the two frontends are at different points on the same path
# and one number would hide a regression in whichever app was improving slower.
#
# Each app's transport client is itself counted in the raw-fetch total — it is
# the one file that *should* call fetch, so that count floors at 1 rather than
# 0. The ratchet only asserts direction, so a floor is not a problem.
_BASELINES = {
    "autobot-frontend": {
        "clients": 8,
        "raw_fetch": 17,
        "axios": 0,
        "responses": 187,
        # #15454: raised for the four typed detail fetches #15429 added. Same
        # limitation — this counts assertions, and a correct new call is one.
        "inline_generics": 577,
    },
    "autobot-slm-frontend": {
        "clients": 1,
        "raw_fetch": 3,
        # One holdout: `composables/useAutobotApi.ts` — a composable, not the
        # transport client, so this one is a real bypass and should reach 0.
        # The main frontend is already there.
        "axios": 1,
        "responses": 31,
        "inline_generics": 87,
    },
}

_APP_SRC = {
    "autobot-frontend": _MAIN_SRC,
    "autobot-slm-frontend": _SLM_SRC,
}

_SOURCE_SUFFIXES = (".ts", ".vue")

# Floors, not censuses: a walk that stops matching must fail loudly rather than
# pass by reaching nothing.
_MIN_SOURCE_FILES = {"autobot-frontend": 500, "autobot-slm-frontend": 100}

_CLIENT_CLASS_RE = re.compile(r"\bclass\s+([A-Za-z]+(?:ApiClient|ApiService|Client))\b")
# No `\s*` before the paren: prose such as "a failed fetch (#14064)" or a test
# name like "share ONE voices fetch (no self-aborting race)" matches with it, and
# three such comments were counted as transport sites on the first pass. A real
# call is always written `fetch(`.
_RAW_FETCH_RE = re.compile(r"(?<![.\w])(?:window\.)?fetch\(")
_AXIOS_IMPORT_RE = re.compile(r"""from\s+['"]axios['"]""")
_RESPONSE_INTERFACE_RE = re.compile(r"^\s*(?:export\s+)?interface\s+\w+Response\b", re.MULTILINE)

# `api.get<Shape>(...)` is an assertion, not a check — TypeScript takes the
# caller's word for what the endpoint returns. #14062 is the case in point: a
# view and its test fixture shared the same wrong shape for
# `/api/llc/boards/{board_id}/items`, so the two layers that should have
# disagreed agreed, three tests passed, and every board rendered zero rows
# (#13993). Counted separately from hand-typed interfaces because the fix is
# different: these become checked by importing the generated contract, which
# for LLC already exists and simply is not imported.
_INLINE_GENERIC_RE = re.compile(r"\b\w*[aA]pi\w*\.(?:get|post|put|patch|delete)\s*<")


def _is_test(path: Path) -> bool:
    """Test scaffolding is not contract surface.

    A spec that stubs `fetch` or declares a fixture response is not a caller
    bypassing the client — counting it would make the ratchet grow whenever
    someone adds coverage, which is the opposite of the incentive intended.
    """
    return "__tests__" in path.parts or ".test." in path.name or ".spec." in path.name


def _source_files(root: Path) -> list[Path]:
    return [
        path
        for path in sorted(root.rglob("*"))
        if path.suffix in _SOURCE_SUFFIXES
        and path.is_file()
        and "node_modules" not in path.parts
        and "generated" not in path.parts
        and not _is_test(path)
    ]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _client_class_names(root: Path) -> set[str]:
    """Every HTTP-client class name, excluding test mocks."""
    names: set[str] = set()
    for path in _source_files(root):
        for name in _CLIENT_CLASS_RE.findall(_read(path)):
            if "Mock" not in name:
                names.add(name)
    return names


def _raw_fetch_files(root: Path) -> list[str]:
    return [
        path.relative_to(_REPO_ROOT).as_posix()
        for path in _source_files(root)
        if _RAW_FETCH_RE.search(_read(path))
    ]


def _axios_importers(root: Path) -> list[str]:
    return [
        path.relative_to(_REPO_ROOT).as_posix()
        for path in _source_files(root)
        if _AXIOS_IMPORT_RE.search(_read(path))
    ]


def _hand_typed_response_count(root: Path) -> int:
    return sum(len(_RESPONSE_INTERFACE_RE.findall(_read(path))) for path in _source_files(root))


def _inline_generic_count(root: Path) -> int:
    """Unverified response-shape assertions at the call site."""
    return sum(len(_INLINE_GENERIC_RE.findall(_read(path))) for path in _source_files(root))


def _measure(app: str) -> dict[str, int]:
    root = _APP_SRC[app]
    return {
        "clients": len(_client_class_names(root)),
        "raw_fetch": len(_raw_fetch_files(root)),
        "axios": len(_axios_importers(root)),
        "responses": _hand_typed_response_count(root),
        "inline_generics": _inline_generic_count(root),
    }


_DIMENSION_ADVICE = {
    "clients": "Extend an existing client rather than adding another that shares no base with the others.",
    "raw_fetch": "Route the call through that app's transport client; a direct fetch builds its own URL, so no config fix reaches it.",
    "axios": "Use the transport client, not axios directly.",
    "responses": "Import the generated contract at `src/types/generated/api.ts` instead of declaring another response shape by hand.",
    "inline_generics": "Type the call from the generated contract rather than asserting a shape inline — `api.get<Shape>` is a claim TypeScript cannot check.",
}


@pytest.mark.parametrize("app", sorted(_BASELINES))
def test_the_tree_this_guard_reads_is_present(app: str) -> None:
    """A moved or renamed frontend would make every count zero, and zero passes."""
    root = _APP_SRC[app]
    assert root.is_dir(), f"{root} is missing — this guard is pinned to the wrong path"

    found = len(_source_files(root))
    assert found >= _MIN_SOURCE_FILES[app], (
        f"{app}: only {found} source file(s) found, expected at least "
        f"{_MIN_SOURCE_FILES[app]} — the walk has stopped reaching this app, which would "
        "make every ratchet below pass by counting nothing"
    )


@pytest.mark.parametrize("app", sorted(_BASELINES))
@pytest.mark.parametrize("dimension", sorted(_DIMENSION_ADVICE))
def test_contract_sprawl_only_shrinks(app: str, dimension: str) -> None:
    """Growth is a regression; an unrecorded shrink is a stale baseline.

    Both directions fail, matching `python_file_size_ratchet_baseline.py`. A
    baseline that silently drifts below the real number stops being evidence of
    anything, so the constant must be lowered in the same commit that does the
    work — that keeps it a claim someone made on purpose.
    """
    actual = _measure(app)[dimension]
    baseline = _BASELINES[app][dimension]

    assert actual <= baseline, (
        f"{app}: {dimension} is {actual}, ratchet allows {baseline} (#12363, #12420).\n"
        f"{_DIMENSION_ADVICE[dimension]}"
    )
    assert actual == baseline, (
        f"{app}: {dimension} is down to {actual} but the baseline still says {baseline} — "
        "lower it in the commit that did the work, so the number stays a deliberate claim"
    )
