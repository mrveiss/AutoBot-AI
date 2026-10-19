# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Every upload route applies the one strict filename policy (#18704).

Before, ``conversation_files.is_safe_file`` had no path-component check, so a
conversation upload named ``a/b.txt`` passed while the general file API
refused it, and its deny-list lacked ``httpd.conf`` / ``nginx.conf``.
"""

import pytest

from api import conversation_files, files
from security import upload_filename_policy

VALIDATORS = [conversation_files.is_safe_file, files.is_safe_file]
IDS = ["conversation_files", "files"]


def test_both_routes_use_the_one_policy():
    assert conversation_files.is_safe_file is upload_filename_policy.is_safe_file
    assert files.is_safe_file is upload_filename_policy.is_safe_file
    assert conversation_files.ALLOWED_EXTENSIONS is files.ALLOWED_EXTENSIONS


@pytest.mark.parametrize("validator", VALIDATORS, ids=IDS)
@pytest.mark.parametrize("name", ["a/b.txt", "../x.txt", "/etc/passwd.txt", "..\\x.txt", "x\\y.txt", "dir/../notes.md"])
def test_a_name_with_a_path_component_is_refused(validator, name):
    assert validator(name) is False


@pytest.mark.parametrize("validator", VALIDATORS, ids=IDS)
@pytest.mark.parametrize("name", ["httpd.conf", "nginx.conf", ".env", "web.config"])
def test_the_extended_deny_list_applies_to_both(validator, name):
    assert validator(name) is False


@pytest.mark.parametrize("validator", VALIDATORS, ids=IDS)
@pytest.mark.parametrize("name", ["report.xls", "report.xlsx", "notes.odt", "slides.pptx", "app.conf", "a.pdf"])
def test_the_reconciled_allow_list_accepts_both_routes_formats(validator, name):
    assert validator(name) is True


@pytest.mark.parametrize("validator", VALIDATORS, ids=IDS)
@pytest.mark.parametrize(
    "name",
    [
        "report\u202efdp.sh",  # BIDI override: displays as "reportsh.pdf"
        "a\u200bb.txt",  # zero-width space (Cf)
        "a\x7f.txt",  # DEL
        "a\x85.txt",  # C1 next-line
        "a\uff0fb.txt",  # fullwidth solidus, NFKC -> "/"
        "\uff0e\uff0e\uff0fx.txt",  # fullwidth "../"
        "a\uff3cb.txt",  # fullwidth reverse solidus, NFKC -> "\"
        "a\u2215b.txt",  # division slash, NOT folded by NFKC
        "a\u2044b.txt",  # fraction slash
        ".",
        "..",
    ],
)
def test_deceptive_and_lookalike_names_are_refused(validator, name):
    assert validator(name) is False


@pytest.mark.parametrize("name", ["résumé.pdf", "отчёт.docx", "報告.txt"])
def test_ordinary_unicode_names_still_pass(name):
    assert upload_filename_policy.is_safe_file(name) is True


def test_the_lists_are_frozen_and_disjoint():
    assert isinstance(upload_filename_policy.ALLOWED_EXTENSIONS, frozenset)
    assert not upload_filename_policy.ALLOWED_EXTENSIONS & upload_filename_policy._DANGEROUS_EXTENSIONS


def test_a_deny_listed_type_wins_over_the_allow_list(monkeypatch):
    widened = upload_filename_policy.ALLOWED_EXTENSIONS | {".exe"}
    monkeypatch.setattr(upload_filename_policy, "ALLOWED_EXTENSIONS", widened)
    assert upload_filename_policy.is_safe_file("tool.exe") is False


def test_the_conversation_write_path_is_contained_in_the_session_dir(tmp_path, monkeypatch):
    from conversation_file_manager import ConversationFileManager

    manager = ConversationFileManager(storage_dir=tmp_path / "files", db_path=tmp_path / "files.db")
    monkeypatch.setattr(manager, "_generate_stored_filename", lambda name, digest: "../../escape.txt")
    with pytest.raises(ValueError, match="escapes session directory"):
        manager._prepare_file_info("session-1", b"data", "ok.txt")
    monkeypatch.setattr(manager, "_generate_stored_filename", lambda name, digest: "abc_ok.txt")
    info = manager._prepare_file_info("session-1", b"data", "ok.txt")
    assert info.file_path.parent == manager.get_session_dir("session-1").resolve()
