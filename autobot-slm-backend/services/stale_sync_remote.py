# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The only node access of the stale code-sync file cleanup: a read-only listing and a checked removal (#22033).

Candidate paths go to the node on STDIN, one per line, never inlined into the script (the lesson of
``ansible/roles/_shared/tasks/sync_deletions.yml``, whose realpath containment ``REMOVE_SCRIPT`` shares): a
hostile file name is data, never shell. Both scripts run as ``sudo -n /bin/bash -c`` over the key-only ssh the
key probe proved, with the old target as ``$1``. Listing writes nothing. Removal re-hashes each file and removes
it only when it still equals the approved git blob, is a regular file, is not a symlink, and no parent is a
symlink out of the root.
"""

from __future__ import annotations

import re
import shlex
from typing import Iterable

from autobot_shared.logging_manager import get_logger
from autobot_shared.slm_stale_file_actions import SSH_TIMEOUT_SECONDS
from models.database import Node
from services.backup_ssh import run_command
from services.node_ssh_key_probe import key_only_ssh_command
from services.ssh_utils import InvalidSshDestination
from services.stale_sync_targets import PresentFile, StaleFile, StaleListingError

logger = get_logger(__name__)

#: One line per path found: ``size<TAB>mtime<TAB>blob<TAB>relative path``. Read-only.
LIST_SCRIPT = r"""
root=$(realpath -e -- "$1") || exit 3
while IFS= read -r rel; do
  f="$root/$rel"
  [ -f "$f" ] && [ ! -L "$f" ] || continue
  [ "$(realpath -m -- "$f")" = "$f" ] || continue
  size=$(stat -c %s -- "$f") || continue
  mtime=$(stat -c %Y -- "$f") || continue
  blob=$({ printf 'blob %s\0' "$size"; cat -- "$f"; } | sha1sum | cut -d' ' -f1)
  printf '%s\t%s\t%s\t%s\n' "$size" "$mtime" "$blob" "$rel"
done
"""

#: Reads ``blob<TAB>relative path`` lines; one line per path: ``removed|refused|changed|absent|failed<TAB>path``.
REMOVE_SCRIPT = r"""
root=$(realpath -e -- "$1") || exit 3
while IFS=$'\t' read -r want rel; do
  f="$root/$rel"
  if [ ! -e "$f" ] && [ ! -L "$f" ]; then printf 'absent\t%s\n' "$rel"; continue; fi
  if [ -L "$f" ] || [ ! -f "$f" ] || [ "$(realpath -m -- "$f")" != "$f" ]; then
    printf 'refused\t%s\n' "$rel"; continue
  fi
  size=$(stat -c %s -- "$f")
  have=$({ printf 'blob %s\0' "$size"; cat -- "$f"; } | sha1sum | cut -d' ' -f1)
  if [ "$have" != "$want" ]; then printf 'changed\t%s\n' "$rel"; continue; fi
  if rm -f -- "$f"; then printf 'removed\t%s\n' "$rel"; else printf 'failed\t%s\n' "$rel"; fi
done
"""

_LISTED = re.compile(r"^(\d+)\t(\d+)\t([0-9a-f]{40})\t(.+)$")
_REMOVED = re.compile(r"^(removed|refused|changed|absent|failed)\t(.+)$")


def _command(node: Node, script: str, root: str) -> list[str]:
    """``ssh ... sudo -n /bin/bash -c <script> <name> <root>``; raises StaleListingError for a bad destination."""
    try:
        base = key_only_ssh_command(node)
    except InvalidSshDestination as exc:
        raise StaleListingError("the node's SSH destination is invalid") from exc
    return [*base, f"sudo -n /bin/bash -c {shlex.quote(script)} stale-sync {shlex.quote(root)}"]


async def _run(node: Node, script: str, root: str, lines: Iterable[str]) -> str:
    """The script's output; raises StaleListingError unless it ran to completion on the node."""
    stdin = "".join(f"{line}\n" for line in lines).encode("utf-8")
    ok, output = await run_command(_command(node, script, root), timeout=int(SSH_TIMEOUT_SECONDS), stdin=stdin)
    if not ok:
        logger.warning("Stale-file script on node %s did not complete: %s", node.node_id, output[:200])
        raise StaleListingError("the node did not answer the stale-file check (ssh failed or timed out)")
    return output


async def stat_candidates(node: Node, root: str, rel_paths: list[str]) -> list[PresentFile]:
    """Those of *rel_paths* that are regular files under *root* on the node, with size, mtime and blob id."""
    if not rel_paths:
        return []
    asked, found = set(rel_paths), []
    for line in (await _run(node, LIST_SCRIPT, root, rel_paths)).splitlines():
        match = _LISTED.match(line)
        if match and match.group(4) in asked:
            found.append(PresentFile(match.group(4), int(match.group(1)), int(match.group(2)), match.group(3)))
    return found


async def remove_files(node: Node, root: str, files: list[StaleFile]) -> dict[str, str]:
    """Remove *files* from *root* on the node, each only while it still equals its approved blob.

    Returns {relative path: removed | refused | changed | absent | failed}; a path the node did not answer for
    is ``failed``, never assumed removed.
    """
    if not files:
        return {}
    wanted = {item.path for item in files}
    results = {path: "failed" for path in wanted}
    output = await _run(node, REMOVE_SCRIPT, root, (f"{item.blob}\t{item.path}" for item in files))
    for line in output.splitlines():
        match = _REMOVED.match(line)
        if match and match.group(2) in wanted:
            results[match.group(2)] = match.group(1)
    return results
