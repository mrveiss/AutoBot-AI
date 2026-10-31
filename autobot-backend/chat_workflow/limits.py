# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One home for the chat workflow's iteration cap (#17468).

The cap had two truths. `ChatWorkflowManager.MAX_CONTINUATION_ITERATIONS = 5`
was the named one, and `graph.py`'s routing decision hardcoded `< 5` beside it.
Both said five, so nothing failed and nothing logged -- the defect only appeared
the day someone raised the constant and observed no effect on the LangGraph
path, because that path never read it.

A duplicated value is invisible precisely while it is still correct. This module
exists so there is one place to change, and both readers reach it here.

Read as a module ATTRIBUTE at the point of use (`limits.MAX_CONTINUATION_ITERATIONS`),
not bound into each caller's namespace at import. Binding the value at import
recreates the problem in a smaller form: each importer would hold its own copy,
a test could patch one and not the other, and the two would agree only by
accident of ordering.
"""

from __future__ import annotations

from autobot_shared.env_utils import env_int

#: Maximum multi-step continuation iterations for one turn (#352, #17468).
#: Env-backed per the project's configuration rule -- a budget written as a bare
#: literal cannot be changed without a deploy, and this one is a safety limit.
MAX_CONTINUATION_ITERATIONS: int = env_int("AUTOBOT_MAX_CONTINUATION_ITERATIONS", default=5)

#: Files attached to one chat message that are read into the prompt (#20195). Env-backed: a bound written as a
#: bare literal cannot be changed without a deploy. Files past the count are reported to the user, not dropped.
ATTACHMENT_MAX_FILES: int = env_int("AUTOBOT_CHAT_ATTACHMENT_MAX_FILES", default=5)

#: Characters of one attached file's text that reach the prompt (#20195); the rest is cut and the user told.
ATTACHMENT_MAX_CHARS_PER_FILE: int = env_int("AUTOBOT_CHAT_ATTACHMENT_MAX_CHARS_PER_FILE", default=20000)

#: Characters of attached-file text across ALL files of one message (#20195); a later file is cut to what is left.
ATTACHMENT_MAX_CHARS_TOTAL: int = env_int("AUTOBOT_CHAT_ATTACHMENT_MAX_CHARS_TOTAL", default=60000)

#: Bytes of one attached file on disk that extraction is attempted for (#20195); a larger file is reported, never read.
#: Checked BEFORE any extraction, so a huge upload costs the turn nothing.
ATTACHMENT_MAX_FILE_BYTES: int = env_int("AUTOBOT_CHAT_ATTACHMENT_MAX_FILE_BYTES", default=10 * 1024 * 1024)

#: Bytes an Office/OpenDocument archive may expand to, summed over its members from the archive's own index (#20195).
#: A small file that declares more is a decompression bomb and is reported, never opened.
ATTACHMENT_MAX_UNCOMPRESSED_BYTES: int = env_int(
    "AUTOBOT_CHAT_ATTACHMENT_MAX_UNCOMPRESSED_BYTES", default=50 * 1024 * 1024
)

#: Seconds one attached file may take to yield its text (#20195); past it the file is reported unreadable.
ATTACHMENT_EXTRACT_TIMEOUT_SECONDS: int = env_int("AUTOBOT_CHAT_ATTACHMENT_EXTRACT_TIMEOUT_SECONDS", default=30)
