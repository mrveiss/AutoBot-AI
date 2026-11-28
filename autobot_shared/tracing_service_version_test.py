# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A span is never tagged with a release nobody made: unset means no ``service.version`` (#17821)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from autobot_shared.env_registry import REGISTRY

_README = Path(__file__).resolve().parent.parent / "README.md"
_LITERAL_VERSION = re.compile(r"current version\W+v?\d+\.\d+\.\d+", re.IGNORECASE)


def test_the_registry_declares_no_service_version_literal() -> None:
    assert REGISTRY["AUTOBOT_OTEL_SERVICE_VERSION"].default == ""


def test_the_readme_states_no_hand_maintained_version_literal() -> None:
    assert not _LITERAL_VERSION.search(_README.read_text(encoding="utf-8"))
    assert _LITERAL_VERSION.search("**Current Version**: v1.5.0")  # contrast: a stale literal is caught


def test_an_unset_version_omits_the_attribute_and_a_set_one_is_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("opentelemetry.sdk")
    from autobot_shared.tracing import _create_tracer_provider

    monkeypatch.delenv("AUTOBOT_OTEL_SERVICE_VERSION", raising=False)
    assert "service.version" not in _create_tracer_provider("svc", None).resource.attributes
    assert _create_tracer_provider("svc", "9.9.9").resource.attributes["service.version"] == "9.9.9"
