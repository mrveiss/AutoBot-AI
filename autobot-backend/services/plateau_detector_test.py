# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for services.plateau_detector.plateau_reached (#12624)."""

from __future__ import annotations

from services.plateau_detector import plateau_reached


class TestPlateauReached:
    def test_fewer_flags_than_window_never_plateaus(self) -> None:
        assert plateau_reached([False], window=3) is False

    def test_all_false_over_window_is_a_plateau(self) -> None:
        assert plateau_reached([False, False], window=2) is True

    def test_one_true_within_window_prevents_plateau(self) -> None:
        assert plateau_reached([False, True], window=2) is False

    def test_only_the_trailing_window_matters(self) -> None:
        # An old True outside the window must not mask a later plateau.
        assert plateau_reached([True, False, False], window=2) is True

    def test_empty_flags_never_plateaus(self) -> None:
        assert plateau_reached([], window=1) is False
