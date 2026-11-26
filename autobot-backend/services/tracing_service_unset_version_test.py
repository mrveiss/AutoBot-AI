# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The backend's tracing resource never carries an invented service version (#17821)."""

import pytest

pytest.importorskip("opentelemetry.sdk")

from services.tracing_service import TracingService  # noqa: E402


def test_an_unset_version_omits_service_version_and_a_set_one_is_kept():
    TracingService.reset_instance()
    service = TracingService()
    assert service._service_version is None
    assert "service.version" not in service._create_resource().attributes
    service._service_version = "9.9.9"
    assert service._create_resource().attributes["service.version"] == "9.9.9"
    TracingService.reset_instance()
