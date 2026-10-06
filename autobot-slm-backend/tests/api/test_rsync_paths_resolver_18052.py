# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The moved rsync helpers must resolve the deployed dir from their own module.

#18052 moved six path/rsync helpers out of ``code_sync`` into ``_rsync_paths``.
``_restore_component_snapshot`` resolves ``get_release_component_dir`` from the
new module's globals, so the pre-existing ``patch("api.code_sync....")`` stopped
reaching it -- silently.  The test kept passing while a MagicMock repr was going
into the rsync destination argv.

The argv assertion here is what makes the patch load-bearing: if the helper moves
again, the patch misses, the stub leaks back in, and this fails rather than
passing vacuously.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from api._rsync_paths import _restore_component_snapshot

from .test_code_sync_deploy_bugs import _run


def test_restore_component_snapshot_returns_false_on_timeout(tmp_path) -> None:
    """#15323: the extracted restore helper reports failure on timeout so the
    (now-unconditional) caller's restart-either-way logic has a real signal
    to log, rather than the restart happening with no record of why."""
    deployed = tmp_path / "deployed"
    deployed.mkdir()
    argv: list = []

    async def _fake_exec(*cmd, **kw):
        argv.extend(cmd)
        proc = MagicMock()
        proc.communicate = AsyncMock(side_effect=TimeoutError())
        return proc

    with (
        patch("api.code_sync.get_release_component_dir", return_value=str(deployed)),
        # #18052: the rsync helpers moved to api._rsync_paths and resolve the
        # name from their own module globals, so patching only api.code_sync
        # left the real resolver in play and the patch proved nothing.  The
        # argv assertion below is what makes this patch load-bearing: if the
        # helper moves again, the real resolver returns a different path and
        # this fails instead of passing vacuously.
        patch("api._rsync_paths.get_release_component_dir", return_value=str(deployed)),
        patch("asyncio.create_subprocess_exec", side_effect=_fake_exec),
        patch("asyncio.wait_for", side_effect=__import__("asyncio").TimeoutError),
    ):
        steps: list[str] = []
        result = _run(_restore_component_snapshot("autobot-backend", str(tmp_path / "snap"), steps))

    assert result is False
    assert any("timed out" in s for s in steps)
    assert any(str(deployed) in str(a) for a in argv), f"restore must target the resolved deployed dir, got {argv}"
