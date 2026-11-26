# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tracing settings, split out of ``ssot_config.MiscConfig`` (#21685).

``ssot_config.py`` is over the file-size ceiling and may not grow, so these fields live here and
``MiscConfig`` inherits them: ``config.misc.otel_*`` is the single definition.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from autobot_shared.paths import project_root


class TracingSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(project_root() / ".env"), env_file_encoding="utf-8", extra="ignore")

    # Trace sampling: AUTOBOT_OTEL_SAMPLE_RATE is the one setting. AUTOBOT_TRACE_SAMPLE_RATE is a deprecated alias,
    # used only when the canonical name is unset (autobot_shared/tracing.py logs the warning). Strings: a bad value
    # falls back to the default at the read site instead of failing the whole config load.
    otel_sample_rate: str = Field(default="0.1", alias="AUTOBOT_OTEL_SAMPLE_RATE")
    # Default spelled as the env registry's ``False`` (env_registry.py) so the two planes agree (#17419); read
    # case-insensitively by ``tracing._is_otel_enabled``.
    otel_enabled: str = Field(default="False", alias="AUTOBOT_OTEL_ENABLED")
    otel_endpoint: str = Field(default="", alias="AUTOBOT_OTEL_ENDPOINT")
    otel_service_version: str = Field(default="1.5.0", alias="AUTOBOT_OTEL_SERVICE_VERSION")
    trace_sample_rate: str | None = Field(default=None, alias="AUTOBOT_TRACE_SAMPLE_RATE")
