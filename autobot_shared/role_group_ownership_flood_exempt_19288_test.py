# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The stale-role warning is de-duplicated per (node, stale set) and exempt from the flood guard (#19288).

Moving ``role_group_ownership`` to ``get_logger`` attached the flood guard, which keys on the message
template, so the sixth DIFFERENT node in a window was dropped. ``_WARNED`` already limits the warning
to one line per (node, stale set), so the call site is marked ``flood_exempt``.
"""

import logging
import uuid
from collections.abc import Iterator
from types import SimpleNamespace

import pytest

from autobot_shared import role_group_ownership
from autobot_shared.logging_manager import LogFloodSuppressionFilter
from autobot_shared.role_group_ownership import warn_stale_detected_roles

_THRESHOLD = 5


@pytest.fixture
def strict_flood_guard() -> Iterator[None]:
    """A fresh guard on the module logger, whatever AUTOBOT_LOG_FLOOD_ENABLED says."""
    guard = LogFloodSuppressionFilter(threshold=_THRESHOLD, window_seconds=3600.0)
    role_group_ownership.logger.addFilter(guard)
    try:
        yield
    finally:
        role_group_ownership.logger.removeFilter(guard)


def _node(stale: list[str]) -> SimpleNamespace:
    return SimpleNamespace(node_id=f"flood-{uuid.uuid4().hex}", roles=[], detected_roles=stale)


def _warnings(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == role_group_ownership.__name__]


@pytest.mark.usefixtures("strict_flood_guard")
def test_distinct_nodes_past_the_flood_threshold_are_all_reported(caplog: pytest.LogCaptureFixture) -> None:
    nodes = [_node(["vnc"]) for _ in range(_THRESHOLD + 3)]
    with caplog.at_level(logging.WARNING, logger=role_group_ownership.__name__):
        for node in nodes:
            warn_stale_detected_roles(node)
    assert len(_warnings(caplog)) == len(nodes)


@pytest.mark.usefixtures("strict_flood_guard")
def test_one_node_and_stale_set_is_reported_once(caplog: pytest.LogCaptureFixture) -> None:
    node = _node(["vnc"])
    with caplog.at_level(logging.WARNING, logger=role_group_ownership.__name__):
        for _ in range(_THRESHOLD + 3):
            warn_stale_detected_roles(node)
        node.detected_roles = ["vnc", "npu-worker"]
        warn_stale_detected_roles(node)
    assert len(_warnings(caplog)) == 2, "once for the first stale set, once for the changed one"
