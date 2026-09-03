# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Deployed-venv dependency reconciliation for the code-sync update path (#15063).

`pip install -r requirements.txt` — the only Python dependency step the
builtin updater ever ran — only adds and upgrades. A package deleted from a
requirements file stayed installed in the deployed venv indefinitely, because
nothing in the update path ever asked pip to remove anything.

This module adds the removal half, scoped and auditable:

1. Resolve the *declared set* for a component from its requirements file(s),
   following `-r`/`-e` includes the same way pip does (`-c` constraint files
   pin versions but do not themselves declare a package for install, so they
   are validated but not added to the declared set).
2. Compare that declared set against the one recorded the *previous* time
   reconciliation ran for this venv (a small lock file next to the venv).
   Only a package that WAS declared before and is NOT declared now is even a
   removal candidate — a name this tool's own history never declared is
   never a candidate at all, which is what keeps an unrelated
   operator-installed package (`ipdb`, say) off the removal list. There
   being no history to compare against (first run, or a freshly recreated
   venv) is treated as "cannot reconcile yet", not "remove nothing is same
   as everything is fine" — the run records a baseline and removes nothing.
3. Drop from that candidate list anything still reachable, transitively, from
   the CURRENT declared set (walked over each installed distribution's own
   `Requires-Dist`, read locally from the venv — no network, no resolver
   call) — so a package another declared dependency still needs is never
   removed just because it stopped being declared directly.
4. Report the resulting removal set before touching anything, then uninstall
   it. A package pip fails to remove stays in the lock's declared set so the
   next run retries it, rather than the bookkeeping silently forgetting it.

Components whose ansible role installs an explicit package LIST rather than a
requirements file (`EXPLICIT_LIST_COMPONENTS`) have nothing here to reconcile
against — `refuse_explicit_list` reports that plainly instead of silently
skipping them.

INSTALL PROVENANCE (#15067) — step 2's name diff alone cannot tell "this
tool put this exact installation here" apart from "an operator happens to
have installed something under this exact name since". `venv_provenance.py`
closes that gap with a dist-info-adjacent marker file this tool stamps onto
every currently-required package after its own `pip install` confirms it
present, so an operator's later manual reinstall under a name this tool once
declared erases the marker along with the rest of that dist-info directory.
A removal candidate is only actually removed when its marker is present; one
with no marker — including every package on every host that predates this
module — is reported and left alone unless an operator opts in via
`venv_provenance.ALLOW_UNVERIFIED_REMOVAL_ENV`. See that module's docstring
for the full model and the first-run rationale.
"""

from __future__ import annotations

import asyncio
import configparser
import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import venv_provenance as provenance
from autobot_shared.time_utils import utc_timestamp

# Plain stdlib logging, deliberately (mirrors code_sync.py itself, and the
# password_epoch.py precedent CLAUDE.md documents): this module is imported
# at collection time by tests that stub `config` as a MagicMock, and
# `autobot_shared.logging_manager.get_logger()` reads real config at import
# time to size its file handler — under that stub regime it raises before a
# single test in the file can run.
logger = logging.getLogger(__name__)

# Timeouts are env-backed module constants, never a hardcoded bare number
# scattered through call sites — mirrors the existing pip-install timeout
# pattern in code_sync.py.
_PIP_INSTALL_TIMEOUT = float(os.environ.get("AUTOBOT_PIP_INSTALL_TIMEOUT", "300"))
_VENV_INSPECT_TIMEOUT = float(os.environ.get("AUTOBOT_VENV_INSPECT_TIMEOUT", "60"))
_PIP_UNINSTALL_TIMEOUT = float(os.environ.get("AUTOBOT_PIP_UNINSTALL_TIMEOUT", "120"))

# Recorded next to the venv itself (never in the deployed component tree, so
# it is never rsynced away by a resync) — the previous run's declared set.
_DECLARED_LOCK_FILENAME = ".autobot_declared_lock.json"

# Worker components whose ansible role installs an explicit package LIST
# rather than a requirements file — code_sync.py's `_WORKER_COMPONENT_PIP`
# comment traces exactly why each one is absent from that dict. There is no
# file for this module to reconcile against, so these must refuse and report,
# never silently pass through as "nothing to do" (#15063 AC4).
EXPLICIT_LIST_COMPONENTS: frozenset = frozenset({"autobot-npu-worker", "autobot-browser-worker", "autobot-slm-agent"})

_NAME_BOUNDARY_RE = re.compile(r"[<>=!~;\[\s]")
_NORMALIZE_RE = re.compile(r"[-_.]+")
# Narrow, dependency-free extraction of a PEP 621 `[project] name = "..."` field —
# a full TOML parser is unwarranted for the one string this needs, and `tomllib`
# is 3.11+ only while this module must import under whatever interpreter the
# test runner provides (#15063).
_TOML_PROJECT_NAME_RE = re.compile(r'(?m)^\s*name\s*=\s*["\']([^"\']+)["\']')


@dataclass(frozen=True)
class ReconcileReport:
    """Outcome of one `reconcile_component` run, for tests and callers."""

    component: str
    status: str  # "ok" | "baseline_recorded" | "refused" | "not_applicable"
    reason: str
    declared: Tuple[str, ...] = ()
    removed: Tuple[str, ...] = ()
    kept_transitive: Tuple[str, ...] = ()
    unverified: Tuple[str, ...] = ()  # candidates skipped: no install-provenance marker (#15067)
    failed: Tuple[str, ...] = ()


def normalize_name(name: str) -> str:
    """PEP 503 normalization — how pip itself compares distribution names."""
    return _NORMALIZE_RE.sub("-", name).strip("-").lower()


def extract_requirement_name(spec: str) -> Optional[str]:
    """Bare, normalized package name from a requirement or Requires-Dist spec.

    Deliberately ignores version specifiers, extras and markers — over-
    including (treating a marker'd requirement as required) only makes the
    transitive closure larger, which can only prevent a removal, never cause
    an unsafe one.
    """
    spec = spec.strip()
    if not spec:
        return None
    boundary = _NAME_BOUNDARY_RE.search(spec)
    name = spec[: boundary.start()] if boundary else spec
    name = name.strip()
    return normalize_name(name) if name else None


def _strip_inline_comment(line: str) -> str:
    """A requirements-file comment is preceded by whitespace, never mid-token."""
    return re.split(r"\s+#", line, maxsplit=1)[0].strip()


def _editable_project_name(project_dir: Path) -> Optional[str]:
    """Distribution name of a `-e <path>` local package, from its own metadata."""
    pyproject = project_dir / "pyproject.toml"
    if pyproject.exists():
        try:
            text = pyproject.read_text(encoding="utf-8")
        except OSError:
            return None
        match = _TOML_PROJECT_NAME_RE.search(text)
        if match:
            return normalize_name(match.group(1))
    setup_cfg = project_dir / "setup.cfg"
    if not setup_cfg.exists():
        return None
    parser = configparser.ConfigParser()
    try:
        parser.read(setup_cfg, encoding="utf-8")
    except configparser.Error:
        return None
    name = parser.get("metadata", "name", fallback=None)
    return normalize_name(name) if name else None


def _resolve_line(code: str, path: Path, declared: Set[str], warnings: List[str], seen: Set[Path]) -> None:
    """Handle one parsed (comment-stripped) requirements-file line."""
    if code.startswith(("-r ", "--requirement ")):
        target = path.parent / code.split(None, 1)[1].strip()
        _resolve_into(target, declared, warnings, seen)
    elif code.startswith(("-c ", "--constraint ")):
        # A constraint pins a version IF something else requires the package —
        # it never declares the package for install on its own (#15063).
        target = path.parent / code.split(None, 1)[1].strip()
        if not target.exists():
            warnings.append(f"constraints file not found: {target}")
    elif code.startswith(("-e ", "--editable ")):
        target = path.parent / code.split(None, 1)[1].strip()
        name = _editable_project_name(target)
        if name is None:
            warnings.append(f"could not determine package name for editable install: {target}")
        else:
            declared.add(name)
    elif code.startswith("-"):
        return  # other pip options (--hash, --index-url, ...) name no package
    else:
        name = extract_requirement_name(code)
        if name is None:
            warnings.append(f"unparseable requirement line in {path}: {code!r}")
        else:
            declared.add(name)


def _resolve_into(path: Path, declared: Set[str], warnings: List[str], seen: Set[Path]) -> None:
    resolved = path.resolve()
    if resolved in seen:
        return
    seen.add(resolved)
    if not path.exists():
        warnings.append(f"requirements file not found: {path}")
        return
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        warnings.append(f"could not read {path}: {exc}")
        return
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        code = _strip_inline_comment(stripped)
        if code:
            _resolve_line(code, path, declared, warnings, seen)


def resolve_declared_names(entry_path: Path) -> Tuple[Set[str], List[str]]:
    """The true declared set for *entry_path*, resolving `-r`/`-e` includes.

    Returns (names, warnings). A non-empty warnings list means the declared
    set could NOT be established with confidence — callers must refuse rather
    than act on a partial result (#15063).
    """
    declared: Set[str] = set()
    warnings: List[str] = []
    _resolve_into(entry_path, declared, warnings, set())
    return declared, warnings


_INSPECT_SCRIPT = (
    "import importlib.metadata as m, json\n"
    "out = {}\n"
    "for d in m.distributions():\n"
    "    name = d.metadata.get('Name')\n"
    "    if not name:\n"
    "        continue\n"
    "    di = getattr(d, '_path', None)\n"
    "    out[name] = {'requires': d.requires or [], 'dist_info': str(di) if di else None}\n"
    "print(json.dumps(out))\n"
)


async def installed_state(venv_python: Path) -> Optional[Dict[str, Dict[str, object]]]:
    """Every distribution installed in *venv_python*'s venv — its raw
    Requires-Dist strings and its dist-info directory (for #15067 provenance
    markers) — read locally via importlib.metadata, no network, no resolver
    call. Returns None when the venv cannot be introspected."""
    if not venv_python.exists():
        return None
    try:
        proc = await asyncio.create_subprocess_exec(
            str(venv_python),
            "-c",
            _INSPECT_SCRIPT,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=_VENV_INSPECT_TIMEOUT)
    except (asyncio.TimeoutError, OSError) as exc:
        logger.error("venv-reconcile: could not introspect %s: %s", venv_python, exc)
        return None
    if proc.returncode != 0:
        logger.error("venv-reconcile: introspection failed for %s: %s", venv_python, stdout)
        return None
    try:
        return json.loads(stdout.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        logger.error("venv-reconcile: bad introspection output for %s: %s", venv_python, exc)
        return None


def build_dependency_graph(raw_state: Dict[str, Dict[str, object]]) -> Dict[str, Set[str]]:
    """Normalize `installed_state`'s raw Requires-Dist strings into a name graph."""
    graph: Dict[str, Set[str]] = {}
    for name, info in raw_state.items():
        requires = info.get("requires") or [] if isinstance(info, dict) else []
        deps = {n for n in (extract_requirement_name(r) for r in requires) if n}
        graph.setdefault(normalize_name(name), set()).update(deps)
    return graph


def transitive_closure(roots: Set[str], graph: Dict[str, Set[str]]) -> Set[str]:
    """Every package reachable from *roots* by walking `graph` — deliberately
    marker-blind (#15063): treating a conditional dependency as required only
    ever prevents a removal, never causes one."""
    seen: Set[str] = set()
    stack = list(roots)
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        stack.extend(graph.get(name, ()))
    return seen


def load_lock(lock_path: Path) -> Optional[Set[str]]:
    """The declared set recorded on the previous reconcile run, or None when
    there isn't one (unreadable, absent, or malformed) — treated as "no
    history to compare against" by the caller, never as "empty is fine"."""
    if not lock_path.exists():
        return None
    try:
        data = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("venv-reconcile: could not read lock %s: %s", lock_path, exc)
        return None
    if not isinstance(data, dict):
        logger.warning("venv-reconcile: malformed lock %s: top level is not an object", lock_path)
        return None
    names = data.get("declared")
    if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
        logger.warning("venv-reconcile: malformed lock %s: 'declared' is not a list of strings", lock_path)
        return None
    return {normalize_name(n) for n in names}


def write_lock(lock_path: Path, declared: Set[str]) -> None:
    payload = {"declared": sorted(declared), "recorded_at": utc_timestamp()}
    lock_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


async def uninstall_packages(pip_bin: Path, names: List[str]) -> Tuple[List[str], List[str]]:
    """`pip uninstall -y` one package at a time, for precise per-package
    success/failure — never a single combined call whose failure would hide
    which specific package survived."""
    removed: List[str] = []
    failed: List[str] = []
    for name in names:
        try:
            proc = await asyncio.create_subprocess_exec(
                str(pip_bin),
                "uninstall",
                "-y",
                name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=_PIP_UNINSTALL_TIMEOUT)
        except (asyncio.TimeoutError, OSError) as exc:
            logger.error("venv-reconcile: uninstall %s errored: %s", name, exc)
            failed.append(name)
            continue
        if proc.returncode == 0:
            logger.info("venv-reconcile: removed %s", name)
            removed.append(name)
        else:
            logger.error(
                "venv-reconcile: uninstall %s failed (rc=%d): %s",
                name,
                proc.returncode,
                stdout.decode("utf-8", errors="replace")[:200],
            )
            failed.append(name)
    return removed, failed


def _report(
    component: str, status: str, reason: str, steps: List[str], *, declared: Optional[Set[str]] = None
) -> ReconcileReport:
    msg = f"venv-reconcile[{component}]: {status} — {reason}" if reason else f"venv-reconcile[{component}]: {status}"
    steps.append(msg)
    (logger.warning if status == "refused" else logger.info)(msg)
    return ReconcileReport(component=component, status=status, reason=reason, declared=tuple(sorted(declared or ())))


def refuse_explicit_list(component: str, steps: List[str]) -> ReconcileReport:
    """Report — not silently skip — a component with no requirements file
    to reconcile against (#15063 AC4)."""
    reason = (
        f"{component} dependencies are an explicit ansible-installed package list, "
        "not a requirements file — reconciliation must go through that component's "
        "ansible role (Update-All / per-role redeploy), not code-sync"
    )
    return _report(component, "refused", reason, steps)


def _unverified_skip_message(component: str, skipped: Set[str]) -> str:
    return (
        f"venv-reconcile[{component}]: {len(skipped)} candidate(s) with no install-provenance "
        f"marker — NOT removed (unverified origin, set {provenance.ALLOW_UNVERIFIED_REMOVAL_ENV}=1 "
        f"to allow after review): {sorted(skipped)}"
    )


async def _apply_removals(
    component: str,
    declared: Set[str],
    previous: Set[str],
    graph: Dict[str, Set[str]],
    dist_info_paths: Dict[str, Optional[Path]],
    lock_path: Path,
    pip: Path,
    steps: List[str],
) -> ReconcileReport:
    candidates = previous - declared
    closure = transitive_closure(declared, graph)
    kept = candidates & closure
    installed = set(graph.keys())
    # `& installed`: pip uninstall -y <not-installed> exits 0 with a warning
    # rather than failing, so without this filter a candidate that is not
    # actually there would be reported (falsely) as removed, not merely waste
    # a subprocess call.
    provisional = (candidates - kept) & installed
    verified, unverified = provenance.split_by_provenance(provisional, dist_info_paths)
    allowed = provenance.allow_unverified_removal()
    skipped = set() if allowed else unverified
    removable = sorted(verified | (unverified if allowed else set()))
    if skipped:
        skip_msg = _unverified_skip_message(component, skipped)
        steps.append(skip_msg)
        logger.warning(skip_msg)
    msg = f"venv-reconcile[{component}]: {len(removable)} package(s) to remove: {removable}"
    steps.append(msg)
    logger.info(msg)
    removed, failed = await uninstall_packages(pip, removable) if removable else ([], [])
    if kept:
        kept_msg = f"venv-reconcile[{component}]: kept (still required transitively): {sorted(kept)}"
        steps.append(kept_msg)
        logger.info(kept_msg)
    write_lock(lock_path, declared | set(failed) | skipped)
    return ReconcileReport(
        component=component,
        status="ok",
        reason="",
        declared=tuple(sorted(declared)),
        removed=tuple(removed),
        kept_transitive=tuple(sorted(kept)),
        failed=tuple(failed),
        unverified=tuple(sorted(skipped)),
    )


async def reconcile_component(component: str, req_path: str, pip_bin: str, steps: List[str]) -> ReconcileReport:
    """Bring *component*'s venv to its declared dependency set, including
    removals — or refuse and report exactly what could not be reconciled
    (#15063). Never removes and discovers: every branch that cannot establish
    the declared set or introspect the venv with confidence refuses instead.
    Every currently-required package is (re-)stamped with this run's own
    install-provenance marker regardless of branch (#15067) — that is the
    only moment reconcile can truthfully claim "I put this exact installation
    here", so it happens whether or not this run goes on to remove anything.
    """
    req, pip = Path(req_path), Path(pip_bin)
    if not req.exists():
        return _report(component, "not_applicable", f"no requirements file at {req}", steps)
    declared, warnings = resolve_declared_names(req)
    if warnings:
        return _report(component, "refused", "; ".join(warnings), steps, declared=declared)
    raw_state = await installed_state(pip.parent / "python")
    if raw_state is None:
        reason = f"could not introspect venv at {pip.parent}"
        return _report(component, "refused", reason, steps, declared=declared)
    graph = build_dependency_graph(raw_state)
    dist_info_paths = provenance.dist_info_paths(raw_state, normalize_name)
    provenance.mark_current_set(component, transitive_closure(declared, graph), dist_info_paths, steps)
    lock_path = pip.parents[1] / _DECLARED_LOCK_FILENAME
    previous = load_lock(lock_path)
    if previous is None:
        write_lock(lock_path, declared)
        reason = f"no prior declared-set snapshot — recorded baseline of {len(declared)} package(s)"
        return _report(component, "baseline_recorded", reason, steps, declared=declared)
    return await _apply_removals(component, declared, previous, graph, dist_info_paths, lock_path, pip, steps)


async def install_pip_deps_for_component(component: str, steps: List[str]) -> bool:
    """Install Python deps from the component's requirements.txt into its venv (#9982).

    Unconditional — pip is fast when nothing changed (same rationale as #1603).
    Appends human-readable step notes to *steps*.
    Returns True on success, False when pip exits non-zero so callers can surface
    the failure (previously the non-zero rc was swallowed — #11322).
    """
    from api.code_sync import _COMPONENT_PIP_PATHS, _WORKER_COMPONENT_PIP  # avoid circular import

    # #12450: worker components carry their own (req, pip) pair — ai-stack's file
    # is requirements-ai.txt, not requirements.txt.
    paths = _COMPONENT_PIP_PATHS.get(component) or _WORKER_COMPONENT_PIP.get(component)
    if paths is None:
        return True
    req_path, pip_bin = paths
    if not Path(req_path).exists():
        steps.append(f"pip: no requirements file at {req_path} — skipped")
        return True
    if component in _WORKER_COMPONENT_PIP and not Path(pip_bin).exists():
        # Worker-only relaxation: a worker venv is provisioned by ansible, never
        # by code-sync, so a missing one means "not deployed here" rather than a
        # broken install — the code rsync + restart is still valid on its own.
        # Backends deliberately keep the original behaviour (attempt the exec so
        # a genuine pip failure surfaces via pip_ok=False, #11322).
        steps.append(f"pip: no venv pip at {pip_bin} — skipped (provisioned by ansible)")
        return True
    return await _run_pip_install(component, req_path, pip_bin, steps)


async def _run_pip_install(component: str, req_path: str, pip_bin: str, steps: List[str]) -> bool:
    steps.append(f"pip: installing {req_path} into {Path(pip_bin).parent}")
    try:
        proc = await asyncio.create_subprocess_exec(
            pip_bin,
            "install",
            "-r",
            req_path,
            "--quiet",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=_PIP_INSTALL_TIMEOUT)
        if proc.returncode == 0:
            logger.info("drift resolve: pip install ok for %s", component)
            steps.append("pip: install succeeded")
            return True
        out = stdout.decode(errors="replace")[:300] if stdout else ""
        logger.error("drift resolve: pip install failed (%d) for %s: %s", proc.returncode, component, out)
        steps.append(f"pip: install failed (rc={proc.returncode}): {out[:150]}")
        return False
    except asyncio.TimeoutError:
        logger.error("drift resolve: pip install timed out for %s", component)
        steps.append("pip: install timed out after 300s")
        return False
    except Exception as exc:
        logger.error("drift resolve: pip install error for %s: %s", component, exc)
        steps.append(f"pip: install error: {exc}")
        return False


async def install_slm_pip_dependencies(req_path: str, pip_bin: str) -> bool:
    """Install Python dependencies from requirements.txt into the SLM venv.

    Runs unconditionally after rsync — pip is fast when nothing changed (#1603).
    Returns True on success or when there is no requirements file to install,
    False on pip failure — callers use this to gate removal reconciliation:
    running removal after a failed install risks reading a venv the install
    only partially updated (#15063).
    """
    if not Path(req_path).exists():
        logger.debug("No requirements.txt at %s — skipping pip install", req_path)
        return True
    try:
        proc = await asyncio.create_subprocess_exec(
            pip_bin,
            "install",
            "-r",
            req_path,
            "--quiet",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=_PIP_INSTALL_TIMEOUT)
        if proc.returncode == 0:
            logger.info("SLM pip install completed successfully")
            return True
        output = stdout.decode(errors="replace")[:500] if stdout else ""
        logger.error("SLM pip install failed (rc=%d): %s", proc.returncode, output)
        return False
    except asyncio.TimeoutError:
        logger.error("SLM pip install timed out after %ss", _PIP_INSTALL_TIMEOUT)
        return False
    except Exception as exc:
        logger.error("SLM pip install error: %s", exc)
        return False
