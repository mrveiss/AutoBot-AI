# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Where the backend looks for plugins, and which of those places it trusts (#18094).

One definition for both plugin hosts: the startup ``PluginManager`` (``initialization/lifespan.py``)
and the API's ``PluginLoader`` (``plugin_manager.py``). They used to restate the search list each,
and only the API one handed credential resolvers over, so the plugin instance the backend actually
runs never received its resolver.

Search order is unchanged: deployed core, deployed community, then the development fallback
relative to the working directory. Trust is narrower than search: a credential resolver reaches
only a plugin under the deployed core root or this checkout's own ``plugins/core-plugins``. The
working-directory fallback is never trusted by its relative spelling, so starting the backend from
another directory cannot make that directory's ``plugins/core-plugins`` count as built-in.
"""

from __future__ import annotations

from pathlib import Path

from autobot_shared.ssot_config import config

_CORE = "core-plugins"
_COMMUNITY = "community-plugins"
#: This checkout's own ``plugins/`` directory, anchored to the source tree rather than the CWD.
_CHECKOUT_PLUGINS = Path(__file__).resolve().parents[1] / "plugins"


def plugin_search_dirs() -> list[Path]:
    """Directories a plugin host searches, first match wins on a name conflict."""
    root = config.path.plugins_path
    dev = Path("plugins")
    return [root / _CORE, root / _COMMUNITY, dev / _CORE, dev / _COMMUNITY]


def trusted_plugin_roots() -> list[Path]:
    """Built-in roots: a credential resolver is injected only into a plugin under one of these."""
    return [config.path.plugins_path / _CORE, _CHECKOUT_PLUGINS / _CORE]
