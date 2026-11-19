# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Frozen count of the literal install root in Ansible files (#18587, #18880).

BOUNDARY: every git-tracked file under autobot-slm-backend/ansible/. Counted: occurrences of
`/opt/autobot` in CODE -- comments are stripped by tools.lint._comment_syntax, because prose
that names the deploy folder is documentation, not configuration. For the same reason Markdown
files and Python docstrings are outside it, and so is tests/fixtures/ (frozen copies of past
files) -- owner decision 2026-10-22, #18882. Excluded: the one definition,
`autobot.base_dir` (`base_dir: "/opt/autobot"`) in inventory/group_vars/all.yml (#15632).

Frozen 2026-10-19: 309 occurrences in 72 files. Cross-derived once at freeze time by an
independent grep that dropped `#` comment lines: the same 72-file set. Each entry only goes DOWN;
#18881 (playbooks) and #18882 (roles, templates, inventory, tests) take it to empty.

Retired by #19040: upgrade-backend-agent.yml (2) and fix-slm-agent-node-id.yml (4), so 303 in 70 files.
#18881 moved every playbook to `autobot.base_dir`: 176 occurrences in 29 files, so 127 in 41 files.
#18882 moved roles, templates, top-level playbooks and scripts; prose and fixtures left the
boundary: 0 -- the floor. Only the one definition names the root.
"""

BASELINE: dict[str, int] = {}
