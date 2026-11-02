#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every free-form shell block in the Ansible tree parses (#20693).

Ansible splits a free-form block with quote tracking, comments included, so one apostrophe in a shell
comment refuses the whole include when it loads, even if that task's ``when`` is false. That stopped
every update before its migrations for a day. It runs Ansible's own splitter, so it needs ansible-core,
which CI installs from constraints/ansible-core.txt.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterator, List, Tuple

import yaml
from ansible.parsing.splitter import split_args

FREE_FORM = {"shell", "command", "raw", "script"}
PREFIX = "ansible.builtin."
#: A tree that yields fewer blocks than this means the walk has stopped finding them.
MIN_BLOCKS = 100


def blocks_in(node: object) -> Iterator[Tuple[str, str]]:
    """(task name, free-form text) for every free-form module in a parsed YAML document."""
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(key, str) and key.removeprefix(PREFIX) in FREE_FORM and isinstance(value, str):
                yield str(node.get("name", "(unnamed)")), value
            yield from blocks_in(value)
    elif isinstance(node, list):
        for item in node:
            yield from blocks_in(item)


def parses(text: str) -> bool:
    try:
        split_args(text)
    except Exception:  # noqa: BLE001 - whatever the splitter raises, Ansible refuses the task
        return False
    return True


def check_tree(root: Path) -> Tuple[int, List[str]]:
    """(blocks examined, refusals). A file that isn't valid YAML is a refusal too: Ansible can't load it."""
    examined, refused = 0, []
    for path in sorted(p for p in root.rglob("*") if p.suffix in (".yml", ".yaml")):
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.constructor.ConstructorError:
            continue  # vault or other tags the safe loader doesn't know; not shell blocks
        except yaml.YAMLError as exc:
            refused.append(f"{path}: not valid YAML: {str(exc).splitlines()[0]}")
            continue
        for name, text in blocks_in(document):
            examined += 1
            if not parses(text):
                refused.append(
                    f"{path}: task {name!r}: Ansible can't split it; look for a stray quote, even in a comment"
                )
    return examined, refused


def main() -> int:
    if parses("# libpq's own variables\necho hi\n") or not parses("# the libpq variables\necho 'hi'\n"):
        print("control failed: the splitter no longer behaves as this check assumes")
        return 2
    root = Path(__file__).resolve().parents[2] / "autobot-slm-backend" / "ansible"
    examined, refused = check_tree(root)
    if examined < MIN_BLOCKS:
        print(f"only {examined} free-form blocks found under {root}: this check would be judging almost nothing")
        return 2
    for line in refused:
        print(line)
    print(f"{examined} free-form blocks examined, {len(refused)} refused")
    return 1 if refused else 0


if __name__ == "__main__":
    sys.exit(main())
