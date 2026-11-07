# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""One print_header: the service registry CLI uses the script_utils one (#18450)."""

from utils import script_utils, service_registry_cli


def test_cli_uses_canonical_print_header():
    assert service_registry_cli.print_header is script_utils.print_header


def test_canonical_print_header_serves_cli_call_shape(capsys):
    service_registry_cli.print_header("Service URLs")
    out = capsys.readouterr().out
    assert "Service URLs" in out
    assert "=" * 10 in out
