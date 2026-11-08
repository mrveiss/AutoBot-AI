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

**This ratchet is gated against the merge base (#19673)**, like the file-size
ratchets: every count may not exceed the same count on the merge base's tree.
There is no recorded number to lower, so a PR that cuts a count edits nothing
shared and two such PRs never conflict; the cut is locked in because the next
PR is measured against a base that already has it.

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
from repo_tests._paths import repo_root
from repo_tests._ratchet_base import base_tree_texts

_REPO_ROOT = repo_root()

_MAIN_SRC = _REPO_ROOT / "autobot-frontend" / "src"
_SLM_SRC = _REPO_ROOT / "autobot-slm-frontend" / "src"

# --- The ratchet ---------------------------------------------------------
#
# There is no recorded number (#19673). Each dimension is measured on this tree and on the merge
# base's, and may not exceed the base's: `now <= base`. A PR that cuts a count edits no shared
# table, so two such PRs never conflict, and the lines it cut cannot be spent back because the
# next PR is measured against a base that already has the cut. Never grow a count to make a new
# file pass: extend an existing client, or import the generated contract instead.
#
# Per app, because the two frontends are at different points on the same path and one number
# would hide a regression in whichever app was improving slower. Each app's transport client is
# itself counted in the raw-fetch total (the one file that *should* call fetch), so that count
# floors at 1 rather than 0; the ratchet only asserts direction, so a floor is no problem.
_APPS = ("autobot-frontend", "autobot-slm-frontend")

# Raw `fetch(` sites that legitimately bypass the transport client (#12363),
# keyed by repo-relative path. A new raw fetch must either route through
# `ApiClient` / `fetchWithAuth` or be added here WITH a reason; the guard also
# fails when an entry no longer contains a raw fetch, so the list cannot rot.
_RAW_FETCH_EXCEPTIONS: dict[str, str] = {
    "autobot-frontend/src/utils/fetchWithAuth.ts": "the canonical auth-injecting fetch helper",
    "autobot-frontend/src/utils/slmClient.ts": "SLM-origin transport client with its own bearer token; the main-app JWT must not be sent",
    "autobot-frontend/src/config/AppConfig.js": "bootstrap config fetch; ApiClient derives its base URL from AppConfig, so it cannot depend on it",
    "autobot-frontend/src/config/ssot-config.ts": "SLM service discovery during config bootstrap, before any client exists; imported by the client",
    "autobot-frontend/src/config/ServiceDiscovery.js": "probes candidate hosts for reachability; not a call to the configured backend",
    "autobot-frontend/src/components/desktop/DesktopInterface.vue": "probes the VNC server (a different origin and service) for vnc.html",
    "autobot-frontend/src/embed/AutobotWidget.ts": "embeddable widget on third-party pages; no AutoBot session, auth, or shared client bundle",
    "autobot-frontend/src/utils/RumAgent.ts": "telemetry beacons that must never throw, log-spam, or trigger the 401 logout path",
    "autobot-frontend/src/workers/thumbnailWorker.ts": "Web Worker context; fetches arbitrary media URLs and cannot import the main-thread client",
    "autobot-frontend/src/components/vision/VideoProcessor.vue": "converts a data: URL to a Blob; no network request",
    "autobot-frontend/src/composables/useConnectionTester.ts": "tests a user-supplied endpoint; sending the app token to it would leak the credential",
    "autobot-frontend/src/components/artifact-cells/CodeCell.stories.ts": "false positive: `fetch(` inside a sample-code string in a story",
    "autobot-frontend/src/components/canvas/CodeCell.stories.ts": "false positive: `fetch(` inside a sample-code string in a story",
    "autobot-frontend/src/composables/useTimeout.ts": "false positive: `fetch(` inside a JSDoc example",
}

_APP_SRC = {
    "autobot-frontend": _MAIN_SRC,
    "autobot-slm-frontend": _SLM_SRC,
}

_SOURCE_SUFFIXES = (".ts", ".vue")
# Raw fetch is also checked in `.js` (AppConfig, ServiceDiscovery live there); the
# other dimensions stay `.ts`/`.vue` so their counts are unchanged.
_RAW_FETCH_SUFFIXES = _SOURCE_SUFFIXES + (".js",)

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


def _source_files(root: Path, suffixes: tuple[str, ...] = _SOURCE_SUFFIXES) -> list[Path]:
    return [
        path
        for path in sorted(root.rglob("*"))
        if path.suffix in suffixes
        and path.is_file()
        and "node_modules" not in path.relative_to(root).parts  # #15510
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


def _raw_fetch_files(root: Path, base: Path = _REPO_ROOT) -> list[str]:
    return [
        path.relative_to(base).as_posix()
        for path in _source_files(root, _RAW_FETCH_SUFFIXES)
        if _RAW_FETCH_RE.search(_read(path))
    ]


def _unlisted_raw_fetch_files(root: Path, base: Path = _REPO_ROOT) -> list[str]:
    """Raw-fetch files with no recorded reason: the only ones the ratchet counts."""
    return [rel for rel in _raw_fetch_files(root, base) if rel not in _RAW_FETCH_EXCEPTIONS]


def _axios_importers(root: Path, base: Path = _REPO_ROOT) -> list[str]:
    return [path.relative_to(base).as_posix() for path in _source_files(root) if _AXIOS_IMPORT_RE.search(_read(path))]


def _hand_typed_response_count(root: Path) -> int:
    return sum(len(_RESPONSE_INTERFACE_RE.findall(_read(path))) for path in _source_files(root))


def _inline_generic_count(root: Path) -> int:
    """Unverified response-shape assertions at the call site."""
    return sum(len(_INLINE_GENERIC_RE.findall(_read(path))) for path in _source_files(root))


def _measure(app: str, repo: Path = _REPO_ROOT) -> dict[str, int]:
    """The five counts for *app* in the tree rooted at *repo* (the checkout, or an exported base)."""
    root = repo / app / "src"
    return {
        "clients": len(_client_class_names(root)),
        "raw_fetch": len(_unlisted_raw_fetch_files(root, repo)),
        "axios": len(_axios_importers(root, repo)),
        "responses": _hand_typed_response_count(root),
        "inline_generics": _inline_generic_count(root),
    }


def _export_base(dest: Path, apps: tuple[str, ...] = _APPS, sha: str | None = None) -> Path:
    """Write each app's ``src`` tree as the merge base had it under *dest*; BaseUnavailable propagates."""
    for app in apps:
        for rel, text in base_tree_texts(_REPO_ROOT, f"{app}/src", sha).items():
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
    return dest


@pytest.fixture(scope="module")
def base_counts(tmp_path_factory: pytest.TempPathFactory) -> dict[str, dict[str, int]]:
    """Every app's counts at the merge base, measured by the same functions as the head."""
    dest = _export_base(tmp_path_factory.mktemp("contract_base"))
    return {app: _measure(app, dest) for app in _APPS}


_DIMENSION_ADVICE = {
    "clients": "Extend an existing client rather than adding another that shares no base with the others.",
    "raw_fetch": "Route the call through that app's transport client; a direct fetch builds its own URL, so no config fix reaches it.",
    "axios": "Use the transport client, not axios directly.",
    "responses": "Import the generated contract at `src/types/generated/api.ts` instead of declaring another response shape by hand.",
    "inline_generics": "Type the call from the generated contract rather than asserting a shape inline — `api.get<Shape>` is a claim TypeScript cannot check.",
}


@pytest.mark.parametrize("app", _APPS)
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


@pytest.mark.parametrize("app", _APPS)
@pytest.mark.parametrize("dimension", sorted(_DIMENSION_ADVICE))
def test_contract_sprawl_only_shrinks(app: str, dimension: str, base_counts: dict[str, dict[str, int]]) -> None:
    """Growth against the merge base is a regression; a shrink needs no edit anywhere (#19673).

    `now <= base`, the base being the real merge base (`repo_tests/_ratchet_base.py`). A base
    that cannot be read fails closed rather than reading as "nothing grew".
    """
    actual = _measure(app)[dimension]
    base = base_counts[app][dimension]

    assert actual <= base, (
        f"{app}: {dimension} is {actual}, the merge base has {base} (#12363, #12420, #19673).\n"
        f"{_DIMENSION_ADVICE[dimension]}"
    )


def test_a_grown_count_is_caught_and_a_shrunk_one_passes(tmp_path: Path) -> None:
    """Known-positive control: the comparison fails on growth and not on a shrink."""
    old, new = tmp_path / "old", tmp_path / "new"
    for tree, n in ((old, 2), (new, 3)):
        (tree / "app" / "src").mkdir(parents=True)
        (tree / "app" / "src" / "a.ts").write_text("interface XResponse {}\n" * n, encoding="utf-8")
    counts = lambda tree: _hand_typed_response_count(tree / "app" / "src")  # noqa: E731
    assert (counts(new), counts(old)) == (3, 2)
    assert not counts(new) <= counts(old), "growth must fail"
    assert counts(old) <= counts(new), "a shrink must pass"


def test_every_raw_fetch_exception_is_still_a_raw_fetch_with_a_reason() -> None:
    """A stale or reasonless entry would silently license a future raw fetch."""
    present = set(_raw_fetch_files(_MAIN_SRC))
    for rel, reason in _RAW_FETCH_EXCEPTIONS.items():
        assert reason.strip(), f"{rel}: an exception needs a one-line reason"
        assert rel in present, f"{rel} no longer contains a raw fetch — drop it from _RAW_FETCH_EXCEPTIONS"


def test_the_exception_list_separates_listed_from_unlisted_raw_fetch(tmp_path: Path) -> None:
    """Contrast pair: an unlisted raw fetch is counted; a listed one is not (#12363)."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "rogue.ts").write_text("await fetch('/api/x')\n", encoding="utf-8")
    (src / "blessed.ts").write_text("await fetch('/api/y')\n", encoding="utf-8")
    (src / "clean.ts").write_text("await client.get('/api/z')\n", encoding="utf-8")
    assert _raw_fetch_files(src, tmp_path) == ["src/blessed.ts", "src/rogue.ts"]
    assert _unlisted_raw_fetch_files(src, tmp_path) == ["src/blessed.ts", "src/rogue.ts"]
    _RAW_FETCH_EXCEPTIONS["src/blessed.ts"] = "test fixture"
    try:
        assert _unlisted_raw_fetch_files(src, tmp_path) == ["src/rogue.ts"]
    finally:
        del _RAW_FETCH_EXCEPTIONS["src/blessed.ts"]
