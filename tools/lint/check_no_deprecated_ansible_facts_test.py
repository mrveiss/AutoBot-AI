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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_no_deprecated_ansible_facts import find_violations  # noqa: E402


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


def test_a_line_is_not_double_counted_across_both_patterns() -> None:
    """A `when:` that also contains `{{ }}` must report once, not twice."""
    body = "      when: \"{{ ansible_distribution }}\" == 'Ubuntu'\n"
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "both.yml", body)
        assert len(find_violations(f)) == 1
