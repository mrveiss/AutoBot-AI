# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one spelling of the "all-users" scope sentinel (#18094).

``GLOBAL_USER`` is the user segment used in per-user Redis keys
(``rag:retrieval_patterns:<user>:<hash>``, ``rag:feedback:<user>:<date>``,
``pref:signal:<org>:<user>:...``) when no individual user applies.

This is NOT the knowledge-board id ``"__global__"`` in ``knowledge/search.py``,
``api/schemas_knowledge.py`` and ``api/knowledge_boards.py``: that names a board,
a different concept that happens to share the spelling.
"""

#: Canonical spelling; every new write uses it.
GLOBAL_USER = "__global__"

#: Spellings written by earlier releases. Readers must still honour rows stored
#: under them; nothing writes them. ``services.feedback_aggregator`` used
#: ``__global_user__`` for the ``pref:signal:`` keyspace. Rewriting stored rows
#: needs human approval (#17038), so they are read, not migrated.
LEGACY_GLOBAL_USER_SPELLINGS: tuple = ("__global_user__",)
