# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#18094 — one env var, one fallback; one SSOT constant, one definition.

Two forks that ``check_getenv_ssot_drift`` (which compares a read against an ``ssot_config``
*Field*) cannot see:

(a) **one env var read with differing fallbacks.** ``NPU_WORKER_PORT`` was ``'8080'`` in the doctor
    and ``8081`` in the worker, so the doctor probed the wrong port by default. Every literal
    2-argument ``os.getenv``/``os.environ.get`` fallback for a name is collected across the scanned
    roots; the name forks when its fallbacks disagree with each other, or with the default the env
    registry declares for it. Spelling is normalised by ``values_disagree`` (``"8081"`` = ``8081``,
    ``""`` = ``False`` = ``0``); a one-argument read has no fallback and is a presence check, not a
    competing default.
(b) **a module constant shadowing an SSOT value.** ``DEFAULT_EMBEDDING_MODEL = "nomic-embed-text"``
    in a feature module while ``ssot_config`` declares ``DEFAULT_EMBEDDING_MODEL =
    "nomic-embed-text:latest"``. Any module-level literal constant whose NAME an SSOT module also
    defines is a shadow, whatever its value: the equal-valued copy is the one that drifts later.

A read that deliberately differs carries ``# ssot-config-exempt: <reason>`` (the marker the sibling
guard already honours). A fork that predates this guard and is tracked elsewhere sits in
:data:`KNOWN_ENV_FORKS` with its issue; the table only shrinks -- an entry whose var no longer forks
is itself a finding, so a fixed fork cannot stay listed.
"""

from __future__ import annotations

import ast
import importlib
import logging
import pkgutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from _scan_helpers import tracked_paths
from check_getenv_ssot_drift import EXEMPT_MARKER, _is_getenv_call, _literal, values_disagree

from _check_harness import VacuousScan  # isort: skip -- check_getenv_ssot_drift puts tools/lint on sys.path

#: Name this guard reports under, in messages and in its floor failures.
HOOK_ID = "env-forks"

#: Trees whose env reads are swept. Named, not inferred: a tree outside this list is not covered, and
#: the reach declaration in ``repo_tests/env_fork_guard_18094_test.py`` fails if one of these is empty.
SCAN_ROOTS = (
    "autobot-backend",
    "autobot-slm-backend",
    "autobot_shared",
    "autobot-infrastructure",
    "autobot-npu-worker",
    "scripts",
)

#: Floor for the literal-fallback env reads the sweep collects (249 live; window [209, 249], pin 229): the ONE
#: floor, enforced by ``check_env_forks`` (the sweep's own entrypoint) and
#: passed to the reach declaration in ``repo_tests/env_fork_guard_18094_test.py`` (whose ``verify_floor``
#: proves it against the live population). A sweep that collected a handful has lost its roots and would
#: report "none found" over nothing.
FORK_READ_FLOOR = 229

#: Modules whose module-level literal constants are the SSOT a feature module must not restate.
SSOT_CONSTANT_SOURCES = (
    "autobot_shared/ssot_config.py",
    "autobot_shared/ssot_constants.py",
    "autobot_shared/ssot_tls.py",
)

#: Forks that predate this guard, each tracked in the issue named. Shrink-only (see module doc).
KNOWN_ENV_FORKS: dict[str, str] = {
    "AUTOBOT_BACKEND_HOST": "#17419",
    "AUTOBOT_BROWSER_SERVICE_HOST": "#17419",
    "AUTOBOT_ENV": "#17419",
    "AUTOBOT_REDIS_HOST": "#17419",
    "AUTOBOT_TLS_CERT_DIR": "#17419",
    "SLM_REPO_PATH": "#15708",
}


@dataclass
class ScanResult:
    """What was checked, and what was found."""

    env_reads: int = 0
    env_vars: int = 0
    registered_vars: int = 0
    constants: int = 0
    unresolved: int = 0
    sites: list[str] = field(default_factory=list)
    forks: dict[str, list[str]] = field(default_factory=dict)
    shadows: list[str] = field(default_factory=list)

    def findings(self) -> list[str]:
        """Unlisted forks, stale baseline entries and shadows, as message lines."""
        out = [
            f"{name}: {'; '.join(sites)}" for name, sites in sorted(self.forks.items()) if name not in KNOWN_ENV_FORKS
        ]
        out += [
            f"{name}: listed in KNOWN_ENV_FORKS ({KNOWN_ENV_FORKS[name]}) but no longer forks -- delete the entry"
            for name in sorted(KNOWN_ENV_FORKS)
            if name not in self.forks
        ]
        return out + self.shadows

    def summary(self) -> str:
        """``checked N`` plus the result, so a clean run is distinguishable from a blind one."""
        found = len(self.findings())
        return (
            f"checked {self.env_reads} env fallback reads over {self.env_vars} vars "
            f"({self.registered_vars} registered; {self.unresolved} non-literal defaults skipped) "
            f"and {self.constants} module constants against {len(SSOT_CONSTANT_SOURCES)} SSOT modules: "
            + (f"{found} finding(s)" if found else "none found")
        )


def registry_defaults() -> dict[str, Any]:
    """name -> default for every spec in every ``env_registry*`` module (import-side-effect registration)."""
    import autobot_shared
    from autobot_shared.env_registry import REGISTRY

    for mod in pkgutil.iter_modules(autobot_shared.__path__):
        if mod.name.startswith("env_registry"):
            importlib.import_module(f"autobot_shared.{mod.name}")
    return {name: spec.default for name, spec in REGISTRY.items()}


def module_constants(source: str) -> dict[str, tuple[Any, int]]:
    """UPPER_CASE module-level ``NAME = <literal>`` -> (value, lineno); empty on a syntax error."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}
    out: dict[str, tuple[Any, int]] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            target, value = node.target, node.value
        else:
            continue
        if isinstance(target, ast.Name) and target.id.isupper() and isinstance(value, ast.Constant):
            out[target.id] = (value.value, node.lineno)
    return out


def _module_literals(tree: ast.Module) -> dict[str, Any]:
    """Every module-level ``NAME = <literal>`` (any case), for resolving a Name used as a default."""
    out: dict[str, Any] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            target, value = node.target, node.value
        else:
            continue
        if isinstance(target, ast.Name) and isinstance(value, ast.Constant):
            out[target.id] = value.value
    return out


def _os_imports(tree: ast.Module) -> tuple[set[str], set[str]]:
    """Local names bound by ``from os import getenv [as g]`` and ``from os import environ [as e]``."""
    getenvs: set[str] = set()
    environs: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "os" and node.level == 0:
            for alias in node.names:
                if alias.name == "getenv":
                    getenvs.add(alias.asname or "getenv")
                elif alias.name == "environ":
                    environs.add(alias.asname or "environ")
    return getenvs, environs


def _is_env_read(node: ast.Call, getenvs: set[str], environs: set[str]) -> bool:
    """``os.getenv``/``os.environ.get`` (via the sibling matcher) or their ``from os import`` spellings."""
    if _is_getenv_call(node):
        return True
    fn = node.func
    if isinstance(fn, ast.Name):
        return fn.id in getenvs
    return (
        isinstance(fn, ast.Attribute)
        and fn.attr == "get"
        and isinstance(fn.value, ast.Name)
        and fn.value.id in environs
    )


def extract_env_reads(source: str) -> tuple[list[tuple[str, Any, int]], int]:
    """``([(NAME, default, lineno)], unresolved)`` for every 2-argument env read in *source*.

    Covers ``os.getenv``, ``os.environ.get`` and the ``from os import getenv/environ`` spellings. A
    default that is a Name resolves only to a module-level literal in the SAME file; any other
    non-literal default is skipped and counted in ``unresolved`` rather than guessed at. A call
    carrying the ``ssot-config-exempt`` marker is skipped entirely.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return [], 0
    lines = source.splitlines()
    literals = _module_literals(tree)
    getenvs, environs = _os_imports(tree)
    out: list[tuple[str, Any, int]] = []
    unresolved = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or len(node.args) != 2 or not _is_env_read(node, getenvs, environs):
            continue
        name = _literal(node.args[0])
        if not isinstance(name, str):
            continue
        end = getattr(node, "end_lineno", node.lineno) or node.lineno
        if EXEMPT_MARKER in "\n".join(lines[node.lineno - 1 : end]):
            continue
        arg = node.args[1]
        default = _literal(arg)
        if default is None and isinstance(arg, ast.Name):
            default = literals.get(arg.id)
        if default is None:
            unresolved += 0 if (isinstance(arg, ast.Constant) and arg.value is None) else 1
            continue
        out.append((name, default, node.lineno))
    return out, unresolved


def fork_sites(reads: list[tuple[Any, str]], registry_default: Any, registered: bool) -> list[str]:
    """Describe the disagreement among ``(fallback, "path:line")`` reads of one name; ``[]`` if they agree."""
    # A registry default of None declares no default: readers are compared only with each other.
    declared = registered and registry_default is not None
    first = reads[0][0]
    differs_among = any(values_disagree(value, first) for value, _ in reads[1:])
    differs_registry = declared and any(values_disagree(value, registry_default) for value, _ in reads)
    if not (differs_among or differs_registry):
        return []
    sites = [f"{value!r} at {where}" for value, where in reads]
    return sites + ([f"registry declares {registry_default!r}"] if declared else [])


def scan(repo_root: Path, files: list[Path], registry: dict[str, Any]) -> ScanResult:
    """Run (a) and (b) over *files* (absolute paths under *repo_root*) against *registry*."""
    result = ScanResult(registered_vars=0)
    ssot: dict[str, str] = {}
    for rel in SSOT_CONSTANT_SOURCES:
        source = repo_root / rel
        if not source.is_file():
            raise VacuousScan(f"{rel} is not in {repo_root} -- there are no SSOT constants to compare against")
        text = source.read_text(encoding="utf-8")
        ssot.update({name: rel for name in module_constants(text)})
    reads: dict[str, list[tuple[Any, str]]] = {}
    for path in files:
        rel_path = path.relative_to(repo_root).as_posix()
        if rel_path.split("/")[0] not in SCAN_ROOTS or rel_path.endswith("_test.py") or "/tests/" in rel_path:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        file_reads, unresolved = extract_env_reads(text)
        result.unresolved += unresolved
        for name, default, lineno in file_reads:
            reads.setdefault(name, []).append((default, f"{rel_path}:{lineno}"))
            result.sites.append(f"{rel_path}:{lineno}")
            result.env_reads += 1
        if rel_path not in SSOT_CONSTANT_SOURCES:
            for name, (_, lineno) in module_constants(text).items():
                result.constants += 1
                if name in ssot:
                    result.shadows.append(f"{rel_path}:{lineno}: {name} shadows the SSOT constant in {ssot[name]}")
    result.env_vars = len(reads)
    result.registered_vars = sum(1 for name in reads if name in registry)
    for name, name_reads in reads.items():
        sites = fork_sites(name_reads, registry.get(name), name in registry)
        if sites:
            result.forks[name] = sites
    return result


def sweep_env_forks(repo_root: Path, registry: dict[str, Any]) -> ScanResult:
    """The ONE population: every git-tracked ``.py`` under *repo_root*, scanned against *registry*.

    ``check_env_forks`` and the reach declaration both call this, so the entrypoint's floor check and the
    declaration's ``verify_floor`` count the same set of reads.
    """
    return scan(repo_root, [repo_root / rel for rel in tracked_paths(repo_root, "*.py")], registry)


def collect_env_forks(argv: list[str], repo_root: Path) -> tuple[int, list[str]]:
    """``(env fallback reads examined, finding lines)`` for ``check_env_forks``; *argv* is unused.

    The reads examined are the population :data:`FORK_READ_FLOOR` is a floor over, so the harness
    refuses (exit 2) a sweep that lost its roots instead of reporting "none found" over nothing.
    """
    del argv  # full-repo only: a fork is two files disagreeing, so a changed-files run would miss it
    result = sweep_env_forks(repo_root, registry_defaults())
    logging.getLogger(HOOK_ID).info("[%s] %s", HOOK_ID, result.summary())
    return result.env_reads, [f"[{HOOK_ID}] {line}" for line in result.findings()]


def summary(n: int) -> str:
    """The closing line, naming every kind of finding :meth:`ScanResult.findings` can carry."""
    return (
        f"[{HOOK_ID}] {n} finding(s): an env var read with differing fallbacks, a fallback that "
        "disagrees with the env registry default, or a module constant shadowing an SSOT constant. "
        "Read the value from one place (the registry / ssot_config) instead of re-stating it (#18094)."
    )
