#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""CLI wrapper around services.sync_deletions (#16310).

Called by ``ansible/roles/_shared/tasks/sync_deletions.yml`` with
``delegate_to: localhost`` -- it runs on the controller (the SLM), which
holds the git checkout every role's synchronize task deploys from, right
after that task succeeds. It never touches a filesystem: it only decides
which component-relative paths are safe to delete, and ansible's own
``ansible.builtin.file: state=absent`` loop removes them on the target
(co-located or remote -- one mechanism for both, #16310 owner decision).

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
"error": null}``. Exits 1 (and sets "error") when the plan could not be
computed -- ansible must treat that as a failed task, never as an empty
delete list, which is the no-data-loss rule in reverse: silence must never
read as "nothing to do".
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.sync_deletions import DeletionPlan, compute_bootstrap_plan, compute_deletion_plan  # noqa: E402


def _read_present_paths(path: str) -> list[str]:
    with open(path, encoding="utf-8") as handle:
        return [line.strip() for line in handle if line.strip()]


async def _run(args: argparse.Namespace) -> DeletionPlan:
    if args.mode == "diff":
        return await compute_deletion_plan(args.source_dir, args.repo_root, args.previous_commit, args.new_commit)
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

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    plan = asyncio.run(_run(args))
    # noqa: print -- stdout IS the interface: ansible's command module captures
    # it and `| from_json`s the result. autobot-slm-backend/scripts/ is not in
    # CLI_OUTPUT_ROOTS (only the repo-root scripts/ is), so this needs the
    # explicit exemption rather than the automatic one.
    print(json.dumps({"delete": plan.delete, "kept": plan.kept, "error": plan.error}))  # noqa: print
    return 1 if plan.error else 0


if __name__ == "__main__":
    sys.exit(main())
