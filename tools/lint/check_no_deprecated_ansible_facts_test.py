#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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
