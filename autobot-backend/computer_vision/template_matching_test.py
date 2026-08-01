# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for TemplateMatchingEngine.find_common_elements (Issue #11580).

Verifies real cv2.matchTemplate detection with non-maximum suppression,
replacing the previous silent stub that always returned an empty list.
"""

import numpy as np
import pytest

from computer_vision.classifiers import TemplateMatchingEngine

cv2 = pytest.importorskip("cv2")


def _make_patch() -> np.ndarray:
    """Build a small, visually distinctive grayscale template."""
    patch = np.zeros((20, 20), dtype=np.uint8)
    cv2.rectangle(patch, (2, 2), (17, 17), 255, 2)
    cv2.line(patch, (2, 2), (17, 17), 200, 1)
    return patch


@pytest.fixture
def template_dir(tmp_path):
    """A templates directory containing a single close_button template."""
    tdir = tmp_path / "templates"
    tdir.mkdir()
    cv2.imwrite(str(tdir / "close_button.png"), _make_patch())
    return tdir


@pytest.mark.asyncio
async def test_finds_three_identical_patches(template_dir):
    """Three identical patches on a screenshot yield exactly three matches."""
    screen = np.zeros((200, 200), dtype=np.uint8)
    coords = [(10, 10), (100, 40), (60, 150)]
    patch = _make_patch()
    for x, y in coords:
        screen[y : y + 20, x : x + 20] = patch

    engine = TemplateMatchingEngine(templates_dir=template_dir)
    matches = await engine.find_common_elements(screen)

    assert len(matches) == 3
    centers = sorted(m["center"] for m in matches)
    assert centers == sorted((x + 10, y + 10) for x, y in coords)
    for match in matches:
        assert match["template_name"] == "close_button"
        assert match["element_type"] == "button"
        assert match["confidence"] >= 0.99
        assert set(match["bbox"]) == {"x", "y", "width", "height"}


@pytest.mark.asyncio
async def test_no_templates_returns_empty(tmp_path):
    """Absent a templates directory the engine legitimately returns empty."""
    engine = TemplateMatchingEngine(templates_dir=tmp_path / "missing")
    assert await engine.find_common_elements(np.zeros((50, 50), dtype=np.uint8)) == []


@pytest.mark.asyncio
async def test_empty_screenshot_returns_empty(template_dir):
    """An empty screenshot short-circuits to an empty result."""
    engine = TemplateMatchingEngine(templates_dir=template_dir)
    assert await engine.find_common_elements(np.array([])) == []


@pytest.mark.asyncio
async def test_no_match_returns_empty(template_dir):
    """A flat screenshot with no template present returns empty."""
    engine = TemplateMatchingEngine(templates_dir=template_dir)
    flat = np.full((200, 200), 128, dtype=np.uint8)
    assert await engine.find_common_elements(flat) == []
