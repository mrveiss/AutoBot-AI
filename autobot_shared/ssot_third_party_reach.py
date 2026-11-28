# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Third-party reader / search fast-path settings, split out of ``ssot_config.FeatureConfig`` (#21850).

``ssot_config.py`` is over the file-size ceiling and may not grow, so these settings live here and
``FeatureConfig`` inherits them: ``config.feature.<name>``.

The third-party reader and search services receive every URL and search query a fast path sends
them. They are therefore opt-in: ``third_party_fast_paths_enabled`` defaults to off, and a user turns
it on in the web research settings. The two base URLs are the only place the destinations are named.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from autobot_shared.paths import project_root


class ThirdPartyReachSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(project_root() / ".env"), env_file_encoding="utf-8", extra="ignore")

    # Default for the user-visible opt-in. Off: no URL or query leaves for a third party unasked.
    third_party_fast_paths_enabled: bool = Field(default=False, alias="AUTOBOT_THIRD_PARTY_FAST_PATHS_ENABLED")

    # Third-party reader service: GET <base><page url> returns the page as markdown.
    third_party_reader_base_url: str = Field(default="https://r.jina.ai/", alias="AUTOBOT_THIRD_PARTY_READER_BASE_URL")

    # Third-party search service: GET <base><url-encoded query> returns search results.
    third_party_search_base_url: str = Field(default="https://s.jina.ai/", alias="AUTOBOT_THIRD_PARTY_SEARCH_BASE_URL")
