# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Content source fallback chain — mirrors llm_shared.fallback_chain (#10932)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from content_reach.base import ContentBackend
from source_attribution import SourceType


@dataclass
class ContentSourceChain:
    """Ordered primary+fallback backends for one content source."""

    source: str
    source_type: SourceType
    backends: list[ContentBackend]

    def backend_names(self) -> list[str]:
        """Return backend names in execution order."""
        return [b.name for b in self.backends]

    def reordered(self) -> "ContentSourceChain":
        """Apply AUTOBOT_CONTENT_CHAIN_<SOURCE> env override, if present."""
        env_key = f"AUTOBOT_CONTENT_CHAIN_{self.source.upper()}"
        spec = os.environ.get(env_key, "").strip()
        if not spec:
            return self

        wanted = [n.strip() for n in spec.split(",") if n.strip()]
        by_name = {b.name: b for b in self.backends}
        promoted = [by_name[n] for n in wanted if n in by_name]
        promoted_names = {b.name for b in promoted}
        remainder = [b for b in self.backends if b.name not in promoted_names]
        return ContentSourceChain(
            source=self.source,
            source_type=self.source_type,
            backends=promoted + remainder,
        )
