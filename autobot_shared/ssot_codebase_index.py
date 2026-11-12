# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Codebase indexing settings, split out of ``ssot_config.MiscConfig`` (#18057).

``ssot_config.py`` is over the file-size ceiling and may not grow, so these fields live here
and ``MiscConfig`` inherits them: ``config.codebase_index_*`` and ``config.misc.*`` are
unchanged. ``RedactedSettings`` is defined in ``ssot_config``, so this base uses
``BaseSettings`` directly; ``MiscConfig`` supplies the redacted repr.
"""

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from autobot_shared.env_utils import parse_int_or_default
from autobot_shared.paths import project_root

# One declared default per knob: the field default, the unparseable-value fallback and the
# reader's own fallback in ``chromadb_storage`` all use these (#20683).
DEFAULT_CODEBASE_INDEX_BATCH_SIZE = 5000
DEFAULT_CODEBASE_INDEX_EMBED_BATCH_SIZE = 100


class CodebaseIndexSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(project_root() / ".env"), env_file_encoding="utf-8", extra="ignore")

    codebase_index_batch_size: int = Field(default=DEFAULT_CODEBASE_INDEX_BATCH_SIZE, alias="CODEBASE_INDEX_BATCH_SIZE")
    codebase_index_embedding_mode: str = Field(default="precompute", alias="CODEBASE_INDEX_EMBEDDING_MODE")
    codebase_index_embed_batch_size: int = Field(
        default=DEFAULT_CODEBASE_INDEX_EMBED_BATCH_SIZE, alias="CODEBASE_INDEX_EMBED_BATCH_SIZE"
    )
    codebase_index_incremental: str = Field(default="", alias="CODEBASE_INDEX_INCREMENTAL")
    codebase_index_parallel_batches: str = Field(default="", alias="CODEBASE_INDEX_PARALLEL_BATCHES")
    codebase_index_parallel_files: str = Field(default="50", alias="CODEBASE_INDEX_PARALLEL_FILES")
    # #18057: the indexing subprocess watchdog. Strings, not ints: pydantic refuses an
    # unparseable int when the config loads, and a bad value here must clamp and log in
    # ``indexing_executor`` rather than stop the backend starting.
    indexing_hard_timeout: str = Field(default="1800", alias="AUTOBOT_INDEXING_HARD_TIMEOUT")
    indexing_progress_timeout: str = Field(default="300", alias="AUTOBOT_INDEXING_PROGRESS_TIMEOUT")
    indexing_watchdog_interval: str = Field(default="30", alias="AUTOBOT_INDEXING_WATCHDOG_INTERVAL")

    # #20683: pydantic refuses an unparseable int when the config loads, which would stop the
    # backend starting before the readers' own fallbacks ran. Fall back to the default and log.
    @field_validator("codebase_index_batch_size", mode="before")
    @classmethod
    def _tolerant_batch_size(cls, value: object) -> int:
        return parse_int_or_default("CODEBASE_INDEX_BATCH_SIZE", value, DEFAULT_CODEBASE_INDEX_BATCH_SIZE)

    @field_validator("codebase_index_embed_batch_size", mode="before")
    @classmethod
    def _tolerant_embed_batch_size(cls, value: object) -> int:
        return parse_int_or_default("CODEBASE_INDEX_EMBED_BATCH_SIZE", value, DEFAULT_CODEBASE_INDEX_EMBED_BATCH_SIZE)
