# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Only the rebuild-and-cutover flow switches the embedding model (#19379, #19383 review).

``set_embedding_model_override`` changes the model every query is embedded with. Called anywhere
but after a complete rebuild, it strands the stored vectors: queries in the new model against
vectors from the old one answer nonsense or fail on dimension. ``knowledge/embedding_switch.py``
calls it only after a zero-failure, count-verified build; this pins that it is the only caller.
"""

from __future__ import annotations

import re

from repo_tests._paths import repo_root

from tools.lint._scan_helpers import tracked_paths

#: The defining module and the one sanctioned caller.
_ALLOWED = {"autobot_shared/embedding_model.py", "autobot-backend/knowledge/embedding_switch.py"}
#: Any use of the name -- a call, or the function handed to ``asyncio.to_thread`` -- other than
#: its definition, an import line or a comment.
_REF = re.compile(r"\bset_embedding_model_override\b")
_NOT_A_USE = re.compile(r"^\s*(#|def |from |import )")


def _uses(source: str) -> bool:
    return any(_REF.search(line) and not _NOT_A_USE.match(line) for line in source.splitlines())


def _is_test(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return name.endswith("_test.py") or name.startswith("test_") or "/tests/" in path


def _callers(paths) -> list[str]:
    return [p for p in paths if p not in _ALLOWED and not _is_test(p) and _uses(_read(p))]


def _read(path: str) -> str:
    return (repo_root() / path).read_text(encoding="utf-8", errors="replace")


def test_the_switch_is_the_only_production_caller() -> None:
    paths = tracked_paths(repo_root(), "*.py")
    assert len(paths) > 1000, f"only {len(paths)} Python files enumerated"
    assert not _callers(paths), "set_embedding_model_override has a second caller; only the switch may cut over"


def test_the_sanctioned_caller_still_calls_it() -> None:
    assert _uses(_read("autobot-backend/knowledge/embedding_switch.py"))


def test_contrast_the_detector() -> None:
    assert _uses("space = set_embedding_model_override(model, collection)")
    assert _uses("space = await asyncio.to_thread(set_embedding_model_override, model, collection)")
    assert not _uses("from autobot_shared.embedding_model import set_embedding_model_override")
    assert not _uses("# set_embedding_model_override is called by the switch")
    assert _is_test("autobot_shared/embedding_model_override_19377_test.py")
    assert not _is_test("autobot-backend/api/embeddings.py")
