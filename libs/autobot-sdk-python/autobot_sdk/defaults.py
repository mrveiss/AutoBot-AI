# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Pagination and search defaults for the SDK's resource methods.

These mirror ``autobot_shared.ssot_constants.QueryDefaults`` value for value.
They are *duplicated* rather than imported because this package ships to PyPI
with two dependencies -- ``httpx`` and ``pydantic`` -- and importing the
platform's shared module would drag the whole backend into a client install.

Duplication is only safe if something stops it drifting: the client and the
server would otherwise disagree about a page size while both looked correct in
isolation. ``repo_tests/sdk_defaults_match_ssot_test.py`` pins every constant
here against ``QueryDefaults`` and fails if either side moves alone.
"""

from __future__ import annotations

#: Results returned by ``knowledge.search()`` when the caller does not say.
DEFAULT_SEARCH_LIMIT: int = 10

#: Rows per page for list endpoints when the caller does not say.
DEFAULT_PAGE_SIZE: int = 50

#: Where an offset-paginated list starts when the caller does not say.
#:
#: This constant used to argue that no route the SDK targets is offset-paginated.
#: That is wrong, and #15170 was filed to settle it either way. Measured: the
#: search route the SDK already calls -- ``POST /knowledge_base/search``, reached
#: by :meth:`autobot_sdk.resources.knowledge.KnowledgeResource.search` -- declares
#: ``offset`` on its request model (``SearchRequest`` in the backend's
#: ``api/schemas_knowledge.py``) and defaults it to ``QueryDefaults.DEFAULT_OFFSET``,
#: the very SSOT key this constant mirrors. So offset pagination is the declared
#: shape of a route in the SDK's own surface, not a shape it left behind: the
#: constant is kept (#15170, option (a)), and that route is where it belongs.
#:
#: ``search()`` does not send it **yet**, and that is deliberate rather than an
#: oversight. The handler declares ``offset`` and never reads it -- the only
#: mention in ``api/knowledge_search.py`` is a docstring line -- so an ``offset=``
#: argument here would be dropped exactly as ``max_results`` was, which is the
#: defect #15119 removed. The client half lands when the server half does.
#:
#: What ``/knowledge_base/entries`` and ``/chat/sessions`` do is unchanged and was
#: never the whole story: the first is cursor-paginated, the second is not
#: paginated at all, which is why the ``offset=`` both used to be called with was
#: dropped by FastAPI (#15119).
#:
#: ``sdk_defaults_match_ssot_test.py`` pins this to ``QueryDefaults``;
#: ``sdk_request_body_test.py`` pins the claim above to the route that carries it,
#: so this docstring cannot go stale the way the one it replaces did.
DEFAULT_OFFSET: int = 0
