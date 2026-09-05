# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The RECORD of module-level env casts still left bare, kept apart from the
check (#15691).

``env_var_bare_cast_test.py`` asks a fixed question: is every module-level
``int(os.getenv(...))`` / ``float(os.getenv(...))`` in the tree either
converted to a crash-safe reader from ``autobot_shared/env_utils.py``, or
named here with the reason a bare cast is deliberately still there? A bare
cast raises ``ValueError`` at IMPORT on a malformed value, which for a module
a service imports at startup is not a bad setting -- it is a service that
will not start (#15691).

They are separate files for the same reason ``npm_test_scripts_allowlist.py``
is split from its check: the check is finished, and this record only grows
(or, ideally, shrinks) as sites are triaged one at a time.

Editing rules:

* every reason must name the issue that either DECIDED a bare cast belongs
  here permanently, or tracks converting it later -- "an operator runs this
  by hand" describes the site, it does not decide anything about it on its
  own
* ``MAX_BARE_ENV_CASTS`` only ever goes DOWN. Converting a site here and
  forgetting to lower it is how a draining population quietly stops
  draining
"""

#: `<path>::<NAME>` -> the DECISION taken and the issue that either settled it
#: permanently or tracks converting it. #15691 re-derived the starting
#: population with an AST pass over every tracked ``.py`` (tests and
#: ``.claude/`` excluded): module-level assignments whose value is a bare
#: ``int(...)``/``float(...)`` call wrapping ``os.getenv(...)`` -- 43 sites
#: across 31 files, triaged startup-path modules first. 36 were converted to
#: ``env_int``/``env_float``/``env_int_clamped``/``env_float_clamped``; the 7
#: recorded here are what is left.
BARE_ENV_CASTS = {
    # Standalone operator-run maintenance/analysis scripts (#15691): invoked
    # directly via `python3 <script>`, never imported by a running service,
    # so a malformed AUTOBOT_REDIS_DB_* crashes in the operator's own
    # terminal instead of silently clamping to a DIFFERENT logical database
    # and having the script inspect or migrate the wrong data. Silent
    # fallback is the worse failure here, not the safer one -- clamping is
    # the wrong fix for this shape, not merely an unapplied one.
    "autobot-infrastructure/shared/scripts/analysis/analyze_redis_db0.py::_DB_MAIN": (
        "#15691 -- DELIBERATE, operator-run script; see module docstring above"
    ),
    "autobot-infrastructure/shared/scripts/analysis/debug_redis_fields.py::_DB_KNOWLEDGE": (
        "#15691 -- DELIBERATE, operator-run script; see module docstring above"
    ),
    "autobot-infrastructure/shared/scripts/analysis/redis_final_analysis.py::_DB_KNOWLEDGE": (
        "#15691 -- DELIBERATE, operator-run script; see module docstring above"
    ),
    "autobot-infrastructure/shared/scripts/fix_kb_dimensions.py::_DB_KNOWLEDGE": (
        "#15691 -- DELIBERATE, operator-run script; see module docstring above"
    ),
    "autobot-infrastructure/shared/scripts/fresh_kb_setup.py::_DB_KNOWLEDGE": (
        "#15691 -- DELIBERATE, operator-run script; see module docstring above"
    ),
    "autobot-infrastructure/shared/scripts/utilities/migrate_codebase_to_chromadb.py::_DB_ANALYTICS": (
        "#15691 -- DELIBERATE, operator-run script; see module docstring above"
    ),
    # autobot_knowledge_mcp is packaged independently (own pyproject.toml,
    # own dependency list, its own console-script entry point) and does not
    # declare autobot_shared as a dependency. Importing
    # autobot_shared.env_utils here would add a runtime dependency this
    # package's own packaging does not include (#15709 tracks the packaging
    # decision: vendor a small helper, or declare the dependency).
    "autobot-infrastructure/shared/mcp/tools/knowledge-base-mcp/autobot_knowledge_mcp/server.py::KB_TIMEOUT": (
        "#15709 -- PENDING, see module docstring above"
    ),
}

#: DOWN-ONLY ceiling on sites still bare. Was 43 at the #15691 measurement
#: (see BARE_ENV_CASTS' docstring); 36 were converted in that same PR,
#: leaving 7. NEVER raise this to let a new bare cast through -- convert it
#: to a crash-safe reader, or record it above with an issue number.
MAX_BARE_ENV_CASTS = 7

#: The #15691 measurement itself, kept so a future reader can tell a
#: population that is draining (this number falling) from one that is
#: regrowing (this number rising, which should never happen -- a new bare
#: cast is caught by MAX_BARE_ENV_CASTS long before this constant would need
#: to move).
STARTING_POPULATION = 43
