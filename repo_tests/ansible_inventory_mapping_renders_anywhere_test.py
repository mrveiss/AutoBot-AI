# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An inventory mapping must render from any play, not only from a real host (#15731).

Ansible resolves a variable WHOLE. Reading one plain-string key of a mapping
forces every sibling to render too -- so a single host-var template anywhere in
the mapping makes the entire mapping unreadable from any play that does not
have that host var.

`autobot.services.frontend` was ``"http://{{ frontend_host }}:{{ frontend_port }}"``
and `frontend_host` is defined only in `production.yml`. Every controller play
reading `autobot.base_dir` -- a literal string sitting three keys above it --
died with "'frontend_host' is undefined" before its first task, and that took
out every self-update on the fleet.

Nothing consumed `autobot.services` in any spelling. It was breaking plays for
no reader at all, which is why it moved to a top-level `autobot_services` rather
than being deleted: the URLs are still the derived SSOT form, they simply must
not sit inside a mapping that controller plays read.

This binds the general property. A guard that only pinned `autobot.services`
would pass the moment someone adds a host template to a different key.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

_REPO_ROOT = Path(__file__).resolve().parents[1]
_GROUP_VARS = _REPO_ROOT / "autobot-slm-backend" / "ansible" / "inventory" / "group_vars"

#: A Jinja reference to something other than a sibling of the same mapping.
#: `{{ foo }}` in an inventory value is a host var or another group var; either
#: way it is not guaranteed to exist for a controller play.
_TEMPLATE = re.compile(r"\{\{\s*[^}]+\}\}")

#: Mappings a controller play reads a plain key out of. These are the ones a
#: stray template makes unreadable, and the reason this guard is narrow rather
#: than banning templates from inventory altogether -- most inventory values
#: SHOULD be host-derived; they just must not share a mapping with values that
#: controller plays depend on.
_CONTROLLER_READ_MAPPINGS = ("autobot",)

#: Floor on the sweep's REACH -- group_vars files parsed, never findings.
_MIN_GROUP_VARS_FILES = 1


def _group_vars_documents() -> list[tuple[str, dict]]:
    found = []
    for path in sorted(_GROUP_VARS.rglob("*.yml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(document, dict):
            found.append((path.name, document))
    return found


def _templated_leaves(node, trail: str = "") -> list[str]:
    if isinstance(node, dict):
        return [leaf for k, v in node.items() for leaf in _templated_leaves(v, f"{trail}.{k}" if trail else str(k))]
    if isinstance(node, list):
        return [leaf for item in node for leaf in _templated_leaves(item, trail)]
    if isinstance(node, str) and _TEMPLATE.search(node):
        return [f"{trail} = {node}"]
    return []


def test_the_sweep_reaches_the_group_vars_it_claims_to() -> None:
    """Reach before findings -- an empty walk must fail, not pass silently."""
    documents = _group_vars_documents()
    assert len(documents) >= _MIN_GROUP_VARS_FILES, (
        f"parsed only {len(documents)} group_vars files (floor {_MIN_GROUP_VARS_FILES}) — it has stopped reading"
    )


def test_controller_read_mappings_carry_no_host_templates() -> None:
    """The property, not the instance: any templated leaf breaks the whole mapping."""
    offenders: list[str] = []
    for name, document in _group_vars_documents():
        for mapping_name in _CONTROLLER_READ_MAPPINGS:
            mapping = document.get(mapping_name)
            if isinstance(mapping, dict):
                offenders += [f"{name}: {mapping_name}.{leaf}" for leaf in _templated_leaves(mapping)]

    assert not offenders, (
        "these sit inside a mapping that controller plays read a plain key out of, so reading ANY "
        "key of it renders these too and the play dies where the host var is undefined (#15731). "
        "Move them to a sibling top-level variable:\n  " + "\n  ".join(offenders)
    )
