# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A failed playbook must report its failure, not its banner (#14298).

Every caller reporting a playbook failure did ``output[:500]``. Ansible's first
lines are its preamble, so what reached the operator was a
``DEFAULT_GATHER_SUBSET`` deprecation warning — while the actual cause sat at
the end of the output, uncut.

That is worse than an empty message. It reads as a diagnosis and points at
something unrelated, so the reader goes and looks at gather_facts.

The fixture below is the real output that misled a live diagnosis: a code-sync
node failure whose cause was a pip resolution conflict.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

_BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _load():
    """Load ansible_utils standalone — the package pulls in heavy services."""
    saved = {n: sys.modules.get(n) for n in ("services",)}
    try:
        if "services" not in sys.modules:
            sys.modules["services"] = MagicMock()
        spec = importlib.util.spec_from_file_location("_au_14298", _BACKEND_ROOT / "services" / "ansible_utils.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        for name, original in saved.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


_au = _load()

# The preamble is long enough on its own to fill a 500-char head slice.
_PREAMBLE = (
    "[DEPRECATION WARNING]: DEFAULT_GATHER_SUBSET option, the module_defaults\n"
    "keyword is a more generic version and can apply to all calls to the\n"
    "M(ansible.builtin.gather_facts) or M(ansible.builtin.setup) actions, use\n"
    "module_defaults instead. This feature will be removed from ansible-core in\n"
    "version 2.18. Deprecation warnings can be disabled by setting\n"
    "deprecation_warnings=False in ansible.cfg.\n"
)

_WITH_FAILED_TASK = (
    _PREAMBLE + "\n"
    "PLAY [Sync role] ***************************************************************\n"
    "\n"
    "TASK [Install AI Python packages from requirements-ai.txt] *********************\n"
    'fatal: [ai-node]: FAILED! => {"changed": true, "cmd": "venv/bin/pip install -r requirements-ai.txt", '
    '"msg": "ERROR: Cannot install tokenizers because these package versions have conflicting dependencies"}\n'
    "\n"
    "PLAY RECAP *********************************************************************\n"
    "ai-node                    : ok=4    changed=1    unreachable=0    failed=1\n"
)

# A run that died before any task — nothing for the parser to find.
_NO_TASK = _PREAMBLE + "\n" + "x" * 800 + "\nERROR! the playbook could not be found\n"


def test_the_summary_names_the_task_and_the_message():
    result = _au.summarize_playbook_failure(_WITH_FAILED_TASK)

    assert "Install AI Python packages" in result
    assert "conflicting dependencies" in result
    assert "DEPRECATION" not in result


def test_a_head_slice_of_the_same_output_would_have_told_you_nothing():
    """The regression, stated as a comparison rather than as prose.

    This is what every call site did. Keeping it executable means the claim in
    the docstring above is checked rather than asserted.
    """
    head = _WITH_FAILED_TASK[:500]

    assert "DEPRECATION WARNING" in head
    assert "conflicting dependencies" not in head
    assert "fatal:" not in head


def test_unparseable_output_falls_back_to_the_tail_not_the_head():
    result = _au.summarize_playbook_failure(_NO_TASK)

    assert "the playbook could not be found" in result
    assert "DEPRECATION WARNING" not in result


def test_the_fallback_is_marked_as_truncated():
    result = _au.summarize_playbook_failure(_NO_TASK)

    assert result.startswith("..."), "a tail slice must not read as the whole output"


def test_short_output_is_returned_whole():
    result = _au.summarize_playbook_failure("ERROR! short and complete")

    assert result == "ERROR! short and complete"
    assert not result.startswith("...")


def test_empty_output_says_so_rather_than_returning_nothing():
    """An empty message renders as no error at all in every surface it reaches."""
    assert _au.summarize_playbook_failure("") == "playbook failed with no output"
    assert _au.summarize_playbook_failure(None) == "playbook failed with no output"


def test_the_tail_size_is_configurable_not_hardcoded():
    result = _au.summarize_playbook_failure(_NO_TASK, tail_chars=40)

    assert len(result) == 43  # 40 + the "..." marker
    assert "the playbook could not be found" in result


def test_the_default_comes_from_the_environment_backed_constant():
    assert _au.PLAYBOOK_FAILURE_TAIL_CHARS == 500
