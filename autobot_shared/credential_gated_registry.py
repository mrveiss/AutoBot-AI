# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared base for credential-gated provider registries (#11664).

Three subsystems (``integrations.capability_registry``,
``agent_loop.search.registry``, ``llm_shared.provider_registry``)
independently implemented the same pattern: a lazily-populated process-wide
singleton whose default entries are registered only when their
credentials/config are present, and whose lookups never raise on a missing
entry. This module holds the shared mechanics:

- :class:`CredentialGatedRegistry` — insertion-ordered name → entry store
  with never-raise lookups and replace-with-warning semantics.
- :func:`gated_registry_singleton` — the lazy-singleton accessor builder
  (reuses :func:`autobot_shared.singleton_factory.lazy_singleton`) that
  catches population failures so config issues never break callers.
"""

from __future__ import annotations

import logging
from typing import Callable, Dict, Generic, List, Optional, TypeVar

from autobot_shared.singleton_factory import lazy_singleton

logger = logging.getLogger(__name__)

T = TypeVar("T")
R = TypeVar("R", bound="CredentialGatedRegistry")


class CredentialGatedRegistry(Generic[T]):
    """Base registry: insertion-ordered name → entry store, never-raise lookups.

    Subclasses keep their public API (``register``/``resolve``/``get_provider``
    …) and layer domain behaviour (fallback chains, capability buckets, health
    caching) on top of these primitives. The store attribute is named
    ``_providers`` because that is the established name across the concrete
    registries (and their tests).
    """

    def __init__(self) -> None:
        """Create an empty registry."""
        self._providers: Dict[str, T] = {}

    def _store_entry(self, name: str, entry: T, *, kind: str = "provider") -> bool:
        """Store *entry* under *name*, warning when an entry is replaced.

        Args:
            name:  Registration name.
            entry: The entry to store.
            kind:  Human label used in the replacement warning.

        Returns:
            True when *name* was not previously registered.
        """
        is_new = name not in self._providers
        if not is_new:
            logger.warning("Replacing existing %s: %s", kind, name)
        self._providers[name] = entry
        return is_new

    def _get_entry(self, name: str) -> Optional[T]:
        """Return the entry registered under *name*, or None (never raises)."""
        return self._providers.get(name)

    def _entry_names(self) -> List[str]:
        """Return registered names in insertion order."""
        return list(self._providers)


def gated_registry_singleton(
    registry_factory: Callable[[], R],
    populate: Callable[[R], None],
    *,
    log: Optional[logging.Logger] = None,
    post_populate: Optional[Callable[[R], None]] = None,
) -> Callable[[], R]:
    """Build the process-wide lazy-singleton accessor for a registry.

    *populate* runs once, on first access, and registers the credential-gated
    default entries. Population failures are caught and logged so a (possibly
    partially populated) registry is always returned — config issues must
    never break callers. *post_populate* (e.g. a degraded-mode warning) runs
    after population, outside the guard.

    Reuses :func:`lazy_singleton`, so the returned accessor carries the
    standard ``reset()`` / ``set_for_test()`` test seams (#11635).
    """
    _log = log or logger

    def _build() -> R:
        registry = registry_factory()
        try:
            populate(registry)
        except Exception as exc:  # config issues must never break callers
            _log.warning("%s auto-registration failed: %s", type(registry).__name__, exc)
        if post_populate is not None:
            post_populate(registry)
        return registry

    return lazy_singleton(_build)
