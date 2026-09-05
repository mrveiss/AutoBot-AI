# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#15728 -- credential-free local admin socket for the self-update trigger.

``services/local_admin_socket.py`` is Option 1 from the issue: a second ASGI
listener reachable ONLY over a Unix domain socket that systemd itself creates
and permissions via a paired ``.socket`` unit, handed to this process solely
through the ``sd_listen_fds()`` protocol (``LISTEN_PID``/``LISTEN_FDS``).

The acceptance criterion that matters most (#4) is the negative one: a
loopback admin route's failure mode is "turns out to be reachable from
somewhere it shouldn't" -- for a socket-activated listener that translates to
"turns out to bind something without systemd actually having handed it a
permissioned fd". Every contrast pair below has that negative half:

* ``_socket_activated_fd`` -- present+matching-PID vs. absent / wrong PID /
  zero count.
* ``start_local_admin_socket`` -- returns a real handle when activated vs.
  ``None`` (nothing exposed, nothing bound) when not.
* the admin app's route surface -- carries exactly ``/self-update`` and NONE
  of the authenticated ``code-sync`` router's other paths (status, drift,
  pull, fleet/*, ...), proving this credential-free app can never leak the
  rest of that surface.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _code_sync_import import import_code_sync  # noqa: E402

import_code_sync()

import api.code_sync as code_sync  # noqa: E402

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_MODULE_PATH = _BACKEND_ROOT / "services" / "local_admin_socket.py"


def _load_local_admin_socket():
    """Load services.local_admin_socket by path (#15728).

    ``services`` is a MagicMock in the root conftest (#3499) -- only
    ``tests/services/conftest.py`` swaps it for a real hollow package, and
    this file must not depend on collection order to get the REAL module.
    Same pattern conftest.py's own ``_REAL_SERVICE_MODULES`` loader uses.
    """
    cached = sys.modules.get("services.local_admin_socket")
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location("services.local_admin_socket", _MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["services.local_admin_socket"] = module
    spec.loader.exec_module(module)
    return module


local_admin_socket = _load_local_admin_socket()


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _clean_env(**overrides):
    env = dict(os.environ)
    env.pop("LISTEN_PID", None)
    env.pop("LISTEN_FDS", None)
    env.update(overrides)
    return env


# ---------------------------------------------------------------------------
# _socket_activated_fd -- the contrast pair AC4 is actually about
# ---------------------------------------------------------------------------


def test_fd_present_and_pid_matches_is_socket_activated():
    env = _clean_env(LISTEN_PID=str(os.getpid()), LISTEN_FDS="1")
    with patch.dict(os.environ, env, clear=True):
        assert local_admin_socket._socket_activated_fd() == 3


def test_fd_absent_is_not_socket_activated():
    """#15728 AC4: the feature not being deployed must expose nothing."""
    with patch.dict(os.environ, _clean_env(), clear=True):
        assert local_admin_socket._socket_activated_fd() is None


def test_fd_present_but_wrong_pid_is_not_socket_activated():
    """#15728 AC4: a LISTEN_PID for a DIFFERENT process (e.g. inherited by a
    forked child that never actually received the fd) must not be trusted."""
    env = _clean_env(LISTEN_PID=str(os.getpid() + 1), LISTEN_FDS="1")
    with patch.dict(os.environ, env, clear=True):
        assert local_admin_socket._socket_activated_fd() is None


def test_fd_present_but_zero_count_is_not_socket_activated():
    env = _clean_env(LISTEN_PID=str(os.getpid()), LISTEN_FDS="0")
    with patch.dict(os.environ, env, clear=True):
        assert local_admin_socket._socket_activated_fd() is None


def test_malformed_listen_env_is_not_socket_activated():
    env = _clean_env(LISTEN_PID="not-a-pid", LISTEN_FDS="1")
    with patch.dict(os.environ, env, clear=True):
        assert local_admin_socket._socket_activated_fd() is None


# ---------------------------------------------------------------------------
# start_local_admin_socket -- wiring, without ever touching a real fd
# ---------------------------------------------------------------------------


def test_start_returns_none_when_not_socket_activated():
    with patch.dict(os.environ, _clean_env(), clear=True):
        handle = _run(local_admin_socket.start_local_admin_socket())
    assert handle is None


def test_start_returns_a_handle_when_socket_activated():
    """The positive half of the AC4 contrast: when a fd IS inherited, the
    listener must actually be wired up, not silently skipped too."""
    fake_server = MagicMock()
    fake_server.should_exit = False
    env = _clean_env(LISTEN_PID=str(os.getpid()), LISTEN_FDS="1")

    async def _start_and_drain():
        handle = await local_admin_socket.start_local_admin_socket()
        if handle is not None:
            await handle.task
        return handle

    with (
        patch.dict(os.environ, env, clear=True),
        patch("services.local_admin_socket.uvicorn.Config") as mock_config,
        patch("services.local_admin_socket.uvicorn.Server", return_value=fake_server),
        patch("services.local_admin_socket._run_local_admin_server", AsyncMock(return_value=None)),
    ):
        handle = _run(_start_and_drain())

    assert handle is not None
    assert handle.server is fake_server
    assert mock_config.call_args.kwargs["fd"] == 3


def test_stop_sets_should_exit_and_awaits_the_task():
    async def _scenario():
        task = asyncio.create_task(asyncio.sleep(0))
        server = MagicMock()
        server.should_exit = False
        handle = local_admin_socket.LocalAdminSocketHandle(task=task, server=server)
        await handle.stop()
        return server.should_exit

    assert _run(_scenario()) is True


# ---------------------------------------------------------------------------
# Route surface -- the admin app must carry ONLY the self-update trigger
# ---------------------------------------------------------------------------


def test_local_admin_app_exposes_only_self_update():
    app = local_admin_socket.create_local_admin_app()
    paths = {route.path for route in app.router.routes}
    assert paths == {"/self-update"}


def test_local_admin_app_never_exposes_authenticated_code_sync_paths():
    """#15728 AC4 contrast: none of the OTHER code-sync endpoints -- still
    gated behind get_current_user on the real HTTP router -- may leak onto
    this unauthenticated, socket-only app."""
    other_paths = {r.path for r in code_sync.router.routes if r.path != "/code-sync/self-update"}
    assert len(other_paths) > 10, "sanity: code_sync_router must have plenty of other routes to contrast against"

    admin_paths = {route.path for route in local_admin_socket.create_local_admin_app().router.routes}
    assert admin_paths.isdisjoint(other_paths)


def test_local_admin_app_disables_docs_and_openapi():
    app = local_admin_socket.create_local_admin_app()
    assert app.docs_url is None
    assert app.redoc_url is None
    assert app.openapi_url is None


# ---------------------------------------------------------------------------
# Shared trigger -- one code path, two doors, not two updaters
# ---------------------------------------------------------------------------


def test_http_route_and_local_socket_share_the_same_trigger_function():
    assert local_admin_socket.resolve_and_queue_self_update is code_sync.resolve_and_queue_self_update


def test_local_self_update_route_delegates_to_the_shared_trigger():
    app = local_admin_socket.create_local_admin_app()
    route = next(r for r in app.router.routes if r.path == "/self-update")
    fake_db = object()

    with patch(
        "services.local_admin_socket.resolve_and_queue_self_update",
        AsyncMock(return_value="sentinel"),
    ) as mock_trigger:
        result = _run(route.endpoint(fake_db))

    mock_trigger.assert_awaited_once_with(fake_db)
    assert result == "sentinel"


def test_http_self_update_route_still_requires_get_current_user():
    """#15728 AC3: the authenticated remote path's own auth must be
    completely unchanged by adding the local socket.

    Asserted by IDENTITY against the symbol the route module holds, not by
    name. ``import_code_sync()`` installs stand-ins for ``services.auth``, so
    under this harness ``get_current_user`` is a ``MagicMock`` and reading
    ``__name__`` off it yields ``"MagicMock"`` -- a name comparison passes or
    fails depending on which test imported the module first, which is no test
    at all. Identity against ``code_sync.get_current_user`` says the real
    thing: whatever that symbol resolves to, this route depends on it, and
    removing the dependency fails here.
    """
    route = next(r for r in code_sync.router.routes if r.path == "/code-sync/self-update")
    deps = [d.call for d in route.dependant.dependencies if d.call is not None]
    assert code_sync.get_current_user in deps, f"observed {len(deps)} dependencies, none of them the auth symbol"
