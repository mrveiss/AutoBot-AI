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
        "cat notes.txt | grep x",
        "git log --oneline",
        "ls *.py",
        "ls --file-type",
        "cat docs/notes.txt",
        "ls /tmp",
        "ls; cat notes.txt",
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
        "tail -qf app.log",
        "tail --foll app.log",
        "tail --ret app.log",
        "tail -n 5",
        "cat",
        "wc -l",
        "grep x",
        "head -n 5",
        "cat /dev/zero",
        "head -c 99999 /dev/zero",
        "cat /dev/stdin",
        "cat -",
        "file -C -m x",
        "git log --ext-diff",
        "git diff --out=f",
        "ls; cat",
        "ls && cat",
        "ls\ncat",
        "grep -A 3 x",
        "grep -e a -e b",
        "du --files0-from=/dev/stdin",
        "wc --files0-from=-",
        "du --files0=/dev/stdin",
        "wc --files=-",
        "cat //dev/zero",
        "cat .env",
        "cat config/.env.local",
        "head -n 5 deploy/id_rsa",
        "grep token secrets/server.key",
        "ls --hide=.env",
        "cat .e*",
        "cat *",
        "grep -r token .",
        "grep --recursive token .",
        "grep --exclude-from=- x y",
        "cat /sys/kernel/debug/tracing/trace_pipe",
        "cat /./proc/self/environ",
        "cat ../proc/self/environ",
        "cat ../../etc/hosts",
        "cat /de?/zero",
        "cat $FILE",
        "cat ~/*",
        "git show --textconv",
        "cat x | sh",
        "FOO=1 ls",
        "unterminated 'quote",
        "",
    ],
)
def test_these_are_held(command):
    assert not is_read_only_command(command)
