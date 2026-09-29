# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One place that says a `source_id` is required, and why (#17758).

Analytics storage keys, document ids, ChromaDB `where` filters and Celery
task-result prefixes all carried the same shape: ``f"...{source_id}..." if
source_id else <unscoped>``. Each fallback merged every project into one
namespace, in three directions:

* **read** -- a project's page is served another project's analysis, which is
  what #17758 reports;
* **write** -- the document lands where scoped readers never look and where any
  project's unscoped read does;
* **delete** -- ``codebase:*`` removes every project's keys, and doc ids without
  a source prefix collide so one project's document upserts over another's.
  That is data loss rather than disclosure.

The class was closed four times before -- #12330 (which built
``resolve_scan_root`` and whose docstring describes this exact leak), #12384,
#8436, #12393 -- and returned each time, because each fix converted the sites
known then and the policy lived in none of them. It lives here now, so a new
call site states the requirement by calling one function instead of re-deciding
it.
"""

from __future__ import annotations

import re
from typing import Annotated

from fastapi import Query

#: A source id is a UUID string (``source_models.py:48``). This is deliberately
#: wider than a UUID pattern -- a legacy or seeded id need not be one -- and
#: deliberately narrower than "non-empty":
#:
#: * ``*``, ``?``, ``[``, ``]`` are Redis glob metacharacters, and these values
#:   reach ``SCAN MATCH`` patterns. ``source_id=*`` builds ``codebase:*:*``,
#:   which matches every project -- and on the delete path deletes them. That is
#:   #17758's destructive variant re-entered through the *value* rather than
#:   through the absence, so rejecting only the empty string does not close it.
#: * ``:`` is excluded so a source id can never spell a dimension tag. Prefixes
#:   are built as ``{prefix}{dimension}:{value}:``, and without this a crafted
#:   id could land in another dimension's namespace.
#: * ``/`` and ``\`` are excluded because these values also reach filesystem
#:   path joins via the source-root resolvers.
_SOURCE_ID_SHAPE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


def require_source_id(source_id: "str | None", what: str) -> str:
    """Return *source_id*, or raise because an unscoped *what* is not an option.

    ``what`` names the thing that would otherwise be built unscoped, so the error
    says which boundary refused rather than only that one did.

    Rejects a malformed id as well as a missing one -- see ``_SOURCE_ID_SHAPE``.
    A route can enforce the shape with ``SourceIdQuery``, but an internal caller
    bypasses the route, and the destructive paths are reached from both.
    """
    if not source_id:
        raise ValueError(f"refusing to build an unscoped {what} without a source_id (#17758)")
    if not _SOURCE_ID_SHAPE.match(source_id):
        raise ValueError(
            f"refusing to build a {what} from a malformed source_id (#17758): "
            "glob metacharacters, separators and colons are not permitted"
        )
    return source_id


#: The query parameter, declared once. Every analytics route that scopes by
#: source uses this rather than spelling `Query(...)` again -- the reported
#: defect was `source_id: str = ""`, an optional parameter nothing read, and a
#: shared required type makes that spelling unavailable.
SourceIdQuery = Annotated[
    str,
    Query(
        min_length=1,
        pattern=r"^[A-Za-z0-9_.-]{1,128}$",
        description="Required (#17758): the code source this result belongs to",
    ),
]


def scoped_prefix(prefix: str, scope: "str | None", scope_name: str = "source_id") -> str:
    """A task-result prefix for ONE value of whatever dimension scopes it (#17758).

    Most callers scope by ``source_id``; ``code_intelligence``'s security score
    scopes by the required ``path`` it analyses. The dimension differs, the
    defect does not: one key per prefix means any ``*/cached`` endpoint serves
    whichever request ran last, whatever distinguishes those requests.

    Raising on a falsy scope is the point -- it makes the global key
    unconstructible, so the ``f"...{x}:" if x else PREFIX`` shape cannot come
    back through a new call site.
    """
    if not scope:
        raise ValueError(f"a task-result prefix requires a {scope_name} (#17758); refusing to build a global key")
    return f"{prefix}{scope_name}:{scope}:"


def source_scoped_prefix(prefix: str, source_id: "str | None") -> str:
    """The task-result prefix for ONE code source (#17758).

    ``{prefix}latest_task_id`` is a single key. Every ``*/cached`` endpoint
    reading it on a fixed prefix therefore serves whichever source scanned last,
    which is the cross-project leak #17758 reports -- and the matching
    ``*/analyze`` starter wrote it there, so scoping one side without the other
    just makes a scoped reader miss an unscoped writer.

    Both sides call this, so they cannot diverge. It **raises** on a falsy
    ``source_id`` rather than returning the unscoped prefix: the
    ``f"...{source_id}:" if source_id else PREFIX`` shape that appears elsewhere
    in this repo is the same leak with a narrower trigger, reappearing whenever
    the parameter is omitted.
    """
    # #17758: through `require_source_id`, so the SHAPE is checked and not only
    # the emptiness. `scoped_prefix` cannot apply this charset itself -- a `path`
    # dimension legitimately contains `/` and `:` -- so the source-specific
    # wrapper is where the source-specific rule belongs.
    return scoped_prefix(prefix, require_source_id(source_id, "task-result prefix"), "source_id")


async def cached_task_result(prefix: str, source_id: str) -> dict:
    """The ``*/cached`` response for ONE source, or ``no_data`` (#17758).

    The three analytics ``*/cached`` endpoints had byte-identical nine-line
    bodies, and that is *how* one leak became three: the scoping fix had to be
    applied in three places and was applied in none. There is one body now, so
    the next correction to it reaches every endpoint instead of the one whose
    symptom was reported.
    """
    from utils.celery_task_status import get_latest_task_result

    cached = await get_latest_task_result(source_scoped_prefix(prefix, source_id))
    if cached and cached.get("result"):
        return {
            "status": "success",
            "from_cache": True,
            "completed_at": cached.get("completed_at"),
            **cached["result"],
        }
    return {"status": "no_data"}
