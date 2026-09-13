# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``document_uploaded``'s trigger validates against BOTH layouts (#15293).

Split out of ``document_analysis_test.py`` rather than grown in place: that
file is at the 600-line ratchet (``scripts/check_python_file_size.py``), and
this is new coverage, not a fix to anything already there.

``_resolve_path`` used to validate a received ``file_path`` against
``PROJECT_ALLOWED_ROOTS`` alone -- the code root ``project_root()`` resolves
to. ``_emit_document_uploaded`` (``api/files.py``) always fires this trigger
with a path under ``SANDBOXED_ROOT``, a subdirectory of the *data* root
(``config.path.data_path``), never the code root. In a checkout the two
coincide (``AUTOBOT_DATA_DIR`` unset, so ``data_path`` resolves under
``project_root()``), which is why the mismatch was invisible in development.
The ansible-deployed layout sets ``AUTOBOT_DATA_DIR`` to an absolute path
outside the code root on purpose (``/var/lib/autobot``, so runtime data
survives a code redeploy), and ``PROJECT_ALLOWED_ROOTS`` never contained it --
``validate_path`` rejected every real upload there, silently: the trigger
logs a WARNING and returns ``success: False``, but nothing inspects that
result, so nothing ever surfaced the rejection outside the log.
"""

import pytest

from autobot_shared.ssot_config import config as ssot_config
from skills.builtin.document_analysis import DocumentAnalysisSkill  # nosemgrep: skill-no-sibling-import


@pytest.fixture
def skill():
    return DocumentAnalysisSkill()


@pytest.mark.asyncio
async def test_a_path_under_the_data_root_validates_even_when_outside_the_code_root(skill, monkeypatch, tmp_path):
    """The exact #15293 defect, reproduced with two roots that do not overlap
    at all -- the ansible-deployed shape. This exercises the real
    ``validate_path`` containment check (resolved paths via ``os.path.realpath``
    and ``Path.relative_to``), not a string comparison against either root.

    Plain text, not a PDF: extraction itself is orthogonal to what this test
    is about (path confinement), and a PDF fixture would couple it to
    ``pypdf`` being importable.
    """
    code_root = tmp_path / "opt_autobot"
    data_root = tmp_path / "var_lib_autobot"
    code_root.mkdir()
    data_root.mkdir()

    monkeypatch.setattr("skills.builtin.document_analysis.PROJECT_ALLOWED_ROOTS", (str(code_root),))
    monkeypatch.setattr(ssot_config.path, "data_dir", str(data_root))

    path = data_root / "upload.md"
    path.write_text("real content", encoding="utf-8")
    result = await skill.execute("extract_text", {"file_path": str(path)})

    assert result["success"] is True
    assert "real content" in result["content"]


@pytest.mark.asyncio
async def test_a_path_under_the_code_root_still_validates_matching_the_checkout_layout(skill, monkeypatch, tmp_path):
    """The checkout layout: ``AUTOBOT_DATA_DIR`` is unset there, so the data
    root and the code root coincide, and a path under the code root alone
    must keep validating -- widening ``allowed_roots`` must not have
    narrowed it.
    """
    code_root = tmp_path / "checkout"
    data_root = tmp_path / "checkout" / "data"
    code_root.mkdir()
    data_root.mkdir()

    monkeypatch.setattr("skills.builtin.document_analysis.PROJECT_ALLOWED_ROOTS", (str(code_root),))
    monkeypatch.setattr(ssot_config.path, "data_dir", str(data_root))

    path = code_root / "upload.md"
    path.write_text("real content", encoding="utf-8")
    result = await skill.execute("extract_text", {"file_path": str(path)})

    assert result["success"] is True
    assert "real content" in result["content"]


@pytest.mark.asyncio
async def test_a_path_outside_both_the_code_root_and_the_data_root_is_still_rejected(skill, monkeypatch, tmp_path):
    """Adding the data root must not turn confinement into an open sandbox --
    a path outside BOTH roots stays rejected.
    """
    code_root = tmp_path / "opt_autobot"
    data_root = tmp_path / "var_lib_autobot"
    elsewhere = tmp_path / "elsewhere"
    for directory in (code_root, data_root, elsewhere):
        directory.mkdir()

    monkeypatch.setattr("skills.builtin.document_analysis.PROJECT_ALLOWED_ROOTS", (str(code_root),))
    monkeypatch.setattr(ssot_config.path, "data_dir", str(data_root))

    path = elsewhere / "upload.md"
    path.write_text("real content", encoding="utf-8")
    result = await skill.execute("extract_text", {"file_path": str(path)})

    assert result["success"] is False
    assert "Invalid file_path" in result["error"]
