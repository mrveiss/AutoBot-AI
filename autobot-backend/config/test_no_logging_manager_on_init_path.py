"""Regression test — GH#8766 / MVA-1465

Verifies that every module on the config-manager init path uses only stdlib
``logging``, not ``logging_manager.get_logger``.  Any module in this set that
imports ``logging_manager`` at module level recreates the circular chain:

    logging_manager → config → <submodule> → logging_manager  (circular)

This guard prevents the regression seen in GH#8765 (``retry_mechanism.py``).
"""

import ast
from pathlib import Path

import pytest

# All modules that are imported (directly or transitively) when
# ``from config.manager import ConfigManager`` executes.
BACKEND_ROOT = Path(__file__).parent.parent
CONFIG_ROOT = Path(__file__).parent

INIT_PATH_MODULES: list[Path] = [
    BACKEND_ROOT / "retry_mechanism.py",
    CONFIG_ROOT / "manager.py",
    CONFIG_ROOT / "__init__.py",
    CONFIG_ROOT / "async_ops.py",
    CONFIG_ROOT / "loader.py",
    CONFIG_ROOT / "file_watcher.py",
    CONFIG_ROOT / "model_config.py",
    CONFIG_ROOT / "service_config.py",
    CONFIG_ROOT / "settings.py",
    CONFIG_ROOT / "sync_ops.py",
    CONFIG_ROOT / "timeout_config.py",
    CONFIG_ROOT / "validation.py",
    CONFIG_ROOT / "defaults.py",
    CONFIG_ROOT / "registry.py",
    BACKEND_ROOT / "constants" / "path_constants.py",
    BACKEND_ROOT / "constants" / "threshold_constants.py",
    BACKEND_ROOT / "constants" / "network_constants.py",
]


def _has_toplevel_logging_manager_import(path: Path) -> bool:
    """Return True if the file imports logging_manager at module (top) level."""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    for node in ast.iter_child_nodes(tree):  # only top-level nodes
        if isinstance(node, ast.Import):
            for alias in node.names:
                if "logging_manager" in alias.name:
                    return True
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if "logging_manager" in module:
                return True
    return False


@pytest.mark.parametrize("module_path", INIT_PATH_MODULES, ids=lambda p: str(p.relative_to(BACKEND_ROOT)))
def test_no_logging_manager_import(module_path: Path) -> None:
    """Each config-manager init-path module must not import logging_manager at top level."""
    assert module_path.exists(), f"Module not found: {module_path}"
    assert not _has_toplevel_logging_manager_import(module_path), (
        f"{module_path.relative_to(BACKEND_ROOT)} imports logging_manager at module level. "
        "Use stdlib logging.getLogger(__name__) instead to avoid circular imports "
        "(GH#7765 pattern, GH#8766)."
    )
