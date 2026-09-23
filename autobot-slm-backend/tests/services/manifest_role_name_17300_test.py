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

#: Role directories that exist in the fixture tree. The path is now built from a
#: directory LISTING rather than from the argument (#17300), so a role has to
#: exist to be resolvable -- which is the property that makes traversal
#: impossible rather than merely filtered.
_REAL_ROLES = ("backend", "ai_stack", "vnc-desktop", "a", "role123")


@pytest.fixture
def loader(tmp_path: Path) -> ManifestLoader:
    for name in _REAL_ROLES:
        (tmp_path / name).mkdir()
    return ManifestLoader(infra_base=tmp_path)


def test_a_real_role_name_resolves_under_the_infra_base(loader, tmp_path):
    """The contrast case: the allowlist must not reject the names it exists for."""
    path = loader._manifest_path("backend")

    assert path is not None
    assert path == (tmp_path / "backend" / "manifest.yml").resolve()


@pytest.mark.parametrize("name", ["ai_stack", "vnc-desktop", "a", "role123"])
def test_ordinary_ansible_role_shapes_are_accepted(name, loader):
    assert loader._manifest_path(name) is not None


def test_a_name_that_passes_the_allowlist_but_is_not_a_directory_is_refused():
    """The listing is the real guard: a well-formed name for a role that does not
    exist resolves to nothing, rather than to a path that merely happens to be
    empty."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        assert ManifestLoader(infra_base=Path(tmp))._manifest_path("backend") is None


def test_a_role_name_with_a_trailing_newline_is_refused(loader):
    """`match()` accepted "backend\n" because `$` also matches before a final
    newline; `fullmatch()` does not. Found in review (#17300)."""
    assert loader._manifest_path("backend\n") is None


def test_a_role_directory_symlinked_out_of_the_base_is_refused(tmp_path):
    """The containment check, exercised for the first time.

    Every other rejection here is caught by the name allowlist before the
    containment check runs, so that check was untested and could have been
    deleted without a failure. A symlink passes the name check and the directory
    listing, and is caught only by `is_relative_to` after `resolve()`.
    """
    base = tmp_path / "infra"
    base.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "manifest.yml").write_text(_VALID_MANIFEST, encoding="utf-8")
    (base / "backend").symlink_to(outside, target_is_directory=True)

    assert ManifestLoader(infra_base=base)._manifest_path("backend") is None


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
