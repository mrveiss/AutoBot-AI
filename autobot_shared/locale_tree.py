# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Dotted-path view of a nested locale tree: the one ``flatten`` (#18954).

``scripts/lift_locale_translations.py`` and ``scripts/list_untranslated.py``
each defined ``flatten``. They agree on the key (the dotted path to the root)
and differ only on what counts as a leaf, so that is the parameter. Stdlib-only:
both callers are bare scripts.
"""

from __future__ import annotations

from typing import Any


def flatten(node: dict, prefix: str = "", *, only_strings: bool = False) -> dict[str, Any]:
    """Key every message in a locale tree by its dotted path to the root.

    Recurses only into dict values. Any other value is a leaf, so a list of
    strings stays one entry rather than becoming indexed children -- the
    lifting rule matches a message by its exact English text, and a list
    flattened into ``k.0``, ``k.1`` would compare fragments against whole
    strings and find nothing. With *only_strings*, a leaf that is not a string
    is dropped instead of kept.

        {"addNodeModal": {"cancel": "Cancel"}}  ->  {"addNodeModal.cancel": "Cancel"}

    The dotted path is what lets two apps' locale files be compared at all:
    ``en.json`` nests by feature, so only a path-keyed view can ask "does this
    app's ``addNodeModal.cancel`` have the same English text as some key in the
    main app's bundle".
    """
    flat: dict[str, Any] = {}
    for key, value in node.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            flat.update(flatten(value, path, only_strings=only_strings))
        elif isinstance(value, str) or not only_strings:
            flat[path] = value
    return flat
