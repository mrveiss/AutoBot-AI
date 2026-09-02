# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Sending to many devices does not scale its query count (#15150).

Its own module because `test_mobile_push.py` is at its recorded size ceiling and
a grandfathered file may not grow (#14236). The fixtures moved to
`tests/integration/conftest.py` in the same change, which is where they belonged
once a second module needed them.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from autobot_shared.time_utils import now_utc  # noqa: F401 — fixtures reference it
from models.mobile_device import MobileDevice
from services.push_notification_service import _send_mobile_push


#: Statements a constant-query send may issue. Deliberately small: the point is
#: that it cannot grow with the device count, and 50 devices must not fit.
_MAX_DEVICE_FETCH_QUERIES = 3


@pytest.mark.asyncio
async def test_device_fetching_does_not_scale_with_device_count(
    mock_session_factory, test_db_session, test_user_id
):
    """Sending to 50 devices issues the same number of queries as sending to 5 (#15150).

    This replaces an `assert elapsed < 5.0` wall clock. That bound measured the
    machine, not the code: on unchanged `Dev_new_gui` the same test varied
    1.249s -> 2.616s run to run, a 2.1x swing against a threshold with under 2x
    headroom, and the self-hosted runner regularly has a dozen PRs queued. It
    failed once in a batch, passed in isolation, and passed on a re-run of the
    identical batch -- a load-sensitive threshold, not a defect.

    It also could not do the job it was there for: an N+1 regression on a fast
    machine finishes well inside 5 seconds, so the assertion that was supposed to
    catch it would have stayed green.

    Counting statements states the property directly. `_send_mobile_push` fetches
    devices with one `select` (`mobile_push.py:134-140`); if that ever becomes a
    query per device, this fails no matter how fast the machine is, and it cannot
    fail because something else was running.
    """

    async def _send_and_count_queries(expected_devices: int) -> tuple[int, int]:
        executed: list[object] = []
        original_execute = test_db_session.execute

        async def counting_execute(*args, **kwargs):
            executed.append(args[0] if args else None)
            return await original_execute(*args, **kwargs)

        test_db_session.execute = counting_execute
        try:
            with (
                patch(
                    "user_management.database.get_async_session_factory",
                    return_value=mock_session_factory,
                ),
                patch("push_notifications.mobile_push._send_apns", return_value=True),
                patch("push_notifications.mobile_push._send_fcm", return_value=True),
            ):
                sent = await _send_mobile_push(
                    user_id=test_user_id,
                    title="Bulk Test",
                    body="Testing many devices",
                    url="/",
                )
        finally:
            test_db_session.execute = original_execute

        assert sent == expected_devices, f"expected {expected_devices} sends, got {sent}"
        return sent, len(executed)

    def _devices(start: int, stop: int) -> list[MobileDevice]:
        return [
            MobileDevice(
                user_id=test_user_id,
                device_name=f"Device {i}",
                device_token=f"token-{i}",
                platform="ios" if i % 2 == 0 else "android",
                # `last_seen_at=None` on purpose. `_get_target_devices` accepts a
                # device with no last-seen (`mobile_push.py:153`), and going
                # through a stored timestamp drags in a naive/aware comparison
                # that has nothing to do with what this test measures. See
                # #15478 for that fragility, which is real and separate.
                last_seen_at=None,
            )
            for i in range(start, stop)
        ]

    for device in _devices(0, 50):
        test_db_session.add(device)
    await test_db_session.commit()

    _, queries = await _send_and_count_queries(50)

    # A constant bound, not a ratio. One `select` fetches every device
    # (mobile_push.py:134-140); the allowance leaves room for a second statement
    # without leaving room for a query per device. An N+1 regression makes this
    # ~50 and fails on any machine, however fast -- which the 5-second wall clock
    # it replaced would not have.
    assert queries <= _MAX_DEVICE_FETCH_QUERIES, (
        f"sending to 50 devices issued {queries} statements, more than the "
        f"{_MAX_DEVICE_FETCH_QUERIES} a constant-query fetch needs. Device fetching "
        "now scales with device count -- an N+1."
    )
