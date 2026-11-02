# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Per-call limits for a command run through the security layer (#19807).

``SecurityLayer.execute_command`` is the one command-execution path. A caller
that runs commands unattended (a workflow step) passes a ``CommandRunPolicy``
instead of building a second path: the policy bounds the child process, makes a
command that needs approval fail at once rather than wait for a person, and
supplies the redactor the shared log and audit sites apply to the command text.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


def _keep(text: str) -> str:
    """The default redactor: leave the text as it is."""
    return text


@dataclass(frozen=True)
class CommandRunPolicy:
    """Limits and recording rules for one command run.

    ``redact`` is applied to the command, and to the risk reasons built from it,
    wherever the shared path logs it, writes it to the audit trail or keeps it in
    history; the command that is executed is never changed by it. ``redact_output``
    is applied to output before anything derived from it is written to disk.
    """

    timeout_s: float
    max_output_bytes: int
    cwd: str
    refuse_approval: bool = True
    redact: Callable[[str], str] = _keep
    redact_output: Callable[[str], str] = _keep

    def show_output(self, output: str) -> str:
        """The form of command *output* that may reach disk or a log."""
        return self.redact_output(output)

    def show(self, command: str) -> str:
        """The form of *command* that may be recorded."""
        return self.redact(command)
