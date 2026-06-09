# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Pydantic-settings config classes for optional LangFuse and LangSmith tracing (GH#9012).

Both classes implement an `.enabled` property that gates client construction —
callers must check `.enabled` before instantiating the observer.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings


class LangFuseTracingConfig(BaseSettings):
    host: str = ""
    public_key: str = ""
    secret_key: str = ""

    model_config = {"env_prefix": "LANGFUSE_", "extra": "ignore"}

    @property
    def enabled(self) -> bool:
        return bool(self.host and self.public_key and self.secret_key)


class LangSmithTracingConfig(BaseSettings):
    api_url: str = "https://api.smith.langchain.com"
    api_key: str = ""
    project: str = "autobot"

    model_config = {"env_prefix": "LANGSMITH_", "extra": "ignore"}

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)
