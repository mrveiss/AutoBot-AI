# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""One answer for a rejected path, and nothing of the path in it (#13579)."""

from __future__ import annotations

import pathlib
import re

import pytest
from fastapi import HTTPException

from autobot_shared.security.path_http import (
    PATH_REFUSED_DETAIL,
    PATH_REFUSED_STATUS,
    require_contained_path,
    require_contained_relative_path,
)

_REPO = pathlib.Path(__file__).resolve().parent.parent.parent


@pytest.mark.parametrize("segment", ["../etc/passwd", "/etc/passwd", "a/../../b"])
def test_a_rejected_relative_segment_is_always_the_same_refusal(tmp_path, segment: str) -> None:
    with pytest.raises(HTTPException) as exc:
        require_contained_relative_path(segment, tmp_path)
    assert exc.value.status_code == PATH_REFUSED_STATUS
    assert exc.value.detail == PATH_REFUSED_DETAIL


@pytest.mark.parametrize("path", ["/etc/passwd", "../../etc/shadow"])
def test_a_rejected_absolute_path_is_always_the_same_refusal(tmp_path, path: str) -> None:
    with pytest.raises(HTTPException) as exc:
        require_contained_path(path, allowed_roots=[str(tmp_path)])
    assert exc.value.status_code == PATH_REFUSED_STATUS
    assert exc.value.detail == PATH_REFUSED_DETAIL


def test_the_refusal_never_echoes_the_path_or_the_roots(tmp_path) -> None:
    """The detail reaches the client.

    Echoing the rejected path, or the roots it failed against, answers the probe
    it was sent to make -- the reply describes the filesystem layout the caller
    was guessing at.
    """
    secret_root = tmp_path / "very-distinctive-root-name"
    secret_root.mkdir()
    with pytest.raises(HTTPException) as exc:
        require_contained_path("/etc/distinctive-probe-target", allowed_roots=[str(secret_root)])
    rendered = f"{exc.value.detail}"
    assert "distinctive-probe-target" not in rendered
    assert "very-distinctive-root-name" not in rendered
    assert str(tmp_path) not in rendered


def test_a_tilde_segment_is_contained_not_rejected(tmp_path) -> None:
    """`~` is shell expansion, not a path feature.

    Under `validate_relative_path` it is an ordinary directory name and stays
    inside the base, so rejecting it would be wrong. `resolve_within_sandbox`
    does forbid it (THREAT_MODEL, section 1) -- a different function with a
    stricter contract, and the distinction is easy to misread as a gap here.
    """
    out = require_contained_relative_path("~/secrets", tmp_path)
    assert str(out).startswith(str(tmp_path))


def test_an_accepted_path_is_returned_unchanged(tmp_path) -> None:
    """A guard that rejects everything passes every rejection test."""
    (tmp_path / "ok.txt").write_text("x", encoding="utf-8")
    assert require_contained_relative_path("ok.txt", tmp_path).name == "ok.txt"
    assert require_contained_path(str(tmp_path / "ok.txt"), allowed_roots=[str(tmp_path)]).name == "ok.txt"


def test_the_shared_status_is_not_403() -> None:
    """403 asserts a real target the caller may not have.

    Validation here is lexical and containment-based and never asks whether the
    target exists, so 403 claims something the validator did not establish -- and
    it lets a caller separate "outside the roots" from "malformed", mapping the
    boundary. Same reasoning as #14012's 409-for-both ruling on session ownership.
    """
    assert PATH_REFUSED_STATUS == 400


def test_no_endpoint_hand_writes_the_translation_again() -> None:
    """Six call sites disagreed; the point is that there is now one.

    The single permitted exception is the recordings route, which answers 404 so
    that an out-of-bounds path is indistinguishable from a missing file -- see
    the comment there. Any other hand-written translation is the regression.
    """
    offenders = []
    for path in sorted((_REPO / "autobot-backend").rglob("*.py")):
        if "test" in path.name:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "validate_path" not in text and "validate_relative_path" not in text:
            continue
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if not re.search(r"except ValueError", line):
                continue
            window = "\n".join(lines[i : i + 6])
            before = "\n".join(lines[max(0, i - 25) : i])
            if "HTTPException" not in window:
                continue
            if "validate_path" not in before and "validate_relative_path" not in before:
                continue
            offenders.append(f"{path.relative_to(_REPO)}:{i + 1}")

    allowed = {"autobot-backend/transcriber/routes/recordings.py"}
    unexpected = [o for o in offenders if o.rsplit(":", 1)[0] not in allowed]
    assert not unexpected, (
        f"these translate a path-validator ValueError by hand instead of using "
        f"autobot_shared.security.path_http: {unexpected}"
    )
