# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Plugin Loader

Dynamic plugin discovery and loading system.

Issue #730 - Plugin SDK for extensible tool architecture.
Issue #6970 - Validate declared hooks against HOOK_REGISTRY on load.
Issue #6971 - Raise PluginLoadError for missing required env vars.
Issue #10294 - File-path fallback for hyphenated core-plugin directories.
Issue #11522 - Validate config_schema (JSON Schema Draft 2020-12) and config at load.
"""

import importlib
import importlib.util
import json
import logging
import os
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, List, Tuple, Type

import jsonschema

from .base import BasePlugin, PluginLoadError, PluginManifest, PluginRegistry, PluginStatus
from .hooks import validate_hook_names
from .registry import get_registry

logger = logging.getLogger(__name__)

_DRAFT_202012_VALIDATOR = jsonschema.Draft202012Validator


def _validate_config_schema(plugin_name: str, config_schema: Dict[str, Any]) -> None:
    """Raise PluginLoadError if config_schema is not a valid JSON Schema Draft 2020-12.

    Issue #11522 — structural validation at load time.
    """
    try:
        _DRAFT_202012_VALIDATOR.check_schema(config_schema)
    except jsonschema.SchemaError as exc:
        raise PluginLoadError(
            f"Plugin '{plugin_name}': config_schema is not valid JSON Schema " f"(Draft 2020-12): {exc.message}"
        ) from exc


def _validate_config_against_schema(
    plugin_name: str,
    config: Dict[str, Any],
    config_schema: Dict[str, Any],
) -> None:
    """Raise PluginLoadError if config does not conform to config_schema.

    Issue #11522 — field-level error detail on non-conforming config.
    """
    validator = _DRAFT_202012_VALIDATOR(config_schema)
    errors = list(validator.iter_errors(config))
    if not errors:
        return

    # Value-free, field-level messages: name the field and the violated
    # constraint but never echo the submitted value (#11522 review m-4) —
    # these strings surface in HTTP 422 responses via validate_plugin_config.
    def _fmt(err: jsonschema.ValidationError) -> str:
        path = ".".join(str(p) for p in err.path) or "<root>"
        if err.validator == "required":
            # 'required' messages name schema-declared fields, never submitted
            # values — keep them for actionable diagnostics.
            return f"  - {path}: {err.message}"
        return f"  - {path}: violates '{err.validator}' constraint"

    field_messages = [_fmt(err) for err in errors]
    raise PluginLoadError(
        f"Plugin '{plugin_name}': config does not conform to config_schema:\n" + "\n".join(field_messages)
    )


def validate_plugin_config(plugin_name: str, config: Dict[str, Any], config_schema: Dict[str, Any]) -> None:
    """Public seam: validate a plugin *config* against its *config_schema*.

    For use outside the SDK (e.g. the plugin-manager API config-update path).
    The schema itself is already structurally validated at plugin load time,
    so only config conformance is checked here.  Raises PluginLoadError with
    field-level, value-free messages.
    """
    if not config_schema:
        return
    _validate_config_against_schema(plugin_name, config, config_schema)


class PluginLoader:
    """
    Plugin discovery and loading system.

    Discovers plugins from filesystem, loads manifests, and instantiates plugins.
    """

    def __init__(self, plugin_dirs: List[Path] | None = None) -> None:
        """
        Initialize plugin loader.

        Args:
            plugin_dirs: List of directories to search for plugins
        """
        self.plugin_dirs = plugin_dirs or []
        self.registry = PluginRegistry()
        # Maps plugin name -> directory containing its plugin.json (set during discover_plugins)
        self._manifest_dirs: Dict[str, Path] = {}

    def discover_plugins(self) -> List[PluginManifest]:
        """
        Discover all plugins in configured directories.

        Returns:
            List of plugin manifests found
        """
        manifests = []

        for plugin_dir in self.plugin_dirs:
            if not plugin_dir.exists():
                logger.warning("Plugin directory does not exist: %s", plugin_dir)
                continue

            # Look for plugin.json files
            for manifest_file in plugin_dir.rglob("plugin.json"):
                try:
                    with open(manifest_file, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    manifest = PluginManifest(**data)
                    # Remember where on disk this plugin lives (needed for file-path fallback)
                    self._manifest_dirs[manifest.name] = manifest_file.parent
                    manifests.append(manifest)
                    logger.info("Discovered plugin: %s v%s", manifest.name, manifest.version)

                except Exception as e:
                    logger.error(
                        "Failed to load manifest %s: %s",
                        manifest_file,
                        e,
                        exc_info=True,
                    )

        return manifests

    async def load_plugin(self, manifest: PluginManifest, config: Dict | None = None) -> BasePlugin | None:
        """
        Load a plugin from its manifest.

        Args:
            manifest: Plugin manifest
            config: Plugin configuration

        Returns:
            Loaded plugin instance or None on failure
        """
        try:
            # Check dependencies
            missing_deps = self._check_dependencies(manifest)
            if missing_deps:
                logger.error(
                    "Cannot load plugin %s: missing dependencies %s",
                    manifest.name,
                    missing_deps,
                )
                return None

            # Validate declared hooks against HOOK_REGISTRY (GH#6970)
            if manifest.hooks:
                validate_hook_names(manifest.hooks, plugin_name=manifest.name)

            # Check required environment variables (GH#6971)
            missing_required, missing_optional = self._check_required_env(manifest)
            if missing_required:
                raise PluginLoadError(
                    f"Cannot load plugin '{manifest.name}': " f"required env vars not set: {missing_required}"
                )
            if missing_optional:
                logger.info(
                    "Plugin %s loaded with optional env vars unset: %s",
                    manifest.name,
                    missing_optional,
                )

            # GH#11522: validate config_schema and supplied config at load time
            if manifest.config_schema:
                _validate_config_schema(manifest.name, manifest.config_schema)
                if config:
                    _validate_config_against_schema(manifest.name, config, manifest.config_schema)

            # Import plugin module — pass on-disk directory for file-path fallback (#10294)
            plugin_dir = self._manifest_dirs.get(manifest.name)
            plugin_class = self._import_plugin_class(manifest.entry_point, plugin_dir)
            if not plugin_class:
                return None

            # Instantiate plugin
            plugin = plugin_class(manifest, config)

            # Initialize plugin
            await plugin.initialize()
            plugin.status = PluginStatus.LOADED

            # Register with plugin registry and unified registry
            self.registry.register(plugin)
            get_registry().register(manifest)

            logger.info("Loaded plugin: %s v%s", manifest.name, manifest.version)
            return plugin

        except Exception as e:
            logger.error("Failed to load plugin %s: %s", manifest.name, e, exc_info=True)
            return None

    async def unload_plugin(self, name: str) -> bool:
        """
        Unload a plugin.

        Args:
            name: Plugin name

        Returns:
            True if successfully unloaded
        """
        try:
            plugin = self.registry.get_plugin(name)
            if not plugin:
                logger.warning("Plugin not found: %s", name)
                return False

            # Shutdown plugin
            await plugin.shutdown()
            plugin.status = PluginStatus.UNLOADED

            # Unregister from plugin registry and unified registry
            self.registry.unregister(name)
            get_registry().unregister(name)

            logger.info("Unloaded plugin: %s", name)
            return True

        except Exception as e:
            logger.error("Failed to unload plugin %s: %s", name, e, exc_info=True)
            return False

    async def reload_plugin(self, name: str) -> bool:
        """
        Reload a plugin.

        Args:
            name: Plugin name

        Returns:
            True if successfully reloaded
        """
        try:
            plugin = self.registry.get_plugin(name)
            if not plugin:
                logger.warning("Plugin not found: %s", name)
                return False

            # Use plugin's reload method
            await plugin.reload()

            logger.info("Reloaded plugin: %s", name)
            return True

        except Exception as e:
            logger.error("Failed to reload plugin %s: %s", name, e, exc_info=True)
            return False

    def _check_dependencies(self, manifest: PluginManifest) -> List[str]:
        """
        Check if plugin dependencies are loaded.

        Args:
            manifest: Plugin manifest

        Returns:
            List of missing dependency names
        """
        missing = []
        for dep in manifest.dependencies:
            if not self.registry.get_plugin(dep):
                missing.append(dep)
        return missing

    def _check_required_env(self, manifest: PluginManifest) -> Tuple[List[str], List[str]]:
        """
        Check which env vars declared by the manifest are unset.

        Returns:
            Tuple of (missing_required, missing_optional) env var names.
            An env var set to an empty string is treated as missing.
        """
        missing_required: List[str] = []
        missing_optional: List[str] = []
        for env in manifest.required_env:
            if not os.environ.get(env.name):
                if env.required:
                    missing_required.append(env.name)
                else:
                    missing_optional.append(env.name)
        return missing_required, missing_optional

    def get_env_status(self, plugin_name: str) -> Dict[str, Dict[str, object]] | None:
        """
        Return per-env-var configuration status for a loaded plugin.

        SECURITY: response NEVER contains env var values, only the
        configured/missing boolean and the manifest metadata.

        Args:
            plugin_name: Name of a loaded plugin

        Returns:
            Dict mapping env-var name to status dict, or None if the
            plugin is not loaded.
        """
        plugin = self.registry.get_plugin(plugin_name)
        if plugin is None:
            return None
        return {
            env.name: {
                "configured": bool(os.environ.get(env.name)),  # ssot-config-exempt: dynamic env var name
                "secret": env.secret,
                "required": env.required,
                "description": env.description,
                "docs_url": env.docs_url,
                "obtain_steps": list(env.obtain_steps),
            }
            for env in plugin.manifest.required_env
        }

    def _import_plugin_class(self, entry_point: str, plugin_dir: Path | None = None) -> Type[BasePlugin] | None:
        """
        Import plugin class from entry point.

        Tries ``importlib.import_module(entry_point)`` first.  When that raises
        ``ModuleNotFoundError`` (e.g. core-plugins whose hyphenated directory is not
        importable as a Python package -- GH#10294), falls back to loading the
        ``main.py`` from the plugin's on-disk directory via
        ``importlib.util.spec_from_file_location``, mirroring the approach used in
        ``autobot-backend/api/_video_providers_loader.py``.

        Args:
            entry_point: Python module path (e.g., 'plugins.core_plugins.image_generation_plugin.main')
            plugin_dir:  Directory that contains plugin.json -- used for the file-path fallback.

        Returns:
            Plugin class or None on failure
        """
        module = None

        try:
            module = importlib.import_module(entry_point)
        except ModuleNotFoundError as exc:
            logger.debug(
                "importlib.import_module(%r) failed (%s); attempting file-path fallback",
                entry_point,
                exc,
            )
            module = self._import_from_file(entry_point, plugin_dir)

        if module is None:
            logger.error("Failed to import plugin module: %s", entry_point)
            return None

        # Look for Plugin class or class with 'Plugin' suffix
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if isinstance(attr, type) and issubclass(attr, BasePlugin) and attr is not BasePlugin:
                return attr

        logger.error("No plugin class found in module: %s", entry_point)
        return None

    def _import_from_file(self, entry_point: str, plugin_dir: Path | None) -> ModuleType | None:
        """
        File-path fallback for plugins whose directory name is not importable
        (e.g. ``core-plugins/image-generation-plugin`` -- hyphen prevents normal import).

        Resolves ``main.py`` relative to *plugin_dir* (preferred) or by translating
        the underscored entry-point path back to the hyphenated on-disk path inside
        any configured plugin_dirs.  Registers the module under *entry_point* in
        ``sys.modules`` so intra-plugin relative imports and dataclasses resolve.

        GH#10294 -- mirrors ``autobot-backend/api/_video_providers_loader.py``.
        """
        import sys

        # Candidate file paths, most-canonical first.
        candidates: List[Path] = []

        # The module filename is the entry point's LAST segment, not always
        # "main". telemetry-prompt-middleware declares
        # `...telemetry_prompt_middleware.plugin` and ships plugin.py, so a
        # hardcoded main.py could never find it (#10294).
        module_filename = f"{entry_point.rsplit('.', 1)[-1]}.py"

        # 1. Use the stored manifest directory directly (most reliable).
        if plugin_dir is not None:
            candidates.append(plugin_dir / module_filename)

        # 2. Derive the path from the entry_point by mapping underscores -> hyphens
        #    for each segment, then looking inside every configured plugin_dir.
        #    entry_point like "plugins.core_plugins.image_generation_plugin.main"
        #    -> segments ["plugins", "core_plugins", "image_generation_plugin", "main"]
        #    -> on-disk path: <plugin_root>/core-plugins/image-generation-plugin/main.py
        parts = entry_point.split(".")
        # Drop the leading "plugins" segment and the trailing "main" module name.
        inner_parts = parts[1:-1] if len(parts) >= 3 else parts[:-1]
        hyphenated_parts = [p.replace("_", "-") for p in inner_parts]
        rel_path = Path(*hyphenated_parts) / module_filename if hyphenated_parts else None

        for base_dir in self.plugin_dirs:
            if rel_path is not None:
                candidates.append(base_dir / rel_path)

        for path in candidates:
            if not path.exists():
                continue
            synthesised: List[str] = []
            try:
                spec = importlib.util.spec_from_file_location(entry_point, path)
                if spec is None or spec.loader is None:
                    continue
                module = importlib.util.module_from_spec(spec)
                # #10294: locating the file was never the whole problem. The
                # module's OWN imports reference `plugins.core_plugins.*`, and
                # those parent packages exist in no sys.modules, so exec_module
                # raised ModuleNotFoundError even though the right file had been
                # found — which read as "the fallback failed to load the file".
                synthesised = self._synthesise_parent_packages(entry_point, path)
                # Register before exec so intra-plugin dataclasses/relative refs resolve.
                sys.modules[entry_point] = module
                spec.loader.exec_module(module)  # type: ignore[union-attr]
                logger.info("Loaded plugin module %r from %s (file-path fallback)", entry_point, path)
                return module
            except Exception as exc:
                logger.warning("File-path fallback failed for %r at %s: %s", entry_point, path, exc)
                sys.modules.pop(entry_point, None)
                for name in synthesised:
                    sys.modules.pop(name, None)
                continue

        return None

    def _synthesise_parent_packages(self, entry_point: str, module_path: Path) -> List[str]:
        """Make `plugins.core_plugins.<name>` importable for the plugin's own imports.

        The entry point is a dotted path whose packages do not exist on disk
        under those names — `core_plugins` is the directory `core-plugins`, and
        neither carries an ``__init__.py``. A plugin that imports its own
        siblings by absolute path therefore fails at ``exec_module`` even when
        the loader has located exactly the right file (#10294).

        Each parent gets a namespace module whose ``__path__`` points at the
        matching real directory, walked up from the module file so the hyphen /
        underscore mapping never has to be guessed.

        Returns the names created, so a failed exec can withdraw them rather
        than leave half a package tree behind for the next import to trip on.
        """
        import sys

        parents = entry_point.split(".")[:-1]
        if not parents:
            return []

        # Walk up from the module's own directory: the innermost package is the
        # plugin dir, its parent is core-plugins, and so on.
        directories: List[Path] = []
        current = module_path.parent
        for _ in parents:
            directories.append(current)
            current = current.parent
        directories.reverse()

        created: List[str] = []
        for depth, _part in enumerate(parents):
            name = ".".join(parents[: depth + 1])
            if name in sys.modules:
                continue
            package = ModuleType(name)
            package.__path__ = [str(directories[depth])]  # type: ignore[attr-defined]
            package.__package__ = name
            sys.modules[name] = package
            created.append(name)

        if created:
            logger.debug("Synthesised namespace packages for %s: %s", entry_point, created)
        return created

    def get_loaded_plugins(self) -> Dict[str, BasePlugin]:
        """Get all loaded plugins."""
        return self.registry.get_all_plugins()

    def get_plugin_info(self, name: str) -> Dict | None:
        """Get plugin information."""
        plugin = self.registry.get_plugin(name)
        return plugin.get_info() if plugin else None
