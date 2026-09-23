# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
The typed-decision seam's exclusion list, as an assertion (#17308).

#17308 audited eight call sites onto the seam and *rejected* five kinds of
decision, recording each with its reason so a later reader would not
re-propose them. A recorded reason in a docstring is a comment; this file is
the version a commit has to get past.

The rule each module below is held to: it must not import
``llm_shared.decisions``. That is a deliberately blunt check -- it catches the
edit that puts a model call where a deterministic local one already works,
which is the mistake the audit was written to prevent, and it cannot be
satisfied by a comment.

If one of these genuinely needs to change, the honest route is to change this
file in the same commit with the argument in its message, not to add an
exemption in the excluded module.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

#: The repo root, derived from this file rather than from ``project_root()``:
#: that helper consults ``AUTOBOT_PROJECT_ROOT`` and the configured deployment
#: first, so under CI it can resolve somewhere other than the checkout being
#: tested -- and a guard that reads the wrong tree reports "nothing found"
#: when it means "did not look".
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

#: Each entry: (path relative to the repo root, why the seam must not be there).
EXCLUDED: tuple[tuple[str, str], ...] = (
    (
        "autobot-backend/llm_shared/tiered_routing/complexity_router.py",
        "tier routing is already deterministic and local -- there is no LLM cost to displace",
    ),
    (
        "autobot-backend/llm_shared/tiered_routing/complexity_scorer.py",
        "six weighted factors, computed locally in microseconds",
    ),
    (
        "autobot-backend/intent_classifier.py",
        "fast-path classifier, already sub-10ms and local",
    ),
    (
        "autobot-backend/workflow_classifier.py",
        "fast-path classifier, already sub-10ms and local",
    ),
    (
        "autobot-backend/agent_tier_classifier.py",
        "fast-path classifier, already sub-10ms and local",
    ),
    (
        "autobot-backend/services/knowledge/intent_detector.py",
        "fast-path classifier, already sub-10ms and local",
    ),
    (
        "autobot-backend/advanced_rag_optimizer.py",
        "reranking is a local cross-encoder, not an LLM decision",
    ),
    (
        "autobot-backend/security/prompt_injection_detector.py",
        "injection detection is deterministic regex; a steerable model is the wrong direction",
    ),
    (
        "autobot_shared/pre_action_verifier_guard.py",
        "the security gate: a cheaper, injection-steerable classifier must never decide it",
    ),
)

_SEAM_MODULE = "llm_shared.decisions"


def _imports(path: pathlib.Path) -> set[str]:
    """Return every module name *path* imports, absolute forms only."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


@pytest.mark.parametrize(("relative_path", "reason"), EXCLUDED, ids=[entry[0] for entry in EXCLUDED])
def test_excluded_module_does_not_use_the_decision_seam(relative_path: str, reason: str) -> None:
    path = _REPO_ROOT / relative_path
    # A moved or renamed file is a failure, not a skip: the exclusion would
    # otherwise silently stop being checked, which is how a guard reports
    # "nothing found" when it means "did not look".
    assert path.is_file(), f"{relative_path} is gone -- update the exclusion list deliberately"

    assert not any(
        name == _SEAM_MODULE or name.startswith(f"{_SEAM_MODULE}.") for name in _imports(path)
    ), f"{relative_path} must not use the decision seam: {reason}"


def test_the_repo_root_resolves_to_this_checkout() -> None:
    """A positive control: the derived root really is the tree under test."""
    assert (_REPO_ROOT / "autobot_shared").is_dir()
    assert (_REPO_ROOT / "autobot-backend" / "llm_shared" / "decisions.py").is_file()


def test_the_exclusion_list_covers_every_audited_category() -> None:
    """The five rejected categories from #17308 each have at least one entry."""
    joined = " ".join(reason for _path, reason in EXCLUDED)

    for category in ("routing", "classifier", "cross-encoder", "regex", "security gate"):
        assert category in joined, f"exclusion list lost the {category} category"
