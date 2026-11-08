# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Co-located with ``one_serving_predicate_baseline_18820.py`` (#18820).

Pre-push runs a changed module's co-located test, so any edit to the baseline runs the
<=-main check here, where ``origin/main`` is fetched. CI's shallow shards cannot (they skip
with that reason), so this file is what makes the check bite before a push lands.
"""

from __future__ import annotations

from repo_tests.one_serving_predicate_18820_test import (
    test_one_pr_cannot_raise_both_the_frozen_total_and_the_list as _baseline_cannot_outgrow_main,
)


def test_the_baseline_cannot_outgrow_main() -> None:
    _baseline_cannot_outgrow_main()
