# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Install-provenance for the venv reconciler (#15067).

`api/venv_reconcile.py` (#15063) decides what to remove by diffing this
tool's own history of *declared* package names against the current
requirements — a name diff. That protects any name the tool's history never
declared, but it has one proven hole: a package an operator installs, by
hand, under a name this venv's history once declared — after that name left
requirements, before the next reconcile — is indistinguishable from tool
debris and gets removed regardless of who put it there this time. `pip`'s own
`INSTALLER` field cannot discriminate this either: it reads `pip` for both an
operator's manual install and this tool's own, because both really did run
`pip install`.

This module adds the missing signal: a marker file, `AUTOBOT_PROVENANCE`,
written into a distribution's own `dist-info` directory immediately after
*this tool's own* `pip install` confirms that distribution present for the
CURRENT declared set. Deliberately dist-info-adjacent, not venv- or
lock-level: a per-venv lock only knows "this name was declared", and cannot
see whether the on-disk installation was replaced in the meantime — but
`pip install`/`pip uninstall`, whoever runs it, always fully replaces a
distribution's dist-info directory. So the marker surviving IS the proof nothing
touched that installation since this tool itself last confirmed it, and the
marker's absence on an otherwise-matching name IS the proof something did.

Concretely:

- Every reconcile run stamps the marker onto every package in the CURRENT
  declared-and-transitive-closure set, right after this run's own `pip
  install -r requirements.txt` confirmed the venv holds it (`mark_current_set`).
  An operator's later manual `pip install`/`pip uninstall` of that same name
  replaces the dist-info directory and erases the marker; this tool's own next
  run, if the package is still declared, simply re-stamps it — so the marker
  survives an in-place upgrade this tool itself performs (it is rewritten
  every run) without surviving anyone else's install.
- A removal candidate (previously declared, no longer declared, not needed
  transitively — `api/venv_reconcile.py`'s own protections) is only actually
  removed when its marker is present (`split_by_provenance`). No marker means
  no proof: either the host predates this module (every host on first run,
  since dist-info marker files do not retroactively exist for anything
  installed before this landed), or an operator reinstalled that exact name
  after this tool declared it and before the next reconcile — the #15067
  collision this module closes.

First-run / migration behaviour: on every existing deployed host, EVERY
package starts with no marker, including packages this tool's own prior
`declared` lock genuinely put there. Treating "no marker" as "safe to remove"
would reintroduce exactly the operator-package destruction #15067 exists to
prevent, on the very first run after this ships. Treating it as "never
remove" would leave #15063 permanently unresolved for every host that
existed before this change. Neither is acceptable as the automatic default,
so the default REFUSES unverified removals and reports them
(`allow_unverified_removal` is False unless explicitly opted in via
`AUTOBOT_VENV_RECONCILE_ALLOW_UNVERIFIED_REMOVAL`) — reversible, since it is
a plain environment toggle an operator can review the reported candidate list
against and set for one run, then unset. Meanwhile every package still
declared keeps getting freshly marked on each run, so the marker coverage
that lets #15063 close automatically, without the opt-in, grows on its own
as requirements genuinely change going forward — no migration step needed.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

from autobot_shared.time_utils import utc_timestamp

logger = logging.getLogger(__name__)

# The one file this module ever writes inside a dist-info directory — never
# a hardcoded literal at each call site.
PROVENANCE_MARKER_FILENAME = "AUTOBOT_PROVENANCE"

# Opt-in, env-backed (never hardcoded true) — see module docstring for why
# the default must refuse rather than assume.
ALLOW_UNVERIFIED_REMOVAL_ENV = "AUTOBOT_VENV_RECONCILE_ALLOW_UNVERIFIED_REMOVAL"


def allow_unverified_removal() -> bool:
    """Operator opt-in to remove a candidate with no provenance marker (#15067).

    Read live (not cached at import) so a test or an operator's env change
    takes effect on the next call without a process restart.
    """
    return os.environ.get(ALLOW_UNVERIFIED_REMOVAL_ENV, "false").strip().lower() in ("1", "true", "yes")


def dist_info_paths(
    raw_state: Dict[str, Dict[str, object]], normalize: Callable[[str], str]
) -> Dict[str, Optional[Path]]:
    """Normalized-name -> dist-info directory, from `installed_state`'s raw output.

    *normalize* is injected (rather than imported from `venv_reconcile`) so
    this module stays a leaf with zero dependency on its caller.
    """
    paths: Dict[str, Optional[Path]] = {}
    for name, info in raw_state.items():
        location = info.get("dist_info") if isinstance(info, dict) else None
        paths[normalize(name)] = Path(location) if location else None
    return paths


def has_tool_provenance(dist_info: Optional[Path]) -> bool:
    """Whether *dist_info* carries this tool's own install marker."""
    return dist_info is not None and (dist_info / PROVENANCE_MARKER_FILENAME).is_file()


def write_provenance_marker(dist_info: Path, component: str) -> None:
    """Stamp *dist_info* as this tool's own — best-effort, never fatal to the
    surrounding install: a marker write failure means the NEXT candidacy
    check for this package fails closed (unverified), not that this run
    itself should abort."""
    payload = {"tool": "autobot-venv-reconcile", "component": component, "recorded_at": utc_timestamp()}
    marker = dist_info / PROVENANCE_MARKER_FILENAME
    try:
        marker.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    except OSError as exc:
        logger.warning("venv-provenance[%s]: could not write marker at %s: %s", component, marker, exc)


def mark_current_set(component: str, names: Set[str], paths: Dict[str, Optional[Path]], steps: List[str]) -> None:
    """Stamp every currently-required, currently-installed package as this
    tool's own — the only moment a reconcile run can truthfully assert "I put
    this exact installation here" (#15067)."""
    marked = 0
    for name in sorted(names):
        dist_info = paths.get(name)
        if dist_info is None or not dist_info.exists():
            continue
        write_provenance_marker(dist_info, component)
        marked += 1
    if marked:
        steps.append(f"venv-reconcile[{component}]: stamped install-provenance for {marked} package(s)")


def split_by_provenance(names: Set[str], paths: Dict[str, Optional[Path]]) -> Tuple[Set[str], Set[str]]:
    """Removal candidates split into (verified-ours, unverified) by marker
    presence — the only signal that survives an operator's manual reinstall
    under a name this tool's history once declared (#15067)."""
    verified: Set[str] = set()
    unverified: Set[str] = set()
    for name in names:
        (verified if has_tool_provenance(paths.get(name)) else unverified).add(name)
    return verified, unverified
