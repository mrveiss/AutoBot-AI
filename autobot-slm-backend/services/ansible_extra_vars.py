# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Serialise Ansible extra vars so caller-supplied values are never templated (#19005).

Ansible evaluates ``{{ ... }}`` inside an extra var's value when the variable is read, on the
controller. A value that came from outside (a heartbeat-reported service name, an operator's free
text) must therefore reach the playbook tagged ``!unsafe``. JSON cannot carry that tag, so the
extra-vars file is YAML. Stdlib and ``yaml`` only, so ``inventory_builder`` can import it freely.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, TextIO

import yaml


class _Unsafe(str):
    """A str dumped with the ``!unsafe`` tag."""


class _ExtraVarsDumper(yaml.SafeDumper):
    pass


_ExtraVarsDumper.add_representer(_Unsafe, lambda dumper, data: dumper.represent_scalar("!unsafe", str(data)))


def mark_unsafe(value: Any) -> Any:
    """Tag every string in *value* (recursing into mappings, lists and tuples) as Ansible-unsafe."""
    if isinstance(value, str):
        return _Unsafe(value)
    if isinstance(value, Mapping):
        return {k: mark_unsafe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [mark_unsafe(v) for v in value]
    return value


def dump_extra_vars(extra_vars: Mapping[str, Any], fh: TextIO, unsafe_keys: Iterable[str] = ()) -> None:
    """Write *extra_vars* to *fh* as YAML; values under *unsafe_keys* carry the ``!unsafe`` tag.

    Other keys (the merged secret-store values) are written plain, exactly as before.
    """
    unsafe = frozenset(unsafe_keys)
    marked = {k: (mark_unsafe(v) if k in unsafe else v) for k, v in extra_vars.items()}
    yaml.dump(marked, fh, Dumper=_ExtraVarsDumper, default_flow_style=False)
