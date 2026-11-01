# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20567: the proposal routes create a PENDING approval, refuse with 409 when there is nothing to remove."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api import admin_cleanup_proposals as routes
from services import install_cleanup_actions as acts


def _seed(root: Path) -> None:
    backend = root / "autobot-backend"
    backend.mkdir(parents=True)
    for i in (1, 2):
        path = backend / f".env.{i}~"
        path.write_text("x", encoding="utf-8")
        os.utime(path, (i * 100, i * 100))


async def test_status_counts_and_proposal_does_not_remove(tmp_path: Path) -> None:
    await asyncio.to_thread(_seed, tmp_path)
    create = AsyncMock(return_value=SimpleNamespace(id="a1", status="pending"))
    with (
        patch.object(acts, "install_root", return_value=tmp_path),
        patch.object(routes, "ApprovalGateService", return_value=SimpleNamespace(create_approval=create)),
    ):
        status = await routes.env_copies_status()
        reply = await routes.propose_env_copies_cleanup({"id": "u1"}, MagicMock())
    assert status.count == 1 and reply.action == acts.ENV_COPIES_ACTION
    assert create.await_args.kwargs["context"] == {"action": acts.ENV_COPIES_ACTION}
    assert len(await asyncio.to_thread(lambda: list((tmp_path / "autobot-backend").glob(".env.*~")))) == 2


async def test_nothing_to_remove_is_409(tmp_path: Path) -> None:
    with patch.object(acts, "install_root", return_value=tmp_path):
        with pytest.raises(HTTPException) as err:
            await routes.propose_infrastructure_dir_removal({"id": "u1"}, MagicMock())
    assert err.value.status_code == 409
