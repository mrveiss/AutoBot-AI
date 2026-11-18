# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""get_session_dir refuses a session ID that is not one safe path segment (#18760).

The ID is joined onto storage/sessions/ and mkdir'd; validate_session_path only checks
the FILE against that directory, so ``..`` used to make storage/ itself the "session".
"""

import pytest

from conversation_file_manager import ConversationFileManager


def _manager(tmp_path):
    mgr = object.__new__(ConversationFileManager)  # no DB/Redis: only storage_dir is read
    mgr.storage_dir = tmp_path
    return mgr


@pytest.mark.parametrize("bad", ["..", "../x", "a/b", "/etc", "a\x00b", ""])
def test_a_session_id_with_a_path_component_is_refused_before_mkdir(tmp_path, bad) -> None:
    with pytest.raises(ValueError):
        _manager(tmp_path).get_session_dir(bad)
    assert not (tmp_path / "sessions").exists(), "nothing may be created for a refused ID"


@pytest.mark.parametrize("good", ["a1b2c3d4-e5f6-7890-abcd-ef1234567890", "test_session_123"])
def test_a_normal_session_id_gets_its_directory_inside_sessions(tmp_path, good) -> None:
    path = _manager(tmp_path).get_session_dir(good)
    assert path == tmp_path / "sessions" / good and path.is_dir()


def test_validate_session_path_inherits_the_refusal(tmp_path) -> None:
    with pytest.raises(ValueError):
        _manager(tmp_path).validate_session_path("..", "file.txt")
