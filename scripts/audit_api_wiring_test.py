# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the SLM-backend union + baseline logic in audit_api_wiring.py (#12381).

Real-repo authoritative mode requires backend deps that aren't installed in
this dev environment (WSL missing autobot_shared/deps), so these tests
exercise the union + baseline LOGIC directly against small mock openapi.json
fixtures rather than importing app_factory.create_app() / the SLM app. CI
verifies the real route tables when the workflow runs --dump-openapi and
--dump-slm-openapi against the built apps.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "audit_api_wiring.py"
_spec = importlib.util.spec_from_file_location("audit_api_wiring", SCRIPT)
audit = importlib.util.module_from_spec(_spec)
sys.modules["audit_api_wiring"] = audit
_spec.loader.exec_module(audit)  # type: ignore[union-attr]


def _write_openapi(path: Path, paths: list[str]) -> Path:
    path.write_text(json.dumps({"paths": {p: {} for p in paths}}), encoding="utf-8")
    return path


# --------------------------------------------------------- SLM union ----


def test_slm_only_route_is_wired_after_union(tmp_path):
    """A frontend call matching ONLY the SLM backend's route table is not
    unwired once --slm-openapi is unioned in (the #12381 bug)."""
    backend_json = _write_openapi(tmp_path / "backend.json", ["/api/foo"])
    slm_json = _write_openapi(tmp_path / "slm.json", ["/api/nodes"])

    backend = audit.backend_paths_from_openapi(str(backend_json))
    assert not audit.matches("/api/nodes", backend), "sanity: SLM-only route absent pre-union"

    backend |= audit.backend_paths_from_openapi(str(slm_json))
    assert audit.matches("/api/nodes", backend)
    assert audit.matches("/api/foo", backend)
    assert not audit.matches("/api/bar", backend)


def test_slm_union_preserves_single_backend_behavior(tmp_path):
    """Absent --slm-openapi, behavior is unchanged (single-backend set)."""
    backend_json = _write_openapi(tmp_path / "backend.json", ["/api/foo"])
    backend = audit.backend_paths_from_openapi(str(backend_json))
    assert backend == {"/api/foo"}


# --------------------------------------------------------- websocket scan ----


def test_static_websocket_paths_finds_prefixed_websocket_route(tmp_path_factory):
    """A source-level scan finds @router.websocket() routes and combines them
    with the router's own prefix AND any include_router() mount prefix — the
    fix for CI's "+0 websocket" bug (fastapi>=0.139's lazy _IncludedRouter
    wrapping breaks the old isinstance(r, WebSocketRoute) runtime walk, #12381).
    """
    # tmp_path_factory (not the function-scoped tmp_path fixture): tmp_path's
    # own directory is named "test_<function-name>0", which would trip the
    # "/test_" source-exclusion filter (correctly, for real repo paths like
    # "api/test_foo.py") regardless of nesting depth beneath it.
    src = tmp_path_factory.mktemp("ws_scan_fixture")
    module = src / "advanced_control.py"
    module.write_text(
        'router = APIRouter(prefix="/advanced-control")\n'
        '@router.websocket("/ws/desktop/{session_id}")\n'
        "async def ws_desktop(websocket): ...\n"
        '@router.get("/status")\n'
        "async def status(): ...\n",
        encoding="utf-8",
    )
    mount = src / "app_factory.py"
    mount.write_text('app.include_router(advanced_control_router, prefix="/api")\n', encoding="utf-8")

    ws_paths = audit.static_websocket_paths(src)
    assert "/api/advanced-control/ws/desktop/{p}" in ws_paths
    # The GET /status route must NOT be picked up by the websocket-only scan.
    assert not any(p.endswith("/status") for p in ws_paths)


def test_static_websocket_paths_ignores_test_files(tmp_path_factory):
    src = tmp_path_factory.mktemp("ws_scan_fixture")
    (src / "foo_test.py").write_text(
        'router = APIRouter()\n@router.websocket("/ws")\nasync def h(websocket): ...\n',
        encoding="utf-8",
    )
    assert audit.static_websocket_paths(src) == set()


def test_dump_openapi_websocket_union_survives_empty_runtime_walk(monkeypatch, tmp_path, tmp_path_factory):
    """Simulates the exact CI failure mode: a fake `app` whose .routes yields
    zero WebSocketRoute instances (the fastapi>=0.139 _IncludedRouter case) —
    x-websocket-paths must still be populated from the static scan."""
    # tmp_path_factory — see comment in
    # test_static_websocket_paths_finds_prefixed_websocket_route for why.
    src = tmp_path_factory.mktemp("ws_scan_fixture")
    ws_module = src / "ws_router.py"
    ws_module.write_text(
        'router = APIRouter()\n@router.websocket("/ws")\nasync def h(websocket): ...\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(audit, "BACKEND", src)

    class _FakeApp:
        routes = []  # simulates app.routes with everything hidden in _IncludedRouter

        def openapi(self):
            return {"paths": {"/api/foo": {}}}

    fake_app = _FakeApp()

    class _FakeAppFactoryModule:
        @staticmethod
        def create_app():
            return fake_app

    monkeypatch.setitem(sys.modules, "app_factory", _FakeAppFactoryModule)
    monkeypatch.setattr(os, "chdir", lambda *_a, **_k: None)

    out = tmp_path / "openapi.json"
    rc = audit.dump_openapi(str(out))
    assert rc == 0
    spec = json.loads(out.read_text(encoding="utf-8"))
    # No include_router(prefix="/api") mount in this fixture tree, so the
    # static scan yields the bare route ("/ws") rather than a prefixed one —
    # prefix combination itself is covered by
    # test_static_websocket_paths_finds_prefixed_websocket_route above. The
    # point here is that the union is non-empty despite the empty runtime walk.
    assert "/ws" in spec["x-websocket-paths"]
    assert _runtime_websocket_paths_returns_empty(fake_app)


def _runtime_websocket_paths_returns_empty(fake_app) -> bool:
    return audit._runtime_websocket_paths(fake_app) == set()


# --------------------------------------------------------- baseline ----


def test_load_baseline_skips_blanks_and_comments(tmp_path):
    baseline_file = tmp_path / "baseline.txt"
    baseline_file.write_text(
        "# comment\n\n/api/browser/launch\n  \n/api/dev-speedup/format\n# another\n",
        encoding="utf-8",
    )
    assert audit.load_baseline(str(baseline_file)) == {
        "/api/browser/launch",
        "/api/dev-speedup/format",
    }


def test_load_baseline_none_and_missing_file_return_empty_set(tmp_path):
    assert audit.load_baseline(None) == set()
    assert audit.load_baseline(str(tmp_path / "does-not-exist.txt")) == set()


def test_partition_baseline_splits_tracked_from_new():
    unwired = {
        "/api/tracked": {"file_a.ts"},
        "/api/new": {"file_b.ts"},
    }
    tracked, new = audit.partition_baseline(unwired, {"/api/tracked"})
    assert tracked == {"/api/tracked": {"file_a.ts"}}
    assert new == {"/api/new": {"file_b.ts"}}


def test_partition_baseline_empty_baseline_is_noop():
    unwired = {"/api/x": {"f.ts"}}
    tracked, new = audit.partition_baseline(unwired, set())
    assert tracked == {}
    assert new == unwired


# --------------------------------------------------------- main() gating ----


def test_baselined_call_does_not_fail_but_new_unwired_call_does(tmp_path, monkeypatch, capsys):
    """End-to-end through main(): a call matching an SLM-only route is wired,
    a baselined dead call is reported but non-gating, and a genuinely-new
    unwired call still trips --fail-on-unwired."""
    backend_json = _write_openapi(tmp_path / "backend.json", ["/api/wired"])
    slm_json = _write_openapi(tmp_path / "slm.json", ["/api/slm_only"])
    baseline_file = tmp_path / "baseline.txt"
    baseline_file.write_text("/api/tracked_dead\n", encoding="utf-8")

    fake_calls = {
        "/api/wired": {"file_wired.ts"},
        "/api/slm_only": {"file_slm.ts"},
        "/api/tracked_dead": {"file_tracked.ts"},
        "/api/new_dead": {"file_new.ts"},
    }
    monkeypatch.setattr(audit, "frontend_calls", lambda: fake_calls)
    monkeypatch.setattr(audit, "find_missing_api_prefix", lambda backend: {})

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "audit_api_wiring.py",
            "--openapi",
            str(backend_json),
            "--slm-openapi",
            str(slm_json),
            "--baseline",
            str(baseline_file),
            "--only-prefix",
            "/api",  # skip real-repo unmounted-router scan noise
            "--fail-on-unwired",
        ],
    )
    rc = audit.main()
    out = capsys.readouterr().out

    assert rc & 1 == 1, "genuinely-new unwired call must still fail the gate"
    assert "/api/new_dead" in out
    assert "/api/wired" not in out.split("== UNWIRED FRONTEND CALLS")[1]
    assert "/api/slm_only" not in out.split("== UNWIRED FRONTEND CALLS")[1]
    assert "TRACKED UNWIRED CALLS" in out
    assert "/api/tracked_dead" in out


def test_no_new_unwired_calls_passes_gate(tmp_path, monkeypatch, capsys):
    backend_json = _write_openapi(tmp_path / "backend.json", ["/api/wired"])
    slm_json = _write_openapi(tmp_path / "slm.json", ["/api/slm_only"])
    baseline_file = tmp_path / "baseline.txt"
    baseline_file.write_text("/api/tracked_dead\n", encoding="utf-8")

    fake_calls = {
        "/api/wired": {"file_wired.ts"},
        "/api/slm_only": {"file_slm.ts"},
        "/api/tracked_dead": {"file_tracked.ts"},
    }
    monkeypatch.setattr(audit, "frontend_calls", lambda: fake_calls)
    monkeypatch.setattr(audit, "find_missing_api_prefix", lambda backend: {})

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "audit_api_wiring.py",
            "--openapi",
            str(backend_json),
            "--slm-openapi",
            str(slm_json),
            "--baseline",
            str(baseline_file),
            "--only-prefix",
            "/api",
            "--fail-on-unwired",
        ],
    )
    rc = audit.main()
    assert rc == 0


# --------------------------------------------------------- CLI wiring ----


def test_dump_slm_openapi_flag_dispatches(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        audit,
        "dump_slm_openapi",
        lambda out, include_websocket_paths=True: calls.append((out, include_websocket_paths)) or 0,
    )
    out = str(tmp_path / "out.json")
    monkeypatch.setattr(sys, "argv", ["audit_api_wiring.py", "--dump-slm-openapi", out])
    assert audit.main() == 0
    monkeypatch.setattr(sys, "argv", ["audit_api_wiring.py", "--dump-slm-openapi", out, "--no-websocket-paths"])
    assert audit.main() == 0
    assert calls == [(out, True), (out, False)]


def test_dump_slm_openapi_omits_websocket_paths_on_request(tmp_path, monkeypatch):
    """One flag per dumper: the SLM dump drops x-websocket-paths exactly as the backend dump does (#12363)."""

    class _App:
        routes = []

        def openapi(self):
            return {"paths": {"/api/foo": {}}}

    class _Main:
        app = _App()

    monkeypatch.setitem(sys.modules, "main", _Main)
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setattr(os, "chdir", lambda *_a, **_k: None)
    monkeypatch.setattr(audit, "static_websocket_paths", lambda _root: {"/ws"})
    kept, dropped = tmp_path / "kept.json", tmp_path / "dropped.json"
    assert audit.dump_slm_openapi(str(kept)) == 0
    assert audit.dump_slm_openapi(str(dropped), include_websocket_paths=False) == 0
    assert json.loads(kept.read_text(encoding="utf-8"))["x-websocket-paths"] == [
        "/ws"
    ]  # control: the key is emitted by default
    assert "x-websocket-paths" not in json.loads(dropped.read_text(encoding="utf-8"))


# ------------------------------------------- trailing template placeholder ----


def test_trailing_query_placeholder_is_not_part_of_the_path_20910():
    """`${getApiBase()}/evolution/summary${qs ? ...}` reaches /api/evolution/summary (useEvolution.ts form)."""
    line = "const url = `${getApiBase()}/evolution/summary${qs ? `?${qs}` : ''}`"
    found = ["/api" + s for s in audit.GETAPIBASE_CALL_RE.findall(line)]
    assert [audit.norm_path(m) for m in found] == ["/api/evolution/summary"]
    assert audit.norm_path("/api/x/y${query}") == "/api/x/y"
    assert audit.norm_path("/api/x/${id}") == "/api/x/{p}"
    assert audit.norm_path("/api/x/${id}/y") == "/api/x/{p}/y"


# ---------------------------------------------- request-URL forms (#20910) ----


def _calls_in(tmp_path, source: str) -> set[str]:
    """What ``frontend_calls`` extracts from one frontend source file (through the real walk)."""
    src = tmp_path / "autobot-frontend" / "src"
    src.mkdir(parents=True)
    (src / "use.ts").write_text(source, encoding="utf-8")
    saved = audit.FRONTEND_SRC, audit.REPO_ROOT
    audit.FRONTEND_SRC, audit.REPO_ROOT = src, tmp_path
    try:
        return set(audit.frontend_calls())
    finally:
        audit.FRONTEND_SRC, audit.REPO_ROOT = saved


def test_trailing_query_placeholder_call_is_extracted_without_it_20910(tmp_path):
    line = "const url = `${getApiBase()}/evolution/summary${qs ? `?${qs}` : ''}`\n"
    assert "/api/evolution/summary" in _calls_in(tmp_path, line)


def test_get_backend_url_api_call_is_extracted_20910(tmp_path):
    line = "const r = await fetchWithAuth(`${getBackendUrl()}/api/onboarding/status`, {})\n"
    assert "/api/onboarding/status" in _calls_in(tmp_path, line)


def test_get_backend_url_root_call_is_extracted_20910(tmp_path):
    assert "/ws/terminal" in _calls_in(tmp_path, "const u = `${getBackendUrl()}/ws/terminal`\n")


def test_other_host_placeholder_before_api_is_extracted_20910(tmp_path):
    src = "const a = `${backendUrl}/api/things/${id}`\nconst b = `${NetworkConstants.getBackendUrl()}/api/other`\n"
    assert {"/api/things/{p}", "/api/other"} <= _calls_in(tmp_path, src)


def test_file_local_base_constant_calls_are_extended_20910(tmp_path):
    src = (
        "const API_BASE = `${getApiBase()}/knowledge-graph`\n"
        "const a = `${API_BASE}/entities/${id}`\n"
        "const b = API_BASE + '/events'\n"
    )
    assert {"/api/knowledge-graph/entities/{p}", "/api/knowledge-graph/events"} <= _calls_in(tmp_path, src)


def test_parameterised_base_constant_calls_are_extended_20910(tmp_path):
    """RolesView form: ``const base = `/api/llc/roles/${companyId.value}/${roleId}` `` then ``${base}/holders``."""
    src = (
        "const base = `/api/llc/roles/${companyId.value}/${roleId}`\n"
        "const a = await api.get(`${base}/holders?include_past=${past}`)\n"
        "const b = await api.get(`${base}/permissions`)\n"
    )
    assert {"/api/llc/roles/{p}/{p}/holders", "/api/llc/roles/{p}/{p}/permissions"} <= _calls_in(tmp_path, src)


def test_get_api_base_is_not_a_host_placeholder_for_api_paths_20910(tmp_path):
    """`${getApiBase()}/api/x` is `/api/api/x` at runtime; it must not also read as a call to `/api/x`."""
    found = _calls_in(tmp_path, "const u = `${getApiBase()}/api/x`\n")
    assert "/api/api/x" in found and "/api/x" not in found


def test_chained_base_constants_resolve_in_declaration_order_20910(tmp_path):
    """``const CHILD = `${BASE}/sub` `` then ``${CHILD}/leaf``: the leaf is a call, not an unwired route."""
    src = (
        "const BASE = `${getApiBase()}/knowledge-graph`\n"
        "const CHILD = `${BASE}/entities`\n"
        "const a = await api.get(`${CHILD}/${id}/leaf`)\n"
    )
    assert "/api/knowledge-graph/entities/{p}/leaf" in _calls_in(tmp_path, src)
    # a value led by a name that is not a base is no base: nothing is invented
    assert not any("leaf" in c for c in _calls_in(tmp_path / "x", "const C = `${unknown}/entities`\nf(`${C}/leaf`)\n"))
