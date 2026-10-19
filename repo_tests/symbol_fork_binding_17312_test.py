# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Detector matcher contrast pairs (#17312): shared-subclass bindings and conftest.

Two owner-approved matcher changes, each pinned with a pair so neither can
widen into "everything is exempt": a subclass of the SAME-NAMED shared class is
a binding (a same-name class that is not, is still a fork), and ``conftest.py``
is a test file (a non-test file defining the same name is still a fork).
"""

from __future__ import annotations

from pathlib import Path

from autobot_shared.symbol_forks import fork_find_clusters, fork_is_test_file

_SHARED = "class Widget:\n    pass\n"


def _scan(tmp_path: Path, files: dict[str, str]):
    for rel, text in files.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return fork_find_clusters([Path(rel) for rel in files], tmp_path).clusters


def test_a_subclass_of_the_shared_same_name_class_is_not_a_fork(tmp_path) -> None:
    clusters = _scan(
        tmp_path,
        {
            "autobot_shared/widget.py": _SHARED,
            "svc/widget.py": "from autobot_shared.widget import Widget as SharedWidget\n\n\nclass Widget(SharedWidget):\n    extra = 1\n",
        },
    )
    assert "Widget" not in clusters


def test_a_module_attribute_base_from_shared_is_also_a_binding(tmp_path) -> None:
    clusters = _scan(
        tmp_path,
        {
            "autobot_shared/widget.py": _SHARED,
            "svc/widget.py": "from autobot_shared import widget as shared_widget\n\n\nclass Widget(shared_widget.Widget):\n    pass\n",
        },
    )
    assert "Widget" not in clusters


def test_a_same_name_class_that_does_not_subclass_it_is_still_a_fork(tmp_path) -> None:
    clusters = _scan(
        tmp_path,
        {
            "autobot_shared/widget.py": _SHARED,
            "svc/widget.py": "class Widget:\n    extra = 1\n",
        },
    )
    assert "Widget" in clusters


def test_a_same_name_base_from_outside_shared_is_still_a_fork(tmp_path) -> None:
    clusters = _scan(
        tmp_path,
        {
            "autobot_shared/widget.py": _SHARED,
            "other/widget.py": "class Widget:\n    pass\n",
            "svc/widget.py": "from other.widget import Widget as OtherWidget\n\n\nclass Widget(OtherWidget):\n    pass\n",
        },
    )
    assert "Widget" in clusters


def test_a_differently_named_shared_base_is_still_a_fork(tmp_path) -> None:
    clusters = _scan(
        tmp_path,
        {
            "autobot_shared/widget.py": _SHARED,
            "autobot_shared/base.py": "class Base:\n    pass\n",
            "svc/widget.py": "from autobot_shared.base import Base\n\n\nclass Widget(Base):\n    pass\n",
        },
    )
    assert "Widget" in clusters


def test_conftest_is_a_test_file_but_a_look_alike_is_not() -> None:
    assert fork_is_test_file(Path("autobot-backend/conftest.py"))
    assert not fork_is_test_file(Path("autobot-backend/conftest_helpers.py"))
    assert not fork_is_test_file(Path("autobot-backend/not_conftest.py"))


def test_conftest_duplicates_are_not_counted_but_a_non_test_duplicate_is(tmp_path) -> None:
    hook = "def pytest_configure(config):\n    pass\n"
    clusters = _scan(
        tmp_path,
        {
            "a/conftest.py": hook,
            "b/conftest.py": hook,
            "a/helpers.py": "def shared_name():\n    pass\n",
            "b/helpers.py": "def shared_name():\n    pass\n",
        },
    )
    assert "pytest_configure" not in clusters
    assert "shared_name" in clusters
