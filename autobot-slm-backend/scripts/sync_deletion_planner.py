#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""CLI wrapper around services.sync_deletions (#16310).

Called by ``ansible/roles/_shared/tasks/sync_deletions.yml`` with
``delegate_to: localhost`` -- it runs on the controller (the SLM), which
holds the git checkout every role's synchronize task deploys from, right
after that task succeeds. It never touches a filesystem: it only decides
which component-relative paths are safe to delete, and a `realpath`-checked
shell step removes them on the target (co-located or remote -- one
mechanism for both, #16310 owner decision), refusing anything that resolves
outside the target root.

#16310 review round 4, 3(b), accepted residual limitation: a filename
containing a literal newline splits into two lines in the ``find`` ->
ansible -> heredoc transport this CLI's output feeds. This fails SAFE (the
real file is left in place, never deleted) rather than being re-plumbed to
a NUL-separated transport end to end -- see the ansible task file's header
for the full reasoning.

Two modes:

    diff       Both commits known (the target's own marker was slurped).
               python3 sync_deletion_planner.py diff \\
                   --repo-root /opt/autobot/code_source \\
                   --source-dir /opt/autobot/code_source/autobot-backend \\
                   --previous-commit <sha> --new-commit <sha>

    bootstrap  No marker exists yet for this target (first run under this
               feature). Residual risk: a file deleted from git long ago and
               put back on the host by other means since would ALSO satisfy
               "tracked once, absent now" and be proposed for deletion --
               accepted by the owner for the one-time bootstrap only (#16310).
               python3 sync_deletion_planner.py bootstrap \\
                   --repo-root /opt/autobot/code_source \\
                   --source-dir /opt/autobot/code_source/autobot-backend \\
                   --new-commit <sha> --present-file /tmp/present-paths.txt

Prints one JSON object to stdout: ``{"delete": [...], "kept": [...],
"error": null, "bootstrap_required": false}``. Exits 1 (and sets "error")
when the plan could not be computed -- ansible must treat that as a failed
task, never as an empty delete list, which is the no-data-loss rule in
reverse: silence must never read as "nothing to do".

#16310 review round 12, N6: ``diff`` mode exits 0 with
``bootstrap_required: true`` (never "error") when ``--previous-commit`` is
unknown to this clone (a force-push or a re-clone moved history out from
under a target whose marker still names the old commit) -- the caller then
runs ``bootstrap`` mode instead, the same one-time mode used when no marker
exists at all, rather than repeating a fatal error on every run forever.

    ensure-full-history   Unshallow --repo-root if it is a shallow clone,
               through the same scrubbed-env `run_git` helper every other
               mode uses. Called once per pre-flight code_source fetch,
               before any component's diff/bootstrap plan -- #16310's other
               fix: a bootstrap plan computed against a shallow clone is not
               just incomplete, `git log --diff-filter=AR` over a
               one-commit history finds almost nothing to delete and that
               empty, error-free plan still gets recorded as done.
               python3 sync_deletion_planner.py ensure-full-history \\
                   --repo-root /opt/autobot/code_source
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# The backend root alone is not enough: importing `services.git_subprocess` runs
# `services/__init__.py`, which imports AuthService -> `autobot_shared.auth.jwt_core`.
# `autobot_shared` lives at the REPO root, one level above the backend root, so a
# backend-root-only path raised ModuleNotFoundError and aborted the [PRE-FLIGHT]
# unshallow task -- failing every code-sync run (#17452). Backend root precedes the
# repo root for the same reason dump_openapi.py gives: the backend package must win
# over any repo-root shim of the same name.
_SCRIPT = Path(__file__).resolve()
for _path in (str(_SCRIPT.parents[2]), str(_SCRIPT.parents[1])):
    if _path in sys.path:
        sys.path.remove(_path)
    sys.path.insert(0, _path)

from services.git_subprocess import ensure_full_history  # noqa: E402
from services.sync_deletions import DeletionPlan, compute_bootstrap_plan, compute_deletion_plan  # noqa: E402


def _read_present_paths(path: str) -> list[str]:
    with open(path, encoding="utf-8") as handle:
        return [line.strip() for line in handle if line.strip()]


async def _run(args: argparse.Namespace) -> DeletionPlan:
    if args.mode == "diff":
        return await compute_deletion_plan(args.source_dir, args.repo_root, args.previous_commit, args.new_commit)
    if args.mode == "ensure-full-history":
        ok, message = await ensure_full_history(args.repo_root)
        return DeletionPlan(error=None if ok else message)
    present_paths = _read_present_paths(args.present_file)
    return await compute_bootstrap_plan(args.source_dir, args.repo_root, args.new_commit, present_paths)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="mode", required=True)

    diff_parser = sub.add_parser("diff", help="Both commits known -- git-diff-based plan.")
    diff_parser.add_argument("--repo-root", required=True)
    diff_parser.add_argument("--source-dir", required=True)
    diff_parser.add_argument("--previous-commit", required=True)
    diff_parser.add_argument("--new-commit", required=True)

    bootstrap_parser = sub.add_parser("bootstrap", help="No marker yet -- one-time plan from a present-files list.")
    bootstrap_parser.add_argument("--repo-root", required=True)
    bootstrap_parser.add_argument("--source-dir", required=True)
    bootstrap_parser.add_argument("--new-commit", required=True)
    bootstrap_parser.add_argument("--present-file", required=True)

    ensure_parser = sub.add_parser("ensure-full-history", help="Unshallow --repo-root if it is a shallow clone.")
    ensure_parser.add_argument("--repo-root", required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    plan = asyncio.run(_run(args))
    # noqa: print -- stdout IS the interface: ansible's command module captures
    # it and `| from_json`s the result. autobot-slm-backend/scripts/ is not in
    # CLI_OUTPUT_ROOTS (only the repo-root scripts/ is), so this needs the
    # explicit exemption rather than the automatic one.
    print(  # noqa: print
        json.dumps(
            {
                "delete": plan.delete,
                "kept": plan.kept,
                "error": plan.error,
                "bootstrap_required": plan.bootstrap_required,
            }
        )
    )
    return 1 if plan.error else 0


if __name__ == "__main__":
    sys.exit(main())
