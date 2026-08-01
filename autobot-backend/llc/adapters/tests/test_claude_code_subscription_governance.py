# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""ClaudeCodeSubscriptionAdapter inherits governed command building (GH#11186).

The subscription adapter is a second governed-agent execution path; it must apply
the same forbidden-tool enforcement + hardening as its ClaudeCodeAdapter parent
(previously it had its own inline build lacking --disallowedTools, resume
enforcement, and the `--` terminator).
"""

from llc.adapters.claude_code_subscription_adapter import ClaudeCodeSubscriptionAdapter


def _cmd(resume, cfg, prompt="do it"):
    return ClaudeCodeSubscriptionAdapter._build_command("claude", resume, cfg, prompt, session_id="fresh-sid")


def test_fresh_session_enforces_disallowed_and_terminator():
    cmd = _cmd(None, {"allowed_tools": ["Read"], "disallowed_tools": ["Bash"]})
    assert cmd[cmd.index("--allowedTools") + 1] == "Read"
    assert cmd[cmd.index("--disallowedTools") + 1] == "Bash"
    assert cmd[-2] == "--" and cmd[-1] == "do it"


def test_resumed_session_still_enforces_disallowed():
    cmd = _cmd("sess-9", {"disallowed_tools": ["Bash", "Edit"]})
    assert cmd[cmd.index("--resume") + 1] == "sess-9"
    assert cmd[cmd.index("--disallowedTools") + 1] == "Bash,Edit"
    assert cmd[-2] == "--" and cmd[-1] == "do it"


def test_injection_and_prompt_are_neutralized():
    cmd = _cmd(None, {"disallowed_tools": ["Bash", "--evil"]}, prompt="--dangerously-skip-permissions")
    # flag-looking disallowed value dropped; prompt neutralized after `--`
    assert cmd[cmd.index("--disallowedTools") + 1] == "Bash"
    assert cmd[-2] == "--" and cmd[-1] == "--dangerously-skip-permissions"
