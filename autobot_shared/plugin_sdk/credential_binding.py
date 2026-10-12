# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Bind a scoped credential resolver to a plugin's verified origin (#18094).

``manifest.name`` is self-declared in the plugin's own ``plugin.json``, so a name
match alone proves nothing: a community-installed plugin can claim any name. A
resolver is therefore handed over only when the plugin's resolved on-disk
directory lies inside a trusted built-in root. This is origin binding, not
isolation: plugins run in-process, so a loaded plugin can still read
``os.environ`` and module state directly.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Callable, Dict, Iterable

logger = logging.getLogger(__name__)


def _inside(path: Path, root: Path) -> bool:
    """True when the resolved ``path`` is ``root`` or beneath it (symlinks followed)."""
    real = path.resolve()
    base = root.resolve()
    return real == base or base in real.parents


def bound_resolver(
    name: str,
    plugin_dir: Path | None,
    resolvers: Dict[str, Callable[[str], str]],
    trusted_roots: Iterable[Path],
) -> Callable[[str], str] | None:
    """Return the resolver mapped to ``name`` only if ``plugin_dir`` is under a trusted root.

    Otherwise ``None``; a mapped name that fails the origin check is logged at
    WARNING with the plugin name and the reason, never any credential value.
    """
    resolver = resolvers.get(name)
    if resolver is None:
        return None
    if plugin_dir is None:
        reason = "plugin directory unknown"
    elif not any(_inside(plugin_dir, root) for root in trusted_roots):
        reason = "plugin is not under a trusted built-in root"
    else:
        return resolver
    logger.warning("credential resolver withheld from plugin %r: %s", name, reason)
    return None


class CredentialUnavailableError(RuntimeError):
    """A host resolver refused a credential it holds but cannot read (#18094).

    Defined here, in the SDK, so a plugin can tell a refusal apart from any other
    error without importing the backend; the backend's ``VaultKeyUnavailableError``
    subclasses it. The message carries the reason and the key's name, never a value.
    """


class CredentialSlot:
    """A plugin module's host-injected credential resolver -- one implementation for every plugin (#18094).

    The host loader installs a name-scoped resolver; standalone (none installed) a
    key is read from the environment by name, as before. A refusal from the
    resolver propagates as :class:`CredentialUnavailableError`.
    """

    def __init__(self) -> None:
        self._resolver: Callable[[str], str] | None = None

    def set(self, resolver: Callable[[str], str] | None) -> None:
        """Install (or, with ``None``, clear) the resolver."""
        self._resolver = resolver

    def read(self, name: str) -> str:
        """The key *name* via the resolver, else the environment; ``""`` when unset."""
        if self._resolver is not None:
            return self._resolver(name)
        return os.environ.get(name, "")
