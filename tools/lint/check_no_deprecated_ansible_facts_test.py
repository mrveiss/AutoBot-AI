#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for check_no_deprecated_ansible_facts (#7221)."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_no_deprecated_ansible_facts import (  # noqa: E402
    REPO_ROOT,
    _BARE_EXPR_KEYS,
    _iter_scalar_nodes,
    find_violations,
)


def _write(tmp: Path, name: str, body: str) -> Path:
    p = tmp / name
    p.write_text(body, encoding="utf-8")
    return p


def test_clean_file_passes() -> None:
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "ok.yml", "key: '{{ ansible_facts[\"hostname\"] }}'\n")
        assert find_violations(f) == []


def test_deprecated_default_ipv4_blocked() -> None:
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "bad.yml", "host: '{{ ansible_default_ipv4.address }}'\n")
        violations = find_violations(f)
        assert len(violations) == 1
        assert violations[0][1] == "default_ipv4"


def test_deprecated_hostname_blocked() -> None:
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "bad.yml", "msg: 'Host {{ ansible_hostname }}'\n")
        violations = find_violations(f)
        assert len(violations) == 1
        assert violations[0][1] == "hostname"


def test_inventory_var_ansible_user_allowed() -> None:
    """ansible_user is an inventory variable, NOT an auto-injected fact."""
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "ok.yml", "msg: 'User {{ ansible_user }}'\n")
        assert find_violations(f) == []


def test_inventory_var_ansible_host_allowed() -> None:
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "ok.yml", "msg: 'Host {{ ansible_host }}'\n")
        assert find_violations(f) == []


def test_connection_var_ansible_python_interpreter_allowed() -> None:
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "ok.yml", "i: '{{ ansible_python_interpreter }}'\n")
        assert find_violations(f) == []


def test_jinja_filter_chain_blocked() -> None:
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "bad.yml", "k: '{{ ansible_distribution_release | default(\"x\") }}'\n")
        violations = find_violations(f)
        assert len(violations) == 1
        assert violations[0][1] == "distribution_release"


def test_multiple_violations_in_one_file() -> None:
    with tempfile.TemporaryDirectory() as d:
        body = (
            "host: '{{ ansible_default_ipv4.address }}'\n"
            "name: '{{ ansible_hostname }}'\n"
            "ok: '{{ ansible_facts[\"os_family\"] }}'\n"
        )
        f = _write(Path(d), "multi.yml", body)
        violations = find_violations(f)
        assert len(violations) == 2
        attrs = {v[1] for v in violations}
        assert attrs == {"default_ipv4", "hostname"}


def test_jinja_template_file() -> None:
    """`.j2` templates are not YAML and stay on the line-based path."""
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "service.j2", "Environment=HOST={{ ansible_fqdn }}\n")
        violations = find_violations(f)
        assert len(violations) == 1
        assert violations[0][1] == "fqdn"


if __name__ == "__main__":
    # Manual smoke test
    test_clean_file_passes()
    test_deprecated_default_ipv4_blocked()
    test_deprecated_hostname_blocked()
    test_inventory_var_ansible_user_allowed()
    test_inventory_var_ansible_host_allowed()
    test_connection_var_ansible_python_interpreter_allowed()
    test_jinja_filter_chain_blocked()
    test_multiple_violations_in_one_file()
    test_jinja_template_file()
    print("All tests passed.")


# --- #14181: `when:` and friends are Jinja without `{{ }}` --------------------


def test_a_deprecated_fact_in_a_when_clause_is_blocked() -> None:
    """Ansible evaluates `when:` as Jinja with no braces, so the `{{ }}`-anchored
    pattern could not see it.

    `deploy-base.yml` carried the same fact on the same task in all three forms
    — two inside `{{ }}` and one in a `when:`. Fixing only the reported two
    would have moved the ansible-core 2.24 breakage from the template to the
    conditional while the hook reported the file clean.
    """
    body = "      when: hostvars[item]['ansible_default_ipv4']['address'] is defined\n"
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "when.yml", body)
        assert len(find_violations(f)) == 1


def test_other_bare_expression_keys_are_covered() -> None:
    body = (
        "      failed_when: ansible_distribution == 'Ubuntu'\n"
        "      changed_when: ansible_os_family != 'Debian'\n"
        "      until: ansible_hostname is defined\n"
    )
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "bare.yml", body)
        assert len(find_violations(f)) == 3


def test_inventory_vars_stay_valid_in_a_when_clause() -> None:
    """`ansible_host`/`ansible_user` are connection vars, not facts.

    Widening the match without keeping the FACT_ATTRS filter would block the
    inventory vars the migration deliberately left alone — worse than the
    blind spot it closes.
    """
    body = (
        "      when: hostvars[item]['ansible_host'] is defined\n"
        "      failed_when: ansible_user != 'root'\n"
        "      changed_when: ansible_python_interpreter is defined\n"
    )
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "inventory.yml", body)
        assert find_violations(f) == []


def test_a_mixed_when_is_not_double_counted() -> None:
    """A `when:` string that also contains `{{ }}` must report once, not twice.

    Written as a single quoted scalar (the only valid-YAML way to mix a
    `{{ }}` template with trailing bare Jinja on one `when:` line) — the
    line-based era's fixture here quoted only the `{{ }}` half, which is not
    valid YAML and would never appear in a real playbook.
    """
    body = "      when: \"{{ ansible_distribution }} == 'Ubuntu'\"\n"
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "both.yml", body)
        assert len(find_violations(f)) == 1


# --- #14196: line-based scanning is blind to folded/literal/list shapes -------


def test_list_style_when_is_no_longer_invisible() -> None:
    """`when:` on its own line followed by a `- cond` list (all ANDed).

    A line-based scan sees `- ansible_hostname is defined` with no `when:`
    prefix on the same line and never matches it. This shape has 22
    occurrences in the tracked tree today, none of them currently violating
    — but the checker was blind to the shape itself, not just to a specific
    violation.
    """
    body = (
        "- name: t\n"
        "  debug:\n"
        "    msg: x\n"
        "  when:\n"
        "    - ansible_hostname is defined\n"
        "    - inventory_hostname is defined\n"
    )
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "list_when.yml", body)
        violations = find_violations(f)
        assert len(violations) == 1
        assert violations[0][1] == "hostname"


def test_folded_when_block_is_no_longer_invisible() -> None:
    """`when: >-` folds the condition onto a physical line the checker never
    scanned before, because the deprecated fact and the `when:` key are no
    longer on the same line.
    """
    body = "- name: t\n  debug:\n    msg: x\n  when: >-\n    ansible_distribution_release in ['focal']\n    and inventory_hostname is defined\n"
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "folded_when.yml", body)
        violations = find_violations(f)
        assert len(violations) == 1
        assert violations[0][1] == "distribution_release"


def test_literal_until_block_is_no_longer_invisible() -> None:
    body = "- name: t\n  command: echo hi\n  until: |\n    ansible_hostname is defined\n  retries: 3\n"
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "literal_until.yml", body)
        violations = find_violations(f)
        assert len(violations) == 1
        assert violations[0][1] == "hostname"


def test_a_brace_split_across_a_folded_line_is_no_longer_invisible() -> None:
    """A multi-line `cmd: >-` template reference (not a bare-expr key), where
    the `{{ }}` pair itself straddles the fold.

    A per-line scan of `cmd: >-`/`{{ ansible_X }}` folded onto ONE physical
    line was already visible to the old checker (the whole `{{ }}` sat on
    one line, same as any other match) — that shape is a parity case, not a
    fix, and is covered by `test_a_folded_non_bare_key_value_stays_visible`
    below. The genuine blind spot is narrower: PyYAML's folding rule joins
    `echo {{\n      ansible_hostname }}` into `echo {{ ansible_hostname }}`
    (one space where the newline was), so the reference only exists once the
    fold has been resolved. A per-line scan never sees it, because neither
    physical line contains a matched `{{ ... ansible_X ... }}` on its own.
    """
    body = "- name: t\n  ansible.builtin.command:\n    cmd: >-\n      echo {{\n      ansible_hostname }}\n"
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "folded_cmd_split.yml", body)
        violations = find_violations(f)
        assert len(violations) == 1
        assert violations[0][1] == "hostname"


def test_a_folded_non_bare_key_value_stays_visible() -> None:
    """Parity check: a `cmd: >-` value whose whole `{{ ansible_X }}` fits on
    one physical continuation line was already visible to the line-based
    scanner (PATTERN doesn't care which key it's under). The structural
    walker must not regress this — it's not a fix, it's a floor.
    """
    body = "- name: t\n  ansible.builtin.command:\n    cmd: >-\n      echo {{ ansible_hostname }}\n      more args\n"
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "folded_cmd.yml", body)
        violations = find_violations(f)
        assert len(violations) == 1
        assert violations[0][1] == "hostname"


def test_connection_vars_in_a_folded_when_stay_clean() -> None:
    """The real `seed-fleet-nodes.yml`/`setup-internal-ca.yml` shape: a folded
    `when: >-` carrying `ansible_host`/`ansible_run_tags` on a continuation
    line. Neither is a FACT_ATTRS member, so widening the scan to see folded
    blocks must not start flagging them.
    """
    body = (
        "- name: t\n"
        "  debug:\n"
        "    msg: x\n"
        "  when: >-\n"
        "    item in groups['slm_nodes']\n"
        "    or (hostvars[item].ansible_host != slm_manager_ip\n"
        "        and 'force' not in ansible_run_tags)\n"
    )
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "connvars.yml", body)
        assert find_violations(f) == []


def test_nested_block_resets_key_context_per_task() -> None:
    """A `block:` nests task mappings; each nested task has its own keys, so
    the outer `when:` context must not leak into the inner task's `msg:`.
    """
    body = (
        "- name: outer\n"
        "  block:\n"
        "    - name: inner\n"
        "      debug:\n"
        "        msg: '{{ ansible_hostname }}'\n"
        "  when: inventory_hostname is defined\n"
    )
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "block.yml", body)
        violations = find_violations(f)
        assert len(violations) == 1
        assert violations[0][1] == "hostname"


def test_malformed_yaml_does_not_crash_the_hook() -> None:
    """Broken YAML syntax is another hook's job (check-yaml); this hook must
    not raise and block the whole pre-commit run over it.
    """
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "broken.yml", "when: [unclosed\n")
        assert find_violations(f) == []


# --- reach self-check: prove the walk actually descends into the tree ---------


def _tracked_yaml_files(root: Path) -> list:
    skip_dirs = {".git", "__pycache__", "node_modules", ".worktrees", "venv", ".venv"}
    out = []
    for path in root.rglob("*.yml"):
        rel_parts = path.relative_to(root).parts
        if any(part in skip_dirs for part in rel_parts):
            continue
        out.append(path)
    for path in root.rglob("*.yaml"):
        rel_parts = path.relative_to(root).parts
        if any(part in skip_dirs for part in rel_parts):
            continue
        out.append(path)
    return out


def _independent_bare_key_scalar_count(root: Path) -> int:
    """Count bare-expr-key scalars via plain `yaml.safe_load` + dict/list
    recursion — deliberately NOT the checker's own `yaml.compose` node-walk,
    so a regression in that walk (e.g. silently reverting to line-based, or
    stopping descent into sequences) cannot also hide from this count. Two
    independently-written traversals of the same tree must agree.
    """

    def count(obj) -> int:
        total = 0
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key in _BARE_EXPR_KEYS:
                    total += len(value) if isinstance(value, list) else 1
                total += count(value)
        elif isinstance(obj, list):
            for item in obj:
                total += count(item)
        return total

    total = 0
    for path in _tracked_yaml_files(root):
        try:
            docs = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
        except yaml.YAMLError:
            continue
        for doc in docs:
            if doc is not None:
                total += count(doc)
    return total


def _node_walk_bare_key_scalar_count(root: Path) -> int:
    """The same count, produced by the checker's own `_iter_scalar_nodes`."""
    total = 0
    for path in _tracked_yaml_files(root):
        try:
            docs = list(yaml.compose_all(path.read_text(encoding="utf-8"), Loader=yaml.SafeLoader))
        except yaml.YAMLError:
            continue
        for doc in docs:
            if doc is None:
                continue
            for key_context, _node in _iter_scalar_nodes(doc, None):
                if key_context in _BARE_EXPR_KEYS:
                    total += 1
    return total


def test_the_node_walk_reaches_every_bare_expr_key_scalar_in_the_tree() -> None:
    """A scan that silently stopped descending (e.g. only visiting top-level
    keys, or reverting to line-based matching) would still report "clean" —
    that exact gap was found in another lint this week. Counting reach a
    second, independent way closes it: if the node-walk's count diverges
    from the plain-dict-recursion count, the walk regressed.
    """
    ansible_root = REPO_ROOT / "autobot-slm-backend" / "ansible"
    walked = _node_walk_bare_key_scalar_count(ansible_root)
    independent = _independent_bare_key_scalar_count(ansible_root)
    assert walked > 0, "the node-walk found zero bare-expr-key scalars — it never reached the tree"
    assert independent > 0, "the independent count found zero — the ground truth itself is broken"
    assert walked == independent, (
        f"node-walk saw {walked} bare-expr-key scalars, the independently-counted "
        f"dict/list recursion found {independent} — the two traversals disagree"
    )
