# Copyright 2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""SCRATCH, NEVER MERGED: a deliberate hang that proves #16516's last criterion.

The shard runs with ``-o faulthandler_timeout=$PYTEST_FAULTHANDLER_TIMEOUT_S``
(600s). This test blocks past that in a named frame, so the shard log must
show a faulthandler dump naming ``block_in_a_named_frame`` and this test. The
dump does not stop the test; it returns and passes once the sleep ends.

Skipped outside GitHub Actions so the local pre-push hook does not block for
eleven minutes.
"""

import os
import time

import pytest

_PAST_THE_TIMEOUT_S = 660


def block_in_a_named_frame(seconds: int) -> None:
    time.sleep(seconds)


@pytest.mark.skipif(
    os.environ.get("GITHUB_ACTIONS") != "true",
    reason="#16516 deliberate hang runs only in CI",
)
def test_deliberate_hang_dumps_a_traceback_16516():
    block_in_a_named_frame(_PAST_THE_TIMEOUT_S)
