# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Field validators must not be named after the path-containment helper (#13518).

Two Pydantic field validators were called `validate_path` and
`validate_path_pattern` — the same names as the canonical containment helpers in
`autobot_shared/security/path_validator.py`. Neither performs containment:
`FileOperation.path` is a shape check on a request field that resolves nothing,
and `SearchCategoriesByPathRequest.path_pattern` validates a *category* pattern's
character set with no filesystem path involved.

The cost was a readability trap with security consequences. Auditing path
handling starts with `grep "def validate_path"`; before this, that returned two
false hits alongside the real helper, and a reviewer skimming the list could
easily conclude a call site was already covered by containment when it was not.

Renaming is only worth doing if it stays done, so this pins both properties: the
validators still enforce what they always did, and the helper's name is once
again unique to the helper.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pydantic")

from pydantic import ValidationError  # noqa: E402

from api.schemas_knowledge import SearchCategoriesByPathRequest  # noqa: E402
from api.schemas_system import FileOperation  # noqa: E402

# --- the validators still do their job --------------------------------------


def test_a_traversal_path_is_still_rejected():
    with pytest.raises(ValidationError):
        FileOperation(path="../etc/passwd")


def test_an_absolute_path_is_still_rejected():
    with pytest.raises(ValidationError):
        FileOperation(path="/etc/passwd")


def test_an_empty_path_is_still_rejected():
    with pytest.raises(ValidationError):
        FileOperation(path="")


def test_an_ordinary_relative_path_is_still_accepted():
    assert FileOperation(path="notes/today.md").path == "notes/today.md"


def test_a_category_pattern_is_still_normalised_and_checked():
    assert SearchCategoriesByPathRequest(path_pattern="  Docs/API  ").path_pattern == "docs/api"

    with pytest.raises(ValidationError):
        SearchCategoriesByPathRequest(path_pattern="docs/../etc")


# --- the name is the point --------------------------------------------------


def test_the_containment_helper_name_is_unique_to_the_helper():
    """`grep "def validate_path"` must find the helper and nothing else.

    That grep is the first move when auditing path handling. Two false hits made
    it possible to read a schema validator as containment coverage it never
    provided.
    """
    import subprocess
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    # Anchored to a real definition. An unanchored search also matches this
    # file's own prose and the grep argument below, which would make the test
    # fail on its own text.
    out = subprocess.run(
        [
            "grep",
            "-rnE",
            "--include=*.py",
            r"^\s*def validate_path",
            str(repo / "autobot-backend"),
            str(repo / "autobot_shared"),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    hits = [ln for ln in out.stdout.splitlines() if ln.strip()]

    assert len(hits) == 1, (
        "`def validate_path` should match only the canonical containment helper; "
        "extra hits make a path-handling audit read schema validators as "
        "containment:\n  " + "\n  ".join(hits)
    )
    assert "path_validator.py" in hits[0], hits[0]
