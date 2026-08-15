# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An optional extra must not be a hard dependency of another component (#14279).

`spacy` is opt-in for the backend, behind `_spacy_available()`, and declared in
`autobot-backend/requirements-nlp.txt`. Its guard's docstring says why: spaCy's
build deps lack py3.14 wheels (#9825), so entity extraction falls back to the LLM
path when it is absent.

It was also listed as a hard requirement of the AI stack, which nothing there
imports — so provisioning failed on exactly the incompatibility the backend had
designed around: no stable spacy supports 3.14, pip fell through to a
`4.0.0.dev3` sdist, and the build died on the node.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_NLP_EXTRA = _REPO_ROOT / "autobot-backend" / "requirements-nlp.txt"
_AI_STACK = (
    _REPO_ROOT / "autobot-infrastructure" / "shared" / "docker" / "ai-stack" / "requirements-ai.txt"
)
_AI_STACK_SRC = _AI_STACK.parent

_REQ = re.compile(r"^\s*([A-Za-z0-9_.\-]+)\s*(?:[<>=!~\[].*)?$")


def _declared(path: Path) -> set[str]:
    found = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#")[0].strip()
        if not line or line.startswith("-"):
            continue
        match = _REQ.match(line)
        if match:
            found.add(match.group(1).lower().replace("_", "-"))
    return found


def test_both_requirement_files_were_read():
    """Empty sets would make the rule below vacuously true."""
    assert len(_declared(_AI_STACK)) >= 10
    assert len(_declared(_NLP_EXTRA)) >= 1


def test_no_optional_nlp_extra_is_a_hard_ai_stack_dependency():
    """The rule, not just the one package.

    `requirements-nlp.txt` exists so spaCy and friends are installed
    deliberately. Anything in it that also appears as a hard requirement
    elsewhere defeats that — the opt-in becomes mandatory, and its
    platform constraints become everyone's.
    """
    overlap = sorted(_declared(_NLP_EXTRA) & _declared(_AI_STACK))

    assert overlap == [], (
        f"optional NLP extras declared as hard AI-stack deps: {overlap}. "
        "They are opt-in for a reason — see _spacy_available() and #9825."
    )


def test_the_ai_stack_does_not_import_what_it_no_longer_declares():
    """If something under the AI stack actually imported spacy, removing the
    requirement would be wrong — so this pins the premise rather than assuming
    it stays true."""
    sources = "\n".join(
        path.read_text(encoding="utf-8") for path in _AI_STACK_SRC.glob("*.py")
    )

    assert "import spacy" not in sources
    assert "from spacy" not in sources


def test_the_backend_still_owns_the_capability():
    """Removing the mis-declaration must not remove the feature."""
    assert "spacy" in _declared(_NLP_EXTRA)

    extractor = (
        _REPO_ROOT
        / "autobot-backend"
        / "knowledge"
        / "pipeline"
        / "cognifiers"
        / "entity_extractor.py"
    ).read_text(encoding="utf-8")

    assert "_spacy_available" in extractor
    assert "import spacy" in extractor


@pytest.mark.parametrize("path", [_AI_STACK, _NLP_EXTRA])
def test_no_requirement_file_pins_a_pre_release(path):
    """A `.devN` / `aN` / `bN` / `rcN` pin would put a pre-release into a
    production install deliberately. pip reached one here by fallback; nothing
    should reach one on purpose."""
    offenders = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if re.search(r"==\s*[0-9][^\s#]*(dev|a|b|rc)[0-9]", line.split("#")[0])
    ]

    assert offenders == [], offenders
