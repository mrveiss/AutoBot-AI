# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Find one concept defined under one name in several modules (#17312, #12771).

The duplication guard measures **clones** -- jscpd pairs of >=8 identical lines.
The expensive problem is **forks**: four modules that each define `ConfidenceLevel`
and have since drifted. Identical copies cannot disagree; drifted ones hand a
caller different behaviour depending on which import it reached, and they score
ZERO against a clone metric. #17312 measured exactly that: four redaction
implementations, 1164 lines, `Found 0 clones`.

This detector asks the question the clone metric cannot: **how many modules
define this name at top level?**

THE BOUNDARY (ratchet rule 1 -- state it where the reader meets the number)
--------------------------------------------------------------------------
Population: files returned by `git ls-files '*.py'` under ROOTS, minus EXCLUDED.
Predicate:  a *fork cluster* is one symbol NAME bound by a **module-level**
            `class`, `def` or `async def` in **two or more distinct files**.

What this detector is BLIND to, stated because a baseline cannot record what
its detector never saw:

  - **Methods.** Only module-level statements are read. Two classes with a
    `validate()` each are not a cluster; overriding is how classes work.
  - **Differently-named forks.** `redact_secrets` vs `scrub_credentials` are one
    concept and this never pairs them. Name identity is the whole signal, so
    the number is a FLOOR on canonical debt, never a total.
  - **Non-Python.** Vue/TS have their own canonical check (#7458).
  - **Conditional definitions.** A `def` inside `if TYPE_CHECKING:` or a
    try/except fallback is not module-level and is not counted.
  - **Re-exports.** `from x import Foo` does not define `Foo` here, correctly;
    a module that aliases and subclasses the SAME-NAMED class from
    `autobot_shared` is a binding of it and is not counted (#17312); a same-name
    class with any other base still is. `conftest.py` counts as a test file.
  - **Route handlers.** A function decorated `@router.get(...)` / `@app.post(...)`
    is excluded. Its name is local to its own router, so eight modules each
    defining `test_connection` are eight endpoints, not eight forks. Dropping
    this exclusion makes the top of the report entirely false positives -- it
    was the first thing the first run got wrong.

A cluster is a QUESTION, not a verdict. `ValidationResult` in seven modules may
be seven forks of one idea or seven unrelated local result types. The detector
says where to look and who the likely canonical is; a human decides.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # annotations only: nothing is imported at module load
    from autobot_shared.symbol_forks import ForkCluster as Cluster
    from autobot_shared.symbol_forks import ForkDefinition as Definition

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _shared():
    """The detector module, `autobot_shared.symbol_forks`, imported by its real name.

    Nothing touches `sys.path` at import time: a lint module that put the repo
    root at `sys.path[0]` shadowed `autobot-backend`'s own `scripts` package in
    any process that merely imported it, and broke collection on every shard
    (#18362). Run as a script, `tools/lint` is `sys.path[0]` and the root is not
    on the path, so the root is APPENDED here, only when the import would
    otherwise fail, and never ahead of an existing entry.
    """
    try:
        import autobot_shared.symbol_forks as shared
    except ModuleNotFoundError:
        sys.path.append(str(_REPO_ROOT))
        import autobot_shared.symbol_forks as shared
    return shared


#: Names the tests and importers read off this module, mapped to their home in
#: the shared detector (#18067). Resolved lazily by `__getattr__` below.
_SHARED_NAMES = {
    "ROOTS": "FORK_ROOTS",
    "EXCLUDED_PARTS": "FORK_EXCLUDED_PARTS",
    "EXCLUDED_NAMES": "FORK_EXCLUDED_NAMES",
    "Definition": "ForkDefinition",
    "Cluster": "ForkCluster",
    "is_test_file": "fork_is_test_file",
    "in_population": "fork_in_population",
    "is_route_handler": "fork_is_route_handler",
}


def load_exceptions(path: Path | None = None) -> list[dict]:
    """The recorded per-service exceptions; none if the record does not exist."""
    return _shared().fork_load_exceptions(path or EXCEPTIONS)


def validate_exception(entry: dict) -> list[str]:
    """The shared shape checks, plus: an exception links the issue that owns it (a URL or `#N`)."""
    problems = _shared().fork_validate_exception(entry)
    if entry.get("issue") and not _ISSUE_LINK.match(str(entry["issue"])):
        problems.append(f"exception {entry.get('symbol', '?')!r}: 'issue' {entry['issue']!r} is not an issue URL or #N")
    return problems


def apply_exceptions(clusters: dict, exceptions: list[dict]):
    """The shared application, validated with this ratchet's full checks."""
    return _shared().fork_apply_exceptions(clusters, exceptions, validate_exception)


def __getattr__(name: str):
    """PEP 562: the detector's names, without importing it at module load."""
    if name in _SHARED_NAMES:
        return getattr(_shared(), _SHARED_NAMES[name])
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


#: Floor on files successfully PARSED — not on files listed, and never on
#: findings. "0 new clusters" is meaningless if the sweep collapsed, and a
#: findings-based floor cannot tell a clean tree from a broken enumeration.
#: Measured 2026-10-20 (#18559) over the ten FORK_ROOTS: git lists 6,401 python
#: files and 3,396 survive `in_population` and are parsed. The three original
#: roots alone parse 3,031, so 3,200 sits MID-window: under the full reach and
#: above the narrowed one, which means dropping the seven roots added in #18559
#: fails this floor instead of passing it on the old roots alone.
MIN_FILES_PARSED = 3200

BASELINE = _REPO_ROOT / "repo_tests" / "symbol_fork_baseline.json"
EXCEPTIONS = _REPO_ROOT / "repo_tests" / "symbol_fork_exceptions.json"

#: A recorded exception links the issue that owns it: a full URL or `#N`.
_ISSUE_LINK = re.compile(r"^(https://github\.com/[\w.-]+/[\w.-]+/issues/\d+|#\d+)$")


def fork_scan_files() -> list[Path]:
    """`git ls-files` rather than a walk: untracked scratch files are not the tree."""
    shared = _shared()
    return shared.fork_tracked_python_files(_REPO_ROOT, shared.FORK_ROOTS)


def definitions_in(path: Path):
    """Module-level class/def bindings. Nested and conditional defs are out of scope."""
    return _shared().fork_definitions_in(path, _REPO_ROOT)


def find_clusters(paths: list[Path]):
    """Group module-level definitions by name; keep those bound in >=2 files.

    Returns the clusters AND the number of files successfully PARSED, which is
    what the vacuity floor binds to.
    """
    scan = _shared().fork_find_clusters(paths, _REPO_ROOT)
    return scan.clusters, scan.parsed


def canonical_candidate(cluster, import_counts: dict[str, int]):
    """The member a consolidation should merge INTO.

    Ranked by call sites first -- the copy most code already depends on is the
    one whose removal costs most. `autobot_shared` breaks ties because the
    project's rule 2 is to reuse from there. Size is the last resort and the
    weakest signal: the biggest copy may simply be the one that rotted most.
    """

    def rank(d: Definition) -> tuple[int, int, int]:
        return (
            import_counts.get(d.path, 0),
            1 if d.path.startswith("autobot_shared/") else 0,
            d.body_statements,
        )

    return max(cluster.definitions, key=rank)


def count_importers(paths: list[Path], names: set[str]) -> dict[str, dict[str, int]]:
    """For each name, how many files import it from each defining module.

    Counts `from <module> import <name>`. A bare `import module` followed by
    attribute use is NOT counted -- stated because it makes these numbers a
    floor, and a member with 0 here may still have callers.
    """
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for path in paths:
        try:
            tree = ast.parse((_REPO_ROOT / path).read_text(encoding="utf-8"))
        except (SyntaxError, OSError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or not node.module:
                continue
            for alias in node.names:
                if alias.name in names:
                    counts[alias.name][node.module] += 1
    return {k: dict(v) for k, v in counts.items()}


def module_of(path: str) -> str:
    """Dotted module path as an importer would spell it, for both root layouts."""
    stem = path[:-3] if path.endswith(".py") else path
    parts = stem.split("/")
    if parts[0] in ("autobot-backend", "autobot-slm-backend"):
        parts = parts[1:]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def importers_by_path(cluster: Cluster, by_module: dict[str, int]) -> dict[str, int]:
    """Re-key the per-module import counts onto each definition's file path."""
    return {d.path: by_module.get(module_of(d.path), 0) for d in cluster.definitions}


def format_cluster(cluster: Cluster, import_counts: dict[str, int]) -> str:
    """One cluster as a reviewable recommendation."""
    winner = canonical_candidate(cluster, import_counts)
    kinds = "/".join(sorted(cluster.kinds))
    lines = [
        f"{cluster.name}  ({kinds}, {len(cluster.definitions)} definitions" f"{', DRIFTED' if cluster.drifted else ''})"
    ]
    for d in cluster.definitions:
        mark = "  <- canonical candidate" if d is winner else ""
        lines.append(
            f"    {d.path}:{d.lineno}  {d.body_statements} stmts, {import_counts.get(d.path, 0)} importers{mark}"
        )
    lines.append(
        f"    FIX: merge the others into {winner.path} and re-point importers, or rename each to its own concept."
    )
    return "\n".join(lines)


def load_baseline() -> set[str]:
    if not BASELINE.exists():
        return set()
    return set(json.loads(BASELINE.read_text(encoding="utf-8"))["clusters"])


def write_baseline(names: set[str]) -> None:
    shared = _shared()
    BASELINE.write_text(
        json.dumps(
            {
                "_boundary": (
                    "Names bound by a MODULE-LEVEL class/def in >=2 tracked .py files under "
                    f"{list(shared.FORK_ROOTS)}, excluding {sorted(shared.FORK_EXCLUDED_PARTS)} dirs, test files, "
                    f"underscore-prefixed names, {sorted(shared.FORK_EXCLUDED_NAMES)} and classes that subclass the "
                    "same-named class from autobot_shared (a binding, not a second definition); "
                    "test files include conftest.py. "
                    "Methods, differently-named forks and non-Python are NOT seen -- "
                    "this count is a FLOOR on canonical debt. See tools/lint/check_symbol_forks.py."
                ),
                "_contract": (
                    "Shrink-only and BIDIRECTIONAL: a new name here fails CI, and an entry "
                    "that is no longer a fork cluster fails just as loudly. Delete it when "
                    "the duplication goes, or it tolerates whatever takes that name next "
                    "(#17312)."
                ),
                "clusters": sorted(names),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _report(clusters: dict[str, Cluster], paths: list[Path], limit: int) -> None:
    by_name = count_importers(paths, set(clusters))
    ranked = sorted(clusters.values(), key=lambda c: (-len(c.definitions), c.name))
    for cluster in ranked[:limit]:
        print(format_cluster(cluster, importers_by_path(cluster, by_name.get(cluster.name, {}))))
        print()
    print(f"{len(clusters)} fork clusters (showing {min(limit, len(clusters))}).")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", action="store_true", help="print clusters with canonical recommendations")
    parser.add_argument("--limit", type=int, default=25, help="clusters to print in --report")
    parser.add_argument("--freeze", action="store_true", help="rewrite the baseline from the current tree")
    parser.add_argument("--audit-baseline", action="store_true", help="list baseline entries that no longer exist")
    args = parser.parse_args(argv)

    paths = fork_scan_files()
    clusters, parsed = find_clusters(paths)
    clusters, exception_problems = apply_exceptions(clusters, load_exceptions())
    # Floor on files successfully PARSED, not on files git listed and not on
    # findings. `len(paths)` would clear this floor even if `in_population`
    # filtered everything out or every parse failed, which is the exact
    # collapse it exists to catch (CodeRabbit).
    if parsed < MIN_FILES_PARSED:
        print(
            f"check_symbol_forks: parsed only {parsed} of {len(paths)} listed python file(s), "
            f"expected at least {MIN_FILES_PARSED} — the sweep collapsed, so this run has no "
            "verdict to give. A floor on REACH, not on findings (#17312).",
            file=sys.stderr,
        )
        return 2

    if args.report:
        _report(clusters, paths, args.limit)
        return 0
    if args.freeze:
        write_baseline(set(clusters))
        print(f"froze {len(clusters)} clusters into {BASELINE.relative_to(_REPO_ROOT)}")
        return 0

    baseline = load_baseline()
    if args.audit_baseline:
        stale = sorted(baseline - set(clusters))
        for name in stale:
            print(f"STALE baseline entry (no longer a cluster): {name}")
        print(f"{len(stale)} stale of {len(baseline)}.")
        return 0

    # Shrink-only AND bidirectional: a NEW cluster fails, and a STALE entry
    # fails just as loudly. A baseline still listing a name nobody defines twice
    # any more is dead policy, and it silently tolerates whatever appears under
    # that name next. `--audit-baseline` reports staleness; this ENFORCES it.
    new = sorted(set(clusters) - baseline)
    stale = sorted(baseline - set(clusters))

    if new:
        by_name = count_importers(paths, set(new))
        print(f"{len(new)} NEW fork cluster(s) — one name, several module-level definitions (#17312):\n")
        for name in new:
            print(format_cluster(clusters[name], importers_by_path(clusters[name], by_name.get(name, {}))))
            print()
        print("Give the new concept its own name, or extend the existing definition instead of adding one.")
    if stale:
        print(
            f"{len(stale)} baseline entry(ies) are no longer fork clusters: {stale[:10]}\n"
            "Delete them. The list may only shrink, and it has to shrink HERE when the "
            "duplication is gone — otherwise the entry tolerates whatever takes that name next."
        )
    for problem in exception_problems:
        print(problem)
    if new or stale or exception_problems:
        return 1
    print(
        f"symbol forks: {len(clusters)} clusters over {parsed} parsed files "
        f"({len(paths)} listed), none new and none stale against a baseline of {len(baseline)}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
