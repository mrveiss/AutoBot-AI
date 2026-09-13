# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Credential-free local admin entry point for the SLM self-update trigger (#15728).

Today, ``POST /api/code-sync/self-update`` requires an authenticated user --
correct for the network-facing API, but it means an operator already on the
SLM host, who by definition has root there, still has to hold a password to
run routine maintenance. ``/recovery`` (#15462, ``api/health.py``) is the
credential-free entry point for a BROKEN frontend; it is deliberately public
and solves a different problem, and must keep working exactly as it does.

This module is Option 1 from #15728: a second ASGI listener, reachable ONLY
over a Unix domain socket that systemd itself creates and owns via a paired
``.socket`` unit (``autobot-slm-self-update.socket`` -- see
``autobot-slm-backend/ansible/roles/slm_manager/templates/``). Systemd's
``SocketMode=``/``SocketUser=``/``SocketGroup=`` set the socket file's
permissions BEFORE this process ever runs, and hand the already-open,
already-permissioned file descriptor to this exact PID via the standard
``sd_listen_fds()`` protocol (``LISTEN_PID``/``LISTEN_FDS`` env vars -- the
same mechanism ``slm/agent/agent.py`` already uses for ``NOTIFY_SOCKET``, just
the listen side of it). Presence of that fd IS the credential: nothing this
process reads, checks or stores has to be a secret, and the OS enforces "who
can even open the socket" the same way it already enforces "who can SSH in
and become root here" -- a boundary the repo does not have to reimplement.

Deliberately NOT built as ``uvicorn.Config(app, uds=<path>)``: uvicorn binds
that path itself and unconditionally ``chmod``s it ``0o666`` (world
read/write) -- see ``uvicorn.config.Config.bind_socket`` -- which would hand
the credential-free trigger to every local process, defeating the entire
point. Socket activation sidesteps that hard-coded mode entirely by never
letting this process create the socket file at all.

Also deliberately NOT a loopback-bound HTTP route: the SLM backend's own
public API already binds ``127.0.0.1`` only (nginx reverse-proxies to it over
loopback -- see ``autobot-infrastructure/shared/config/nginx/slm-site.conf``),
and it still 401s a request run from a shell on the box, because every
request nginx forwards -- local or remote -- arrives with source
``127.0.0.1`` too. An IP check on that listener could not tell "an operator's
shell on this host" apart from "anyone on the internet, via nginx"; a
completely separate Unix domain socket can, structurally, because it is not
reachable over any network transport at all.
"""

import asyncio
import logging
import os
from dataclasses import dataclass

import uvicorn
from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

from api.code_sync import resolve_and_queue_self_update
from services.database import get_db

logger = logging.getLogger(__name__)

# First fd systemd hands a socket-activated process (sd_listen_fds() always
# starts numbering inherited descriptors here -- see systemd.socket(5) and
# `man sd_listen_fds`). Not configurable: it is part of the sd_listen_fds()
# wire protocol, not an AutoBot setting.
_SD_LISTEN_FDS_START = 3


def _socket_activated_fd() -> int | None:
    """Return the inherited local-admin socket fd, or None when not present.

    None on every path that must NOT expose this listener: ``LISTEN_FDS``/
    ``LISTEN_PID`` unset (dev checkout, CI, an install that has not deployed
    ``autobot-slm-self-update.socket`` yet), or a ``LISTEN_PID`` that does not
    match this process (a forked child inheriting the parent's env without
    actually owning the fd -- the same "turns out to be reachable somewhere
    it shouldn't" failure mode #15728 calls out, just at the process-identity
    layer instead of the network layer).
    """
    listen_pid = os.environ.get("LISTEN_PID")
    listen_fds = os.environ.get("LISTEN_FDS")
    if not listen_pid or not listen_fds:
        return None
    try:
        if int(listen_pid) != os.getpid() or int(listen_fds) < 1:
            return None
    except ValueError:
        logger.warning("Malformed LISTEN_PID/LISTEN_FDS — ignoring local admin socket (#15728)")
        return None
    return _SD_LISTEN_FDS_START


def create_local_admin_app() -> FastAPI:
    """Build the ASGI app served ONLY over the local admin socket (#15728).

    Carries no auth dependency of its own -- reachability over the inherited
    fd already proves the caller is on the host with permission to open the
    socket (AC #1/#2). Never ``include_router`` this into ``main.py``'s public
    ``app`` -- that would put this route back on the network-facing listener
    this design exists to avoid.

    Deliberately no ``response_model=``/return annotation on the route below:
    either one would make FastAPI resolve ``models.schemas.NodeSyncResponse``
    at route-REGISTRATION time (this function's call time), coupling this
    tiny, undocumented (``docs_url=None``) admin app's import order to the
    same ``models.schemas`` stand-in dance ``tests/api/_code_sync_import.py``
    exists to manage for the real HTTP router. ``resolve_and_queue_self_update``
    already returns a real ``NodeSyncResponse`` in production; FastAPI's
    default ``jsonable_encoder`` serializes it the same either way.
    """
    app = FastAPI(title="AutoBot SLM local admin", docs_url=None, redoc_url=None, openapi_url=None)

    @app.post("/self-update")
    async def local_self_update(db: Annotated[AsyncSession, Depends(get_db)]):
        return await resolve_and_queue_self_update(db)

    return app


@dataclass
class LocalAdminSocketHandle:
    """Background task + uvicorn.Server pair for graceful lifespan shutdown (#15728)."""

    task: "asyncio.Task[None]"
    server: uvicorn.Server

    async def stop(self) -> None:
        """Ask uvicorn's own graceful-exit flag to unwind, then wait for the task.

        NOT ``task.cancel()``: that would abort mid-``main_loop()`` and skip
        ``server.shutdown()``, potentially leaving the inherited fd's
        connections half-closed during the very restart self-update itself
        triggers. Setting ``should_exit`` lets ``_run_local_admin_server``
        finish its own ``shutdown()`` call before returning.
        """
        self.server.should_exit = True
        try:
            await self.task
        except asyncio.CancelledError:
            pass


async def _run_local_admin_server(server: uvicorn.Server) -> None:
    """Run a uvicorn.Server without installing its own process signal handlers.

    Reimplements ``uvicorn.Server._serve()`` minus ``capture_signals()``: this
    listener is a background task inside the SAME process as the primary
    FastAPI app, whose OWN uvicorn.Server already owns SIGINT/SIGTERM (set up
    by ``main.py``'s normal startup). A second ``add_signal_handler()`` call
    for the same signal replaces the first on the running loop, which would
    silently break the primary server's graceful shutdown -- exactly the kind
    of regression #11668's SIGTERM handling exists to prevent. main.py's
    lifespan shutdown calls ``LocalAdminSocketHandle.stop()`` explicitly, so no
    signal handling of its own is needed here.
    """
    config = server.config
    if not config.loaded:
        config.load()
    server.lifespan = config.lifespan_class(config)
    await server.startup()
    if not server.should_exit:
        await server.main_loop()
    if server.started:
        await server.shutdown()


async def start_local_admin_socket() -> LocalAdminSocketHandle | None:
    """Serve the local admin app over the inherited systemd socket, if any (#15728).

    Returns None when this process was not socket-activated -- callers (only
    ``main.py``'s lifespan) must treat that as "the feature is not deployed on
    this host" and continue startup normally, the same non-fatal shape as
    every other optional lifespan step (internal API key seeding, SCIM token
    seeding, etc.) -- a missing local admin socket must never block the
    primary, authenticated API from serving.
    """
    fd = _socket_activated_fd()
    if fd is None:
        logger.info("Local self-update admin socket not present (LISTEN_FDS unset) — skipping (#15728)")
        return None

    uv_config = uvicorn.Config(create_local_admin_app(), fd=fd, log_level="warning")
    server = uvicorn.Server(uv_config)
    task = asyncio.create_task(_run_local_admin_server(server))
    logger.info("Local self-update admin socket listening (fd=%s) (#15728)", fd)
    return LocalAdminSocketHandle(task=task, server=server)
