# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The duplicate analyser generates no second copy of the command utilities (#18093, #18124).

It used to embed a 190-line template of `utils/command_utils.py` as a string constant
and write it to a path that no longer exists. Nothing imported the output, and every
function in it already lived in the canonical module, so the template was removed.
This pins that a generated copy cannot come back as a string constant.
"""

import ast
from pathlib import Path

_SCRIPT = Path(__file__).parent / "scripts" / "analyze_duplicates.py"


def _embeds_generated_command_utils(source: str) -> bool:
    """True when a module-level string constant carries a command-execution definition."""
    for node in ast.parse(source).body:
        value = node.value if isinstance(node, (ast.Assign, ast.AnnAssign)) else None
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            if "def execute_shell_command" in value.value:
                return True
    return False


def test_the_analyser_embeds_no_generated_command_utils():
    assert not _embeds_generated_command_utils(_SCRIPT.read_text(encoding="utf-8"))


def test_the_matcher_tells_a_template_from_a_mention():
    template = '_T = """\nasync def execute_shell_command(cmd):\n    pass\n"""\n'
    mention = 'NAMES = ["execute_shell_command"]\nlogger_hint = "use execute_shell_command"\n'
    assert _embeds_generated_command_utils(template)
    assert not _embeds_generated_command_utils(mention)


def test_the_canonical_stripper_strips_a_real_esc_byte():
    from utils.encoding_utils import strip_ansi_codes

    assert strip_ansi_codes("\x1b[31mERROR\x1b[0m done") == "ERROR done"
