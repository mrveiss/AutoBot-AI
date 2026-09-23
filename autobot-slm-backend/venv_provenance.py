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
`pip install`/`pip uninstall`, whoever runs it, replaces a distribution's
dist-info directory. So the marker surviving IS the proof nothing touched that
installation since this tool itself last confirmed it, and the marker's absence
on an otherwise-matching name IS the proof something did.

#17332: that invariant was NOT true as first written, and the failure mode was
worse than a wrong answer. pip removes the paths its `RECORD` lists and then the
directory if nothing is left in it — so an unrecorded extra file KEEPS the
directory alive. The marker was unrecorded, so every pip upgrade of a stamped
package left a `dist-info` holding one file: this marker. Python then reports a
second distribution for that name at version `None`, and the next pip run that
must uninstall it aborts:

    error: uninstall-no-record-file
    x Cannot uninstall cachetools None
    '-> The package's contents are unknown: no RECORD file was found

Twelve packages on one host were in that state, and pip stops at the first, so
each failed deploy revealed one. The marker is now written into `RECORD`
(`write_provenance_marker`), which makes the invariant above true rather than
assumed, and a husk left by the old behaviour is cleared before an install
(`clear_provenance_husks`).

Concretely:

- Every reconcile run stamps the marker onto every package in the CURRENT
  declared-and-transitive-closure set, right after this run's own `pip
  install -r requirements.txt` confirmed the venv holds it (`mark_current_set`).
  An operator's later manual `pip install`/`pip uninstall` of that same name
  replaces the dist-info directory and erases the marker — which it can only
  do because the marker is listed in `RECORD` (#17332); this tool's own next
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


#: The two files a real installation always has. A `dist-info` with neither
#: describes nothing that is installed -- see `is_provenance_husk`.
_DISTRIBUTION_FILES = ("METADATA", "RECORD")


def is_provenance_husk(dist_info: Path) -> bool:
    """A `dist-info` left behind by this tool's own unrecorded marker (#17332).

    Recognised narrowly and by evidence, because the remedy is a deletion: the
    directory must describe no installed distribution (no METADATA, no RECORD)
    AND carry this tool's marker AND contain nothing else. Anything else --
    another tool's leftovers, a partial install, a directory with files this
    module did not write -- is not ours to classify and is left alone.
    """
    if not dist_info.is_dir():
        return False
    if any((dist_info / name).exists() for name in _DISTRIBUTION_FILES):
        return False
    try:
        contents = [entry.name for entry in dist_info.iterdir()]
    except OSError:
        return False
    return contents == [PROVENANCE_MARKER_FILENAME]


def has_tool_provenance(dist_info: Optional[Path]) -> bool:
    """Whether *dist_info* carries this tool's own install marker.

    #17332: a husk carries the marker and describes no installation, so it
    would answer "ours" for a package that is not installed. Asking the
    question of a husk is a category error, and answering True would let a
    removal be authorised by the debris of an earlier one.
    """
    if dist_info is None or not (dist_info / PROVENANCE_MARKER_FILENAME).is_file():
        return False
    return not is_provenance_husk(dist_info)


def _record_marker_in_record(dist_info: Path, marker: Path) -> None:
    """List the marker in the distribution's own `RECORD` (#17332).

    pip deletes the paths `RECORD` names and then the directory if nothing is
    left; an unrecorded file keeps the directory alive as a husk that blocks
    every later pip run for that package. Appending the entry is what makes
    this module's central claim -- "a reinstall erases the marker" -- true.

    The hash and size columns are left empty, which is what pip itself writes
    for `RECORD` and is accepted on uninstall. Idempotent: the reconciler
    re-stamps every declared package on every run.
    """
    record = dist_info / "RECORD"
    if not record.is_file():
        return
    entry = f"{dist_info.name}/{marker.name}"
    body = record.read_text(encoding="utf-8")
    if any(line.split(",", 1)[0] == entry for line in body.splitlines()):
        return
    separator = "" if body.endswith("\n") or not body else "\n"
    record.write_text(f"{body}{separator}{entry},,\n", encoding="utf-8")


def write_provenance_marker(dist_info: Path, component: str) -> None:
    """Stamp *dist_info* as this tool's own — best-effort, never fatal to the
    surrounding install: a marker write failure means the NEXT candidacy
    check for this package fails closed (unverified), not that this run
    itself should abort."""
    payload = {"tool": "autobot-venv-reconcile", "component": component, "recorded_at": utc_timestamp()}
    marker = dist_info / PROVENANCE_MARKER_FILENAME
    try:
        marker.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        _record_marker_in_record(dist_info, marker)
    except OSError as exc:
        logger.warning("venv-provenance[%s]: could not write marker at %s: %s", component, marker, exc)


def site_packages_dirs(venv_dir: Path) -> List[Path]:
    """Every `site-packages` inside *venv_dir*, by glob rather than by version.

    The interpreter version is in the path, and hardcoding it is how this kind
    of helper silently stops matching after an interpreter bump.
    """
    return sorted(venv_dir.glob("lib/python*/site-packages"))


def clear_provenance_husks(site_packages: Path, steps: Optional[List[str]] = None) -> List[str]:
    """Remove the husks this module's own unrecorded marker left (#17332).

    Returns the names removed. Every later pip run for a husked package aborts
    with `uninstall-no-record-file`, and pip stops at the first, so a host with
    several needs several failed deploys to discover them all -- which is why
    this repairs the whole venv in one pass rather than the package in hand.

    On the #17038 question of an agent deleting stored state: what is removed
    is tool-authored debris, not data. `is_provenance_husk` admits only a
    directory that describes no installed distribution and whose *sole* content
    is this module's own marker -- it cannot reach a real installation, an
    operator's files, or another tool's. Each removal is logged by name.
    """
    removed: List[str] = []
    if not site_packages.is_dir():
        return removed
    for dist_info in sorted(site_packages.glob("*.dist-info")):
        if not is_provenance_husk(dist_info):
            continue
        try:
            (dist_info / PROVENANCE_MARKER_FILENAME).unlink()
            dist_info.rmdir()
        except OSError as exc:
            logger.warning("venv-provenance: could not clear husk %s: %s", dist_info, exc)
            continue
        removed.append(dist_info.name)
        logger.warning("venv-provenance: cleared husk dist-info %s (#17332)", dist_info.name)
    if removed and steps is not None:
        steps.append(f"venv-provenance: cleared {len(removed)} husk dist-info dir(s): {', '.join(removed)}")
    return removed


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
