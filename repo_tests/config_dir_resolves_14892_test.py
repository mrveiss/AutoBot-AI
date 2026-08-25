# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#14892: ``PATH.CONFIG_DIR`` must name a directory that is actually there.

The constant read ``PROJECT_ROOT / "infrastructure" / "shared" / "config"`` for
its whole life. No project root — checkout or deployed install — has ever had an
``infrastructure/`` directory; the real one is ``autobot-infrastructure/``. So
every consumer resolved a path that could not exist, and because a missing
config is indistinguishable from a loaded one in most of them, nothing said so.

These assertions are the ones the original value would have failed on the day it
was written.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from autobot_shared.paths import project_root
from autobot_shared.ssot_constants import PATH

#: Files a consumer reaches through ``CONFIG_DIR`` that are present in a checkout.
#: Named individually so a rename fails here rather than silently shrinking the
#: sweep to nothing.
TRACKED_CONFIG_FILES = (
    "error_messages.yaml",
    "config.yaml",
    "security/compliance.yaml",
    "security/domain_security.yaml",
    "security/threat_detection.yaml",
)


class TestConfigDirIsReal:
    def test_config_dir_exists_in_a_checkout(self) -> None:
        assert PATH.CONFIG_DIR.is_dir(), (
            f"PATH.CONFIG_DIR resolves to {PATH.CONFIG_DIR}, which is not a directory. "
            "Nine consumers read config through this constant."
        )

    def test_config_dir_does_not_name_the_nonexistent_infrastructure_spelling(self) -> None:
        """The specific wrong value, asserted by name so it cannot come back."""
        assert "autobot-infrastructure" in PATH.CONFIG_DIR.parts, "the real dir is under autobot-infrastructure"
        assert "infrastructure" not in PATH.CONFIG_DIR.parts, "the bare `infrastructure` spelling is the #14892 bug"
        assert not (project_root() / "infrastructure").exists(), (
            "an `infrastructure/` directory now exists at the project root, so this "
            "test's premise changed — re-check which spelling CONFIG_DIR should use."
        )
        assert PATH.CONFIG_DIR == project_root() / "autobot-infrastructure" / "shared" / "config"

    def test_config_dir_derives_from_the_canonical_project_root(self) -> None:
        """#13149: not a second open-coded ``Path(__file__).parent.parent``.

        Asserted through ``project_root()`` so that running from a worktree —
        which is how all work here happens — resolves inside the worktree.
        """
        assert PATH.PROJECT_ROOT == project_root()
        assert PATH.CONFIG_DIR.is_relative_to(project_root())

    @pytest.mark.parametrize("relative", TRACKED_CONFIG_FILES)
    def test_each_tracked_config_file_is_reachable(self, relative: str) -> None:
        resolved = PATH.get_config_path(*relative.split("/"))
        assert resolved.is_file(), f"{relative} is not reachable through PATH.get_config_path: {resolved}"

    def test_the_tracked_file_population_is_not_empty(self) -> None:
        """Floor asserted separately from the parametrised sweep above.

        An empty ``TRACKED_CONFIG_FILES`` would collect zero test cases and the
        parametrised assertion would pass by never running — the failure mode
        that let a two-pathspec guard here pass for years on one empty half.
        """
        assert len(TRACKED_CONFIG_FILES) >= 5
        assert len(set(TRACKED_CONFIG_FILES)) == len(TRACKED_CONFIG_FILES), "duplicate entries inflate the floor"


class TestAMissIsDistinguishable:
    """#14892 AC3: a config that is absent must not read as one that was loaded."""

    @pytest.fixture(autouse=True)
    def _require_enterprise_package(self):
        """`security.enterprise.__init__` eagerly imports every manager, one of
        which needs an optional dependency. Skip rather than fail where it is
        absent; CI installs the full requirements set."""
        pytest.importorskip("cachetools")

    def test_missing_file_reports_builtin_defaults_and_writes_nothing(self, tmp_path: Path) -> None:
        from security.enterprise.config_loading import SOURCE_BUILTIN_DEFAULTS, load_security_config

        target = tmp_path / "security" / "absent.yaml"

        loaded = load_security_config(target, lambda: {"policy": "built-in"}, "test")

        assert loaded.source == SOURCE_BUILTIN_DEFAULTS
        assert loaded.loaded_from_file is False
        assert loaded.searched_path == target
        assert loaded.values == {"policy": "built-in"}
        # The decoy write is the half that made this permanent: the old miss
        # branch mkdir'd and dumped defaults into the path it had just failed to
        # read, so the next boot loaded them back and reported success.
        assert list(tmp_path.rglob("*")) == [], "a miss must not create anything on disk"

    def test_present_file_reports_the_file(self, tmp_path: Path) -> None:
        from security.enterprise.config_loading import SOURCE_FILE, load_security_config

        target = tmp_path / "present.yaml"
        target.write_text("policy: from-file\n", encoding="utf-8")

        loaded = load_security_config(target, lambda: {"policy": "built-in"}, "test")

        assert loaded.source == SOURCE_FILE
        assert loaded.loaded_from_file is True
        assert loaded.values == {"policy": "from-file"}

    def test_an_empty_file_is_not_treated_as_a_loaded_config(self, tmp_path: Path) -> None:
        """``yaml.safe_load`` returns None for an empty file — an empty policy."""
        from security.enterprise.config_loading import SOURCE_BUILTIN_DEFAULTS, load_security_config

        target = tmp_path / "empty.yaml"
        target.write_text("# only a comment\n", encoding="utf-8")

        loaded = load_security_config(target, lambda: {"policy": "built-in"}, "test")

        assert loaded.source == SOURCE_BUILTIN_DEFAULTS
        assert loaded.values == {"policy": "built-in"}
