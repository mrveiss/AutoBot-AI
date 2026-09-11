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
merged into Dev_new_gui), 11 Sep 2026: 54 of 608 modules failed. Its records named
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

**Shrink-only.** An entry leaves in the change that fixes it: a full run fails on an
entry that no longer fails the way it is listed. There is no sanctioned route in -- a
new offender is fixed, not listed.
"""

from __future__ import annotations

#: 53 -- the SLM's whole ``api`` package (51, ``socket.connect``) and two backend
#: modules that write outside the tree at import.
HAS_IMPORT_EFFECT: frozenset[tuple[str, str]] = frozenset(
    {
        ("autobot-backend", "api.multimodal"),
        ("autobot-backend", "api.vision"),
        ("autobot-slm-backend", "api"),
        ("autobot-slm-backend", "api._resume_plan"),
        ("autobot-slm-backend", "api.agents"),
        ("autobot-slm-backend", "api.api_keys"),
        ("autobot-slm-backend", "api.auth"),
        ("autobot-slm-backend", "api.autobot_teams"),
        ("autobot-slm-backend", "api.autobot_users"),
        ("autobot-slm-backend", "api.blue_green"),
        ("autobot-slm-backend", "api.browser"),
        ("autobot-slm-backend", "api.code_source"),
        ("autobot-slm-backend", "api.code_sync"),
        ("autobot-slm-backend", "api.config"),
        ("autobot-slm-backend", "api.deployments"),
        ("autobot-slm-backend", "api.discovery"),
        ("autobot-slm-backend", "api.errors"),
        ("autobot-slm-backend", "api.events"),
        ("autobot-slm-backend", "api.external_agents"),
        ("autobot-slm-backend", "api.health"),
        ("autobot-slm-backend", "api.infrastructure"),
        ("autobot-slm-backend", "api.llm_config"),
        ("autobot-slm-backend", "api.maintenance"),
        ("autobot-slm-backend", "api.memory_lifecycle_proxy"),
        ("autobot-slm-backend", "api.mfa"),
        ("autobot-slm-backend", "api.monitoring"),
        ("autobot-slm-backend", "api.node_ssh_helpers"),
        ("autobot-slm-backend", "api.nodes"),
        ("autobot-slm-backend", "api.nodes_execution"),
        ("autobot-slm-backend", "api.npu"),
        ("autobot-slm-backend", "api.orchestration"),
        ("autobot-slm-backend", "api.performance"),
        ("autobot-slm-backend", "api.personality_proxy"),
        ("autobot-slm-backend", "api.rdp"),
        ("autobot-slm-backend", "api.redis_service"),
        ("autobot-slm-backend", "api.roles"),
        ("autobot-slm-backend", "api.scim"),
        ("autobot-slm-backend", "api.secrets"),
        ("autobot-slm-backend", "api.security"),
        ("autobot-slm-backend", "api.service_ports"),
        ("autobot-slm-backend", "api.services"),
        ("autobot-slm-backend", "api.settings"),
        ("autobot-slm-backend", "api.setup_wizard"),
        ("autobot-slm-backend", "api.slm_users"),
        ("autobot-slm-backend", "api.sso"),
        ("autobot-slm-backend", "api.sso_auth"),
        ("autobot-slm-backend", "api.stateful"),
        ("autobot-slm-backend", "api.tls"),
        ("autobot-slm-backend", "api.updates"),
        ("autobot-slm-backend", "api.venv_reconcile"),
        ("autobot-slm-backend", "api.vnc"),
        ("autobot-slm-backend", "api.voice_proxy"),
        ("autobot-slm-backend", "api.websocket"),
    }
)

#: 1 -- a facade doing ``from utils.error_boundaries import ...``. That ``utils`` is the
#: backend's top-level package, so the module imports only with ``autobot-backend`` on
#: ``sys.path``; from its own tree it raises ModuleNotFoundError. Not side-effect debt.
DOES_NOT_IMPORT: frozenset[tuple[str, str]] = frozenset({(".", "autobot_shared.error_boundaries")})
