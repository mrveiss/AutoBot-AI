# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Known offenders of ``import_hermeticity_test.py``: frozen, shrink-only (#16198, #16262).

Each entry is a ``(tree, module)`` pair. ``tree`` is the ``sys.path`` entry the module
imports from, repo-relative -- ``autobot-backend``, ``autobot-slm-backend`` or ``.`` --
and ``module`` is its dotted name there. The pair, not the name: ``api.auth`` is a
different module in each backend. The two sets are different debts:

* ``HAS_IMPORT_EFFECT`` -- the sandbox caught the import doing something: a socket
  connect, a process spawn, or a write outside the tree. Side-effect debt.
* ``DOES_NOT_IMPORT`` -- the import raised before any effect could be seen. Not an
  effect; whether it has one once it imports is unknown.

**Boundary** (docs/developer/RATCHET_BASELINES.md, rule 1). The population is every
non-test ``.py`` under ``autobot-backend/api``, ``autobot-slm-backend/api`` and
``autobot_shared`` (``_import_hermeticity_scope.entries``). The detector raises on
``socket.connect``, ``subprocess.Popen``, ``os.system``, ``os.exec``, ``os.spawn``,
``os.posix_spawn`` and writes outside the tree, and fails any import that raises or
exceeds its timeout; the planted controls in the test are its known positives. It
sees nothing else a module does at import -- a DNS lookup, a read, a thread, a signal
handler -- so a module absent from this file has none of THOSE events, which is not
the same as inert. ``test_the_baseline_names_only_modules_in_the_population`` fails
the moment a pair stops naming a module the sweep reaches.

**Provenance.** Run 34564055823, head a0afddd0d (a pull_request run, so checked out
merged into main), 11 Sep 2026: 54 of 608 modules failed. Its records named
modules without their tree, and 10 names exist in both backends, so each tree was
attributed, then checked two ways that share no enumeration with the sweep:

* By elimination, against ``git ls-tree`` at that head, which gives the run's own
  608 (363 + 51 + 194). 41 failing names exist only in the SLM, 10 in both backends,
  ``api.multimodal`` and ``api.vision`` only in the backend, and
  ``autobot_shared.error_boundaries`` only at the root. All 51 SLM modules fail with
  ``socket.connect``: importing any ``api.x`` imports the SLM's ``api`` package first,
  and that connects. So the 10 shared names are the SLM's copies, and since each
  appears once in the records, the backend's copies passed.
* By position. The sweep probes the backend, then the SLM, then the root, each in
  path order, and the records keep that order. Walking them against that sequence
  gives the same 51 / 2 / 1, and the same pairs, compared as sets.

The first full run of the sweep verifies this attribution: a pair in the wrong tree
fails that run twice, as a new offender and as a stale entry.

**Shrink-only.** An entry leaves in the pull request that fixes it: any run that probes
a listed module and finds it no longer failing the way it is listed fails, so the fix
cannot merge with its entry still here. A full run judges every entry; a pull-request
subset judges the entries it probed. There is no sanctioned route in -- a new offender
is fixed, not listed.
"""

from __future__ import annotations

#: 2 -- two backend modules that write outside the tree at import.
#: #16262's fix in config.py's external_url (the socket.connect every SLM
#: api.* module inherited via api/__init__.py's cascading import) cleared
#: all 51 of the SLM's own entries: 4 on the PR-scoped sweep that first
#: reached them (the package's own __init__, _resume_plan, code_sync,
#: venv_reconcile), the remaining 47 confirmed by a full-population sweep
#: (run 34760508167) dispatched specifically to check every listed module,
#: not just the ones one PR's diff happened to touch.
HAS_IMPORT_EFFECT: frozenset[tuple[str, str]] = frozenset(
    {
        ("autobot-backend", "api.multimodal"),
        ("autobot-backend", "api.vision"),
    }
)

#: 1 -- a facade doing ``from utils.error_boundaries import ...``. That ``utils`` is the
#: backend's top-level package, so the module imports only with ``autobot-backend`` on
#: ``sys.path``; from its own tree it raises ModuleNotFoundError. Not side-effect debt.
DOES_NOT_IMPORT: frozenset[tuple[str, str]] = frozenset({(".", "autobot_shared.error_boundaries")})
