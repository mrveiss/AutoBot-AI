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

        assert result == paths_manager_module.Path("data/chats")
        assert list(tmp_path.rglob("*")) == [], "nothing must be created on disk"
