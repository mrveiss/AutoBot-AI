# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""`to_rfc3339` must emit exactly one zone designator (#12967).

`isoformat() + "Z"` is correct only for a naive UTC datetime. On an aware one
the offset is already there, so the result carries a doubled zone
(`+00:00Z`). Prometheus rejected every range query built that way with HTTP
400, and because the caller only logged a warning the graphs came back empty
instead of erroring.
"""

from datetime import datetime, timedelta, timezone

import pytest

from autobot_shared.time_utils import to_rfc3339

AWARE = datetime(2026, 7, 29, 13, 23, 29, tzinfo=timezone.utc)
NAIVE = datetime(2026, 7, 29, 13, 23, 29)


@pytest.mark.parametrize("value", [AWARE, NAIVE])
def test_never_emits_a_doubled_zone(value):
    """The exact defect: '+00:00Z' is not valid RFC3339."""
    rendered = to_rfc3339(value)

    assert "+00:00" not in rendered
    assert rendered.count("Z") == 1
    assert rendered.endswith("Z")


def test_aware_utc_renders_with_z():
    assert to_rfc3339(AWARE) == "2026-07-29T13:23:29Z"


def test_naive_is_treated_as_utc():
    """Matches parse_utc_iso's convention, so a round trip is stable."""
    assert to_rfc3339(NAIVE) == "2026-07-29T13:23:29Z"


def test_non_utc_offset_is_converted_not_relabelled():
    """A +02:00 time must shift, not just get its suffix swapped."""
    berlin = datetime(2026, 7, 29, 15, 23, 29, tzinfo=timezone(timedelta(hours=2)))

    assert to_rfc3339(berlin) == "2026-07-29T13:23:29Z"


def test_output_is_parseable_back():
    from autobot_shared.time_utils import parse_utc_iso

    assert parse_utc_iso(to_rfc3339(AWARE)) == AWARE
