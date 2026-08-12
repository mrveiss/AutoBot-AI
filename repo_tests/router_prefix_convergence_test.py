# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""One router-prefix grammar, shared by both tools that parse it (#12985).

Two modules derive served API paths from source rather than a running app:

* ``scripts/audit_api_wiring.py`` — the **blocking** ``api-wiring`` CI gate
* ``autobot-backend/api/codebase_analytics/api_endpoint_scanner.py``

They had separate regexes for the same grammar and had already diverged. The
scanner received two rounds of package-resolution fixes (#12945, #12956); the
audit received neither, so a registry entry naming a *package* —
``("llc.api", "", …)`` — resolved to a non-existent ``llc/api.py`` and
contributed no prefix at all.

That is worse in the gate than in the scanner: a required check that
under-resolves prefixes either emits false reds that get worked around, eroding
trust in it, or masks real contract drift. It emitted 27 of the former — every
``/api/llc/*`` and ``/api/autoresearch/*`` call a frontend made.

These tests pin the grammar itself and the package resolution, so the two cannot
drift apart again by one being fixed alone.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from autobot_shared.api_routing import router_prefixes as routing

_REPO = Path(__file__).resolve().parents[1]
_BACKEND = _REPO / "autobot-backend"


# --- the grammar ------------------------------------------------------------


def test_apirouter_prefix_is_captured():
    assert routing.file_router_prefix('router = APIRouter(prefix="/llc", tags=["llc"])') == "/llc"


def test_a_trailing_slash_is_normalised_away():
    """Prefixes are concatenated, so `/x/` + `/y` would yield `/x//y`."""
    assert routing.file_router_prefix('APIRouter(prefix="/llc/")') == "/llc"


def test_a_file_without_a_router_prefix_yields_empty():
    assert routing.file_router_prefix("x = 1") == ""


def test_include_router_captures_name_and_prefix():
    found = routing.INCLUDE_ROUTER_RE.findall('app.include_router(chat_router, prefix="/chat")')
    assert found == [("chat_router", "/chat")]


def test_a_registry_tuple_naming_a_package_is_parsed():
    """The shape the audit could not resolve."""
    m = routing.ROUTER_CONFIG_ENTRY_RE.search('    ("llc.api", "", ["llc"], "llc"),')
    assert m is not None
    assert m.group("mod") == "llc.api"
    assert m.group("prefix") == ""


def test_a_registry_tuple_naming_a_variable_is_parsed():
    m = routing.ROUTER_CONFIG_ENTRY_RE.search('    (overseer_router, "/overseer", ["overseer"], "overseer"),')
    assert m is not None
    assert m.group("var") == "overseer_router"
    assert m.group("prefix") == "/overseer"


# --- package resolution, against a synthetic tree ---------------------------


def _make_package(root: Path, *, mounted: bool = True, nested: bool = False) -> Path:
    pkg = root / "llc" / "api"
    pkg.mkdir(parents=True)
    init = ['router = APIRouter(prefix="/llc")', "from .boards import router as boards_router"]
    if mounted:
        init.append("router.include_router(boards_router)")
    (pkg / "boards.py").write_text('router = APIRouter(prefix="/boards")', encoding="utf-8")

    if nested:
        sub = pkg / "admin"
        sub.mkdir()
        (sub / "__init__.py").write_text(
            'router = APIRouter(prefix="/admin")\n'
            "from .users import router as users_router\n"
            "router.include_router(users_router)\n",
            encoding="utf-8",
        )
        (sub / "users.py").write_text('router = APIRouter(prefix="/users")', encoding="utf-8")
        init.append("from .admin import router as admin_router")
        init.append("router.include_router(admin_router)")

    (pkg / "__init__.py").write_text("\n".join(init) + "\n", encoding="utf-8")
    return pkg


def test_a_package_entry_resolves_to_its_submodules(tmp_path):
    """The #12945 fix: the package's own prefix sits between registry and submodule."""
    _make_package(tmp_path)

    resolved = routing.resolve_registry_targets(tmp_path, [("llc.api", "")])

    assert resolved == {tmp_path / "llc" / "api" / "boards.py": "/llc"}


def test_a_package_mounting_nothing_contributes_nothing(tmp_path):
    """No `include_router` at all: the package serves none of what it imports."""
    _make_package(tmp_path, mounted=False)

    assert routing.resolve_registry_targets(tmp_path, [("llc.api", "")]) == {}


def test_a_declared_but_unmounted_submodule_contributes_nothing(tmp_path):
    """#12956: declaring a router is not serving it.

    This is the case the earlier check missed. It only confirmed the package
    mounted *something*, then included every router-declaring module — so a
    sibling that was imported and never mounted still produced routes.

    The fixture therefore mounts one router and leaves a second merely imported;
    a package that mounts nothing is a different (and already-guarded) case.
    """
    pkg = tmp_path / "llc" / "api"
    pkg.mkdir(parents=True)
    (pkg / "boards.py").write_text('router = APIRouter(prefix="/boards")', encoding="utf-8")
    (pkg / "draft.py").write_text('router = APIRouter(prefix="/draft")', encoding="utf-8")
    (pkg / "__init__.py").write_text(
        'router = APIRouter(prefix="/llc")\n'
        "from .boards import router as boards_router\n"
        "from .draft import router as draft_router\n"
        "router.include_router(boards_router)\n",  # draft_router deliberately not mounted
        encoding="utf-8",
    )

    resolved = routing.resolve_registry_targets(tmp_path, [("llc.api", "")])

    assert pkg / "boards.py" in resolved
    assert pkg / "draft.py" not in resolved, "an imported-but-unmounted router contributed routes — it serves nothing"


def test_a_nested_subpackage_resolves_under_its_own_prefix(tmp_path):
    """#12956: globbing gave nested modules the PARENT's prefix, inventing endpoints."""
    _make_package(tmp_path, nested=True)

    resolved = routing.resolve_registry_targets(tmp_path, [("llc.api", "")])

    assert resolved[tmp_path / "llc" / "api" / "admin" / "users.py"] == "/llc/admin"
    assert resolved[tmp_path / "llc" / "api" / "boards.py"] == "/llc"


def test_a_module_entry_still_resolves_to_one_file(tmp_path):
    (tmp_path / "routers").mkdir()
    (tmp_path / "routers" / "code_completion.py").write_text("router = APIRouter()", encoding="utf-8")

    resolved = routing.resolve_registry_targets(tmp_path, [("routers.code_completion", "/code-completion")])

    assert resolved == {tmp_path / "routers" / "code_completion.py": "/code-completion"}


def test_a_registry_entry_naming_nothing_is_skipped(tmp_path):
    assert routing.resolve_registry_targets(tmp_path, [("does.not.exist", "/x")]) == {}


def test_a_backend_without_a_registry_yields_no_entries(tmp_path):
    """autobot-slm-backend has no router_registry — a normal case, not an error."""
    assert routing.registry_entries(tmp_path / "initialization" / "router_registry") == []


# --- against the real tree --------------------------------------------------


@pytest.mark.skipif(not (_BACKEND / "llc" / "api" / "__init__.py").is_file(), reason="llc.api package absent")
def test_the_real_llc_package_resolves_under_slash_llc():
    """The acceptance criterion: `("llc.api", "", …)` must reach `/api/llc/...`.

    `/api` is prepended by app_factory; this resolver owns everything after it.
    """
    entries = routing.registry_entries(_BACKEND / "initialization" / "router_registry")
    resolved = routing.resolve_registry_targets(_BACKEND, entries)

    llc = {p: prefix for p, prefix in resolved.items() if "/llc/api/" in str(p)}

    assert llc, "the llc.api package entry resolved to no files at all — the #12985 defect"
    assert set(llc.values()) == {"/llc"}, f"unexpected prefixes: {sorted(set(llc.values()))}"


def test_both_tools_use_the_shared_grammar_and_keep_no_private_copy():
    """The convergence itself: a second regex set is how these diverged."""
    audit = (_REPO / "scripts" / "audit_api_wiring.py").read_text(encoding="utf-8")
    scanner = (_BACKEND / "api" / "codebase_analytics" / "api_endpoint_scanner.py").read_text(encoding="utf-8")

    for name, source in (("audit_api_wiring", audit), ("api_endpoint_scanner", scanner)):
        assert "autobot_shared.api_routing" in source, f"{name} does not import the shared grammar"
        assert (
            're.compile(r"APIRouter' not in source and "re.compile(r'APIRouter" not in source
        ), f"{name} declares its own APIRouter-prefix regex again"
        assert (
            're.compile(r"include_router' not in source and "re.compile(r'include_router" not in source
        ), f"{name} declares its own include_router regex again"
