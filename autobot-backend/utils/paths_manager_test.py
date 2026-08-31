# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``PathsManager`` must reject a non-str config value, not turn it into a
directory tree (#14217).

``get_data_path``/``get_log_path`` handed whatever ``unified_config_manager``
returned straight to ``Path()``. When ``unified_config_manager`` is an
unconfigured ``MagicMock`` (a broadly-mocked test double), every ``.get()``
call returns another ``MagicMock`` rather than raising or returning the
requested default — three levels deep for the exact evidence in the issue:
``unified_config_manager.get().get().get()``. ``Path(MagicMock())`` never
raises (a ``MagicMock``'s default ``__fspath__`` embeds ``/`` separators),
so the mock's own repr was silently promoted into a real, creatable,
nested directory tree the first time something called ``.mkdir()`` on it.
"""

from unittest.mock import MagicMock

import pytest

import utils.paths_manager as paths_manager_module
from autobot_shared.ssot_config import config as ssot_config
from utils.paths_manager import PathsManager


@pytest.fixture(autouse=True)
def _clear_paths_cache():
    """PathsManager caches config for 60s in a class attribute — isolate."""
    PathsManager.clear_cache()
    yield
    PathsManager.clear_cache()


class TestGetDataPathRejectsNonStrConfig:
    """Drive the real entry point with an object, not a crafted string."""

    def test_unconfigured_magicmock_manager_raises(self, tmp_path, monkeypatch):
        """The real reproduction: an unconfigured mock config manager."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            paths_manager_module,
            "unified_config_manager",
            MagicMock(name="mock.unified_config_manager"),
        )

        with pytest.raises(TypeError):
            PathsManager.get_data_path("file_manager_root")

        assert list(tmp_path.rglob("*")) == [], "nothing must be created on disk"

    def test_configured_manager_with_dict_value_still_works(self, tmp_path, monkeypatch):
        """Unchanged behaviour: a real config dict resolves normally."""
        monkeypatch.setattr(
            paths_manager_module,
            "unified_config_manager",
            MagicMock(**{"get.return_value": {"data": {"directory": str(tmp_path)}}}),
        )

        result = PathsManager.get_data_path("file_manager_root")

        assert result == tmp_path / "file_manager_root"

    def test_non_str_value_for_named_data_entry_raises(self, tmp_path, monkeypatch):
        """A specifically-configured (not just defaulted) entry is checked too."""
        monkeypatch.setattr(
            paths_manager_module,
            "unified_config_manager",
            MagicMock(**{"get.return_value": {"data": {"file_manager_root": object()}}}),
        )

        with pytest.raises(TypeError):
            PathsManager.get_data_path("file_manager_root")


class TestGetLogPathRejectsNonStrConfig:
    def test_unconfigured_magicmock_manager_raises(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            paths_manager_module,
            "unified_config_manager",
            MagicMock(name="mock.unified_config_manager"),
        )

        with pytest.raises(TypeError):
            PathsManager.get_log_path("backend")

        assert list(tmp_path.rglob("*")) == [], "nothing must be created on disk"

    def test_configured_manager_with_dict_value_still_works(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            paths_manager_module,
            "unified_config_manager",
            MagicMock(**{"get.return_value": {"logs": {"directory": str(tmp_path)}}}),
        )

        result = PathsManager.get_log_path("backend")

        assert result == tmp_path / "backend.log"


class TestFallbackMethodsDegradeGracefullyInsteadOfBuildingATree:
    """get_chat_data_dir() etc. already had a try/except safety net — but
    Path(mock) never raised, so the net never caught anything. It must now.
    """

    def test_get_chat_data_dir_with_non_str_backend_value_falls_back(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            paths_manager_module,
            "unified_config_manager",
            MagicMock(**{"get.return_value": {"chat_data_dir": MagicMock(name="mock.chat_data_dir")}}),
        )

        result = PathsManager.get_chat_data_dir()

        # #14113: the ultimate fallback is absolute and SSOT-derived. It used to
        # be Path("data/chats") -- relative, so `monkeypatch.chdir(tmp_path)`
        # above silently changed the answer. Asserting `is_absolute()` and
        # independence from CWD is the property that matters; asserting the exact
        # literal is what let the CWD dependency read as correct for so long.
        assert result.is_absolute(), f"fallback must not be CWD-relative, got {result}"
        assert result == ssot_config.path.data_path / "chats"
        assert tmp_path not in result.parents, "the fallback must not follow the process CWD"
        assert list(tmp_path.rglob("*")) == [], "nothing must be created on disk"


class TestResolversAgreeAndHonourTheDataDirOverride:
    """#14113: the legacy resolver and the SSOT no longer answer differently.

    Before this, ``get_data_path`` read a ``paths:`` key that no ``config.yaml``
    the backend's ``ConfigManager`` loads has ever defined, so every call took a
    fallback of ``Path("data") / name`` — relative, and therefore resolved by the
    OS against whatever working directory the process was launched with. Setting
    ``AUTOBOT_DATA_DIR`` moved ``ssot_config.path.data_path`` and moved nothing
    here, which is how the secrets store came to live somewhere no operator
    setting that variable would look.
    """

    @staticmethod
    def _with_data_dir(monkeypatch, target) -> None:
        """Point the SSOT at *target* and clear both layers of caching."""
        from autobot_shared import ssot_config as ssot_config_module

        monkeypatch.setattr(
            paths_manager_module,
            "unified_config_manager",
            MagicMock(**{"get.return_value": {}}),
        )
        monkeypatch.setenv("AUTOBOT_DATA_DIR", str(target))
        monkeypatch.setenv("AUTOBOT_LOG_DIR", str(target / "logs"))
        ssot_config_module.reload_config()
        monkeypatch.setattr(paths_manager_module, "ssot_config", ssot_config_module.config)
        PathsManager.clear_cache()

    def test_data_dir_override_moves_the_resolved_path(self, tmp_path, monkeypatch):
        target = tmp_path / "relocated"
        self._with_data_dir(monkeypatch, target)

        assert PathsManager.get_data_directory() == target
        assert PathsManager.get_data_path("secrets.db") == target / "secrets.db"

    def test_both_resolvers_agree(self, tmp_path, monkeypatch):
        target = tmp_path / "relocated"
        self._with_data_dir(monkeypatch, target)

        assert PathsManager.get_data_directory() == paths_manager_module.ssot_config.path.data_path

    def test_no_accessor_returns_a_cwd_relative_path(self, tmp_path, monkeypatch):
        """The property that actually failed: every answer must be absolute.

        Asserted across the whole accessor surface rather than the one method
        the bug was found in — ``get_static_directory`` and
        ``get_config_directory`` carried the identical relative literal and had
        no caller to notice.
        """
        target = tmp_path / "relocated"
        self._with_data_dir(monkeypatch, target)
        monkeypatch.chdir(tmp_path)

        accessors = {
            "get_data_directory": PathsManager.get_data_directory(),
            "get_logs_directory": PathsManager.get_logs_directory(),
            "get_static_directory": PathsManager.get_static_directory(),
            "get_config_directory": PathsManager.get_config_directory(),
            "get_data_path": PathsManager.get_data_path("x"),
            "get_log_path": PathsManager.get_log_path("x"),
        }

        # Population floor asserted BEFORE the offender check: an accessor dict
        # that silently shrank would make the emptiness below pass for free.
        assert len(accessors) == 6, "the accessor sweep lost a method"
        relative = {name: str(p) for name, p in accessors.items() if not p.is_absolute()}
        assert relative == {}, f"CWD-relative path(s) returned: {relative}"
