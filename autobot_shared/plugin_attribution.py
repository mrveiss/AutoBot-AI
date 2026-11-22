# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Which plugin's code is registering hooks and tools right now (#19302).

The plugin host sets this around ``initialize()``. Hook and tool registries read it so a registration made
inside plugin code is recorded against that plugin, and a plugin cannot register under another's name.

Limit: this is cooperative attribution. A registration made outside the context (from a thread executor,
or a callback that runs later) carries no owner. Plugins run in-process and are trusted code (see
``docs/developer/THREAT_MODEL.md``); this makes honest mistakes visible, it is not a sandbox.
"""

from contextlib import AbstractContextManager, contextmanager, nullcontext
from contextvars import ContextVar
from typing import Iterator

_registering_plugin: ContextVar[str | None] = ContextVar("registering_plugin", default=None)


@contextmanager
def registering_for_plugin(plugin_name: str) -> Iterator[None]:
    """Attribute every hook and tool registered inside the block to *plugin_name*."""
    token = _registering_plugin.set(plugin_name)
    try:
        yield
    finally:
        _registering_plugin.reset(token)


def scope_for(plugin_name: str | None) -> AbstractContextManager[None]:
    """Attribute the block to *plugin_name*; a no-op for a host callback with no plugin."""
    return registering_for_plugin(plugin_name) if plugin_name else nullcontext()


def current_plugin() -> str | None:
    """The plugin whose code is running the registration, or None outside plugin context."""
    return _registering_plugin.get()


def resolve_owner(claimed: str | None) -> str | None:
    """The owner to record: *claimed* outside plugin context; inside it the plugin itself.

    Raises:
        PermissionError: inside plugin context, *claimed* names a different plugin.
    """
    current = current_plugin()
    if current is None or claimed in (None, current):
        return current or claimed
    raise PermissionError(f"plugin '{current}' cannot register under the name '{claimed}'")
