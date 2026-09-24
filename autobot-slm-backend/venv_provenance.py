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

Thirteen distributions across two venvs on one host were in that state, and pip
stops at the first, so each failed deploy revealed one. The first sweep counted
twelve because it looked in `autobot-backend/venv` alone and said "on one host";
the thirteenth is `psycopg2_binary` in `autobot-slm-backend/venv` -- the SLM's
own venv, which is the component that runs the builtin updater this repair is
wired into. The marker is now written into `RECORD`
(`write_provenance_marker`), which makes the invariant above true rather than
assumed, and a husk left by the old behaviour is cleared before an install
(`clear_provenance_husks`).

That claim is exact, and #17357 is what made it exact rather than usual. #17338
appended the `RECORD` entry after writing the marker, and the append could
no-op -- no `RECORD` to append to, or an `OSError` swallowed by the same
handler as the marker write -- which left the marker on disk unrecorded: one
package back in the state above, from the code that exists to prevent it. So
the stamp and its `RECORD` entry are now one operation. A marker that cannot be
recorded is not left behind, and the package simply reads as unverified next
time. The invariant therefore holds in every case, at the price of provenance
for a package whose `RECORD` is missing or unwritable -- a price this module
was already built to pay, since "unverified" is a state it handles and a husk
is not.

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

    It must also be a real directory, not a symlink to one (#17362). `is_dir`
    and `iterdir` both follow links, so a `*.dist-info` symlink pointing at a
    directory whose sole entry is a file named `AUTOBOT_PROVENANCE` used to
    answer True here -- and the deletion then reached THROUGH the link and
    removed that file in the target directory, outside `site-packages`
    entirely. That contradicted the promise this docstring makes two paragraphs
    up, which is the reason it is checked rather than assumed: #17339 made this
    predicate run as root on every provisioned host, in three venvs, so the
    property has to hold rather than merely be likely.
    """
    if dist_info.is_symlink() or not dist_info.is_dir():
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


#: Suffix of the temp file `_replace_record_atomically` replaces RECORD from.
#: Named rather than inlined so a test can refuse exactly that write without
#: hardcoding the spelling -- the #17357 tests broke silently once the RECORD
#: write moved, and a shared constant is what makes that break loud.
RECORD_TMP_SUFFIX = ".autobot-provenance-tmp"


def _preserve_record_identity(record: Path, tmp: Path) -> None:
    """Give *tmp* the mode and ownership of *record* before it replaces it (#17371).

    `os.replace` installs the temp file's own mode and owner. A `RECORD` that
    becomes root-owned or `0600` breaks pip for the venv's own user -- and
    since #17339 this runs as root on every provisioned host, which is exactly
    where the temp file's owner differs from the manifest's.

    A failure to `chown` is not fatal: it means this process is not root, in
    which case it could not have changed the owner anyway and the file it
    created already belongs to the right user.
    """
    try:
        stat = record.stat()
    except OSError:
        return
    try:
        os.chmod(tmp, stat.st_mode & 0o7777)
    except OSError as exc:
        logger.warning("venv-provenance: could not carry %s's mode onto its replacement: %s", record, exc)
    try:
        os.chown(tmp, stat.st_uid, stat.st_gid)
    except (OSError, AttributeError):
        pass


def _replace_record_atomically(record: Path, body: str) -> None:
    """Replace *record* with *body* via a temp file and `os.replace` (#17371).

    `Path.write_text` opens with `"w"`, which truncates before writing, so an
    interrupted run -- a kill during provisioning, a full disk, an OOM, a power
    loss -- can leave RECORD short or empty. RECORD is the manifest pip uses to
    know what a package owns, so losing it breaks pip's management of a package
    that was working, chosen by whatever happened to be mid-write rather than
    by having any problem. The reconciler re-stamps every declared package on
    every run, so the exposure is once per package per run.

    `os.replace` is atomic within a filesystem, and the temp file is created in
    the same directory to guarantee that. A reader sees the old complete file
    or the new complete file, never a partial one. The temp file is removed on
    any failure so a failed run leaves no `RECORD.*` litter beside the manifest
    -- which would be a husk in a different costume.
    """
    tmp = record.with_name(f"{record.name}{RECORD_TMP_SUFFIX}")
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        _preserve_record_identity(record, tmp)
        os.replace(tmp, record)
    except BaseException:
        # Including KeyboardInterrupt and SystemExit: an interrupted
        # provisioning run is the scenario this function exists for, and the
        # temp file must not outlive it.
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _record_marker_in_record(dist_info: Path, marker: Path) -> bool:
    """List the marker in the distribution's own `RECORD` (#17332). True if it is listed.

    pip deletes the paths `RECORD` names and then the directory if nothing is
    left; an unrecorded file keeps the directory alive as a husk that blocks
    every later pip run for that package. Appending the entry is what makes
    this module's central claim -- "a reinstall erases the marker" -- true.

    The hash and size columns are left empty, which is what pip itself writes
    for `RECORD` and is accepted on uninstall. Idempotent: the reconciler
    re-stamps every declared package on every run.

    The return value is what the caller needs to keep that claim true rather
    than mostly true (#17357): a distribution with no `RECORD` cannot list the
    marker, so a marker left there would be exactly the unrecorded file this
    function exists to prevent. `OSError` is deliberately NOT caught here --
    the caller must be able to tell "not recorded" from "recorded", and a
    swallowed error here would report success for a write that did not happen.
    """
    record = dist_info / "RECORD"
    if not record.is_file():
        return False
    entry = f"{dist_info.name}/{marker.name}"
    try:
        body = record.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        # A ValueError, so the caller's `except OSError` would NOT catch it and
        # it would abort the remaining packages in `mark_current_set`'s loop --
        # fatal, against that caller's "never fatal to the surrounding install"
        # (#17371). Unreadable RECORD is treated as unrecordable: the package
        # is left unstamped and reads as unverified, exactly as a missing
        # RECORD does.
        logger.warning("venv-provenance: %s has a non-UTF-8 RECORD (%s); leaving it untouched", dist_info.name, exc)
        return False
    if any(line.split(",", 1)[0] == entry for line in body.splitlines()):
        return True
    separator = "" if body.endswith("\n") or not body else "\n"
    _replace_record_atomically(record, f"{body}{separator}{entry},,\n")
    return True


def _take_back_unrecorded_marker(marker: Path, component: str, why: str) -> None:
    """Remove a marker this call just wrote but could not get listed in `RECORD` (#17357).

    This is a rollback, not a cleanup: the only file it can remove is the one
    the caller wrote microseconds earlier in the same call, so it never
    deletes state belonging to an earlier run or to anything else.

    Leaving it instead is the #17332 defect reintroduced one package at a time
    -- an unrecorded file in a `dist-info`, which survives the next uninstall
    and turns the directory into a husk that blocks every later pip run for
    that name. Unstamped is a state this module already handles (the package
    reads as unverified and is not removed without
    `AUTOBOT_VENV_RECONCILE_ALLOW_UNVERIFIED_REMOVAL`); a husk is a state that
    breaks pip for everything downstream of it.
    """
    try:
        marker.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning(
            "venv-provenance[%s]: %s is unrecorded AND could not be removed (%s) -- "
            "this dist-info will survive its next uninstall as a husk (#17332)",
            component,
            marker,
            exc,
        )
        return
    logger.info(
        "venv-provenance[%s]: left %s unstamped -- %s; it will read as unverified rather than seed a husk",
        component,
        marker.parent.name,
        why,
    )


def write_provenance_marker(dist_info: Path, component: str) -> None:
    """Stamp *dist_info* as this tool's own — best-effort, never fatal to the
    surrounding install: a marker write failure means the NEXT candidacy
    check for this package fails closed (unverified), not that this run
    itself should abort.

    A marker that cannot be listed in `RECORD` is not written at all (#17357).
    The stamp and its `RECORD` entry are one operation, because the marker is
    only safe to leave on disk while pip knows to delete it: half of it -- a
    marker with no entry -- is precisely the #17332 husk, a `dist-info` that
    survives its own uninstall and blocks every later pip run for that name.

    So the two ways this can fail land in the same place, which is the place
    the paragraph above already promised: unstamped, read as unverified next
    time, removable only under
    `AUTOBOT_VENV_RECONCILE_ALLOW_UNVERIFIED_REMOVAL`. That costs provenance
    for one package in one run. The alternative -- stamp anyway, as this did
    before #17357 -- keeps provenance and knowingly seeds a husk, trading a
    state this module handles for one that breaks pip for everything after it.
    """
    # Imported here, not at module scope (#17339): ansible stages THIS FILE
    # alone onto a node and runs it with the target venv's own interpreter,
    # where `autobot_shared` is not importable. Only the marker-writing half
    # needs it, and that half never runs from the staged copy.
    from autobot_shared.time_utils import utc_timestamp  # noqa: PLC0415

    payload = {"tool": "autobot-venv-reconcile", "component": component, "recorded_at": utc_timestamp()}
    marker = dist_info / PROVENANCE_MARKER_FILENAME
    try:
        marker.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        recorded = _record_marker_in_record(dist_info, marker)
    except OSError as exc:
        logger.warning("venv-provenance[%s]: could not write marker at %s: %s", component, marker, exc)
        # The marker may be on disk already: this also catches an OSError from
        # the RECORD step, which runs after the marker write has succeeded.
        _take_back_unrecorded_marker(marker, component, f"RECORD could not be updated: {exc}")
        return
    if not recorded:
        _take_back_unrecorded_marker(marker, component, "the distribution has no RECORD to list it in")


def site_packages_dirs(venv_dir: Path) -> List[Path]:
    """Every `site-packages` inside *venv_dir*, by glob rather than by version.

    The interpreter version is in the path, and hardcoding it is how this kind
    of helper silently stops matching after an interpreter bump.
    """
    return sorted(venv_dir.glob("lib/python*/site-packages"))


def _unlink_marker_within(dist_info: Path) -> None:
    """Remove the marker inside *dist_info* without following a link out of it (#17362).

    `O_NOFOLLOW` fails with `ELOOP` if *dist_info* is itself a symlink, and
    `O_DIRECTORY` fails with `ENOTDIR` if it is not a directory, so the
    descriptor can only name the real directory being cleared. Unlinking
    relative to that descriptor removes the entry inside it -- `unlink` never
    follows the final component, so a symlinked marker loses the link, not its
    target. Both failures are `OSError`, which the caller already logs and
    skips.
    """
    fd = os.open(dist_info, os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY)
    try:
        os.unlink(PROVENANCE_MARKER_FILENAME, dir_fd=fd)
    finally:
        os.close(fd)


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

    The removal enforces that last clause itself rather than trusting the
    predicate to have done so (#17362): `_unlink_marker_within` opens the
    directory with `O_NOFOLLOW | O_DIRECTORY` and unlinks by `dir_fd`, so the
    deletion cannot leave the directory it is clearing even if a link is
    planted between the check and the removal.
    """
    removed: List[str] = []
    if not site_packages.is_dir():
        return removed
    for dist_info in sorted(site_packages.glob("*.dist-info")):
        if not is_provenance_husk(dist_info):
            continue
        try:
            _unlink_marker_within(dist_info)
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


def clear_venv_husks(venv_dir: Path) -> List[str]:
    """Clear husks in every ``site-packages`` under *venv_dir*. Returns the names.

    The whole-venv form of :func:`clear_provenance_husks`, extracted so the
    ansible entry point below and ``api/venv_reconcile._run_pip_install`` share
    one loop as well as one classification (#17339).
    """
    removed: List[str] = []
    for site_packages in site_packages_dirs(venv_dir):
        removed.extend(clear_provenance_husks(site_packages))
    return removed


def main(argv: Optional[List[str]] = None) -> int:
    """Clear a venv's husks from the command line (#17339).

    The reachable-from-ansible half of #17332's repair. A host whose only
    entry point is provisioning never runs ``api/venv_reconcile``, so its
    husks survive and every pip step that must upgrade a husked package keeps
    aborting with ``uninstall-no-record-file``.

    Deliberately runnable by the venv's OWN interpreter: a husk is a
    ``dist-info`` directory, not a broken interpreter or a broken stdlib, so
    this repairs the venv that is broken without needing a second one. That
    matters most for ``autobot-slm-backend/venv``, which runs the builtin
    updater -- the only other path to this repair -- and can therefore be the
    venv whose husk blocks its own repair.

    Exit status is 0 when there was nothing to clear: an absent venv on first
    provisioning is not a failure, and neither is a healthy one.
    """
    import argparse

    parser = argparse.ArgumentParser(description="Clear AUTOBOT_PROVENANCE dist-info husks from a venv (#17332).")
    parser.add_argument("venv", help="path to the virtualenv to repair, e.g. /opt/autobot/autobot-backend/venv")
    args = parser.parse_args(argv)

    venv_dir = Path(args.venv)
    if not venv_dir.is_dir():
        print(f"venv-provenance: {venv_dir} does not exist, nothing to clear")
        return 0
    removed = clear_venv_husks(venv_dir)
    if removed:
        print(f"venv-provenance: cleared {len(removed)} husk dist-info dir(s): {', '.join(removed)}")
    else:
        print(f"venv-provenance: no husks in {venv_dir}")
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through subprocess in tests
    raise SystemExit(main())
