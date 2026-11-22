# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one Vue single-file-component ``<script>`` body extractor (#21641).

The closing tag tolerates whitespace and attributes (``</script >``) as browsers do, and the
match is case-insensitive. ``[\\s\\S]*?`` (not a nested quantifier) keeps it ReDoS-safe (#1733).
"""

import re

VUE_SCRIPT_RE = re.compile(
    r"<script(?=[\s>/])[^>]*>([\s\S]*?)</script(?=[\s>/])[^>]*>",
    re.IGNORECASE,
)
