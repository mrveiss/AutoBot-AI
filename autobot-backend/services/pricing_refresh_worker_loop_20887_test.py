# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20887: pricing Celery task bodies run on the persistent worker loop; only the CLI keeps asyncio.run."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest


@pytest.mark.parametrize(
    "task_attr,body_attr",
    [("refresh_pricing_if_empty", "refresh_if_empty"), ("refresh_pricing_daily", "refresh_all")],
)
def test_task_bodies_route_through_run_in_worker_loop(task_attr, body_attr):
    from services import pricing_refresh

    async def fake_body():
        return {"written": 0}

    seen: list[object] = []

    def fake_run(coro):
        seen.append(coro)
        coro.close()
        return {"written": 0}

    with (
        patch.object(pricing_refresh, body_attr, fake_body),
        patch.object(pricing_refresh, "run_in_worker_loop", fake_run),
    ):
        getattr(pricing_refresh, task_attr).run()
    assert len(seen) == 1
    # The coroutine handed to the loop is the patched body, not some other coroutine.
    assert seen[0].cr_code is fake_body.__code__


def test_cli_main_still_uses_asyncio_run(capsys):
    from services import pricing_refresh

    async def fake_refresh_all():
        return {"written": 1}

    with patch.object(pricing_refresh, "refresh_all", fake_refresh_all):
        assert pricing_refresh.main() == 0
    assert json.loads(capsys.readouterr().out) == {"written": 1}
