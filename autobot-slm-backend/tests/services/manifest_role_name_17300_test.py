# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A role name cannot address a manifest outside the infra base (#17300).

`_manifest_path` joined `role_name` as its own path segment with no validation,
and that value arrives from a `role` query parameter and a `role_name` POST body
field. `role_name="../../../../etc"` walked out of the infra base before both
`path.exists()` and `path.open()`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from services.manifest_loader import ManifestLoader


@pytest.fixture
def loader(tmp_path: Path) -> ManifestLoader:
    return ManifestLoader(infra_base=tmp_path)


def test_a_real_role_name_resolves_under_the_infra_base(loader, tmp_path):
    """The contrast case: the allowlist must not reject the names it exists for."""
    path = loader._manifest_path("backend")

    assert path is not None
    assert path == (tmp_path / "backend" / "manifest.yml").resolve()


@pytest.mark.parametrize("name", ["ai_stack", "vnc-desktop", "a", "role123"])
def test_ordinary_ansible_role_shapes_are_accepted(name, loader):
    assert loader._manifest_path(name) is not None


@pytest.mark.parametrize(
    "name",
    [
        "../../../../etc",
        "..",
        "../backend",
        "/etc",
        "backend/../../etc",
        "back end",
        "Backend",
        "",
        "." * 5,
        "a" * 65,
    ],
    ids=["traversal", "dotdot", "relative", "absolute", "embedded", "space", "uppercase", "empty", "dots", "toolong"],
)
def test_a_name_that_is_not_a_role_is_refused(name, loader):
    assert loader._manifest_path(name) is None


#: A manifest that PASSES RoleManifest validation. The first version of this
#: fixture said `name: pwned` and was a false negative: `_load_from_disk`
#: swallows a validation error in its generic `except Exception` and returns
#: None, so the test passed with the guard removed — it was asserting that
#: pydantic rejects a malformed file, not that traversal was blocked. Caught by
#: reverting the guard and watching the test stay green.
_VALID_MANIFEST = """role: autobot-pwned
description: a manifest planted outside the infra base
deploy:
  source: pwned/
  destination: /opt/autobot/pwned/
"""


def test_a_refused_name_never_reaches_the_filesystem(loader, tmp_path):
    """`_load_from_disk` returns None because the GUARD fired, not because the file was bad.

    The planted manifest is schema-valid on purpose: with the guard removed this
    traversal loads it and the test fails. That is the only way the assertion
    means what it says.
    """
    outside = tmp_path.parent / "outside"
    outside.mkdir(exist_ok=True)
    (outside / "manifest.yml").write_text(_VALID_MANIFEST, encoding="utf-8")

    assert loader._load_from_disk(f"../{outside.name}") is None


def test_the_planted_manifest_really_is_loadable(loader, tmp_path):
    """The control. Without it, _VALID_MANIFEST could drift back to being invalid
    and silently restore the false negative the test above exists to avoid."""
    inside = tmp_path / "pwned"
    inside.mkdir()
    (inside / "manifest.yml").write_text(_VALID_MANIFEST, encoding="utf-8")

    assert loader._load_from_disk("pwned") is not None, "_VALID_MANIFEST no longer validates"
