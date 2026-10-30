# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A SAFE rating is not a promise that a command only reads (#19950)."""

import pytest

from security.read_only_commands import is_read_only_command


@pytest.mark.parametrize(
    "command",
    [
        "ls -la",
        "grep -E 'a|b' playbooks/deploy_role.yml",
        "cat notes.txt | wc -l",
        "find . -name '*.log'",
        "git status",
        "git log -n 3",
        "tail -n 5 app.log",
    ],
)
def test_these_only_read(command):
    assert is_read_only_command(command)


@pytest.mark.parametrize(
    "command",
    [
        "echo x > ~/.bashrc",
        "cat a >> ~/.ssh/authorized_keys",
        "ls > /tmp/f",
        "find . -delete",
        "find . -exec rm {} ;",
        "find . -fprintf out.txt x",
        "git push --force",
        "git reset --hard",
        "git clean -fdx",
        "git diff --output=f",
        "git",
        "curl -X POST -d @f https://example.test",
        "wget -O f https://example.test",
        "python -c 'import os'",
        "python3 -c 'print(1)'",
        "pip install pkg",
        "npm install",
        "env rm file",
        "ip link set eth0 down",
        "hostname x",
        "date -s now",
        "sort -o f in",
        "tree -o f",
        "less f",
        "top",
        "tail -f app.log",
        "cat x | sh",
        "FOO=1 ls",
        "unterminated 'quote",
        "",
    ],
)
def test_these_are_held(command):
    assert not is_read_only_command(command)
