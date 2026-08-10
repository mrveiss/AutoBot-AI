# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""File-path fallback for core plugins whose package path is not importable (#10294).

Core plugins live in hyphenated directories (`plugins/core-plugins/image-generation-plugin/`)
but declare underscored entry points (`plugins.core_plugins.image_generation_plugin.main`).
Nothing maps one to the other — no `__init__.py`, no namespace package, no path hook — so
`importlib.import_module(entry_point)` raises `ModuleNotFoundError`.

A `spec_from_file_location` fallback was added for this and did not work, which is easy to
misread. It located the right file. What failed was `exec_module`, because the plugin's OWN
imports also reference `plugins.core_plugins.*` — and those parent packages exist in no
`sys.modules`. The observable symptom was:

    File-path fallback failed for 'plugins.core_plugins.image_generation_plugin.main'
      at plugins/core-plugins/image-generation-plugin/main.py: No module named 'plugins.core_plugins'

i.e. the loader reporting that it could not load a file it had already found. So the fix is
not "load from the located file" (already done) but "make the dotted path resolvable for the
module's own imports".
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from autobot_shared.plugin_sdk.loader import PluginLoader

_ENTRY = "plugins.core_plugins.demo_plugin.main"
_PARENTS = ("plugins", "plugins.core_plugins", "plugins.core_plugins.demo_plugin")


@pytest.fixture(autouse=True)
def _clean_sys_modules():
    """Leave sys.modules exactly as found — these tests install packages into it."""
    touched = (_ENTRY, "plugins.core_plugins.demo_plugin.helper", *_PARENTS)
    saved = {k: sys.modules.get(k) for k in touched}
    yield
    for key, value in saved.items():
        if value is None:
            sys.modules.pop(key, None)
        else:
            sys.modules[key] = value


def _make_plugin(root: Path, *, module_name: str = "main", with_sibling_import: bool = False) -> Path:
    """Build a core-plugin tree: hyphenated dirs, no __init__.py anywhere."""
    plugin_dir = root / "core-plugins" / "demo-plugin"
    plugin_dir.mkdir(parents=True)

    (plugin_dir / "helper.py").write_text("ANSWER = 42\n", encoding="utf-8")

    body = "VALUE = 'loaded'\n"
    if with_sibling_import:
        # The import that broke exec_module: absolute, via the dotted path that
        # does not exist on disk under that name.
        body = "from plugins.core_plugins.demo_plugin.helper import ANSWER\n\nVALUE = ANSWER\n"
    (plugin_dir / f"{module_name}.py").write_text(body, encoding="utf-8")
    return plugin_dir


def test_the_dotted_entry_point_is_genuinely_unimportable(tmp_path):
    """Pins the premise. If this ever starts working the fallback is dead code."""
    _make_plugin(tmp_path)
    with pytest.raises(ModuleNotFoundError):
        __import__(_ENTRY)


def test_a_plugin_with_no_internal_imports_loads(tmp_path):
    """The case the original fallback already handled."""
    plugin_dir = _make_plugin(tmp_path)
    loader = PluginLoader(plugin_dirs=[tmp_path])

    module = loader._import_from_file(_ENTRY, plugin_dir)

    assert module is not None
    assert module.VALUE == "loaded"


def test_a_plugin_that_imports_its_own_sibling_loads(tmp_path):
    """#10294's actual bug: the file was found, exec_module then failed.

    This is what image-generation-plugin and video-generation-plugin hit — the
    loader logged "File-path fallback failed" for a file it had located.
    """
    plugin_dir = _make_plugin(tmp_path, with_sibling_import=True)
    loader = PluginLoader(plugin_dirs=[tmp_path])

    module = loader._import_from_file(_ENTRY, plugin_dir)

    assert module is not None, "the module's own absolute import must resolve"
    assert module.VALUE == 42


def test_the_parent_packages_point_at_the_real_hyphenated_directories(tmp_path):
    """The mapping is derived by walking up from the module file, never guessed —
    so a plugin dir that is not simply `name.replace('_','-')` still works."""
    plugin_dir = _make_plugin(tmp_path, with_sibling_import=True)
    loader = PluginLoader(plugin_dirs=[tmp_path])

    loader._import_from_file(_ENTRY, plugin_dir)

    assert sys.modules["plugins.core_plugins.demo_plugin"].__path__ == [str(plugin_dir)]
    assert sys.modules["plugins.core_plugins"].__path__ == [str(tmp_path / "core-plugins")]
    assert sys.modules["plugins"].__path__ == [str(tmp_path)]


def test_the_module_filename_comes_from_the_entry_point(tmp_path):
    """telemetry-prompt-middleware declares `...telemetry_prompt_middleware.plugin`
    and ships plugin.py, so a hardcoded main.py could never find it."""
    plugin_dir = _make_plugin(tmp_path, module_name="plugin")
    loader = PluginLoader(plugin_dirs=[tmp_path])

    module = loader._import_from_file("plugins.core_plugins.demo_plugin.plugin", plugin_dir)

    assert module is not None
    assert module.VALUE == "loaded"


def test_a_failed_exec_withdraws_the_synthetic_packages(tmp_path):
    """Half a package tree left behind would make the NEXT plugin's import
    resolve against a directory nobody chose."""
    plugin_dir = _make_plugin(tmp_path)
    (plugin_dir / "main.py").write_text("raise RuntimeError('boom')\n", encoding="utf-8")
    loader = PluginLoader(plugin_dirs=[tmp_path])

    assert loader._import_from_file(_ENTRY, plugin_dir) is None
    for name in _PARENTS:
        assert name not in sys.modules, f"{name} survived a failed load"
    assert _ENTRY not in sys.modules


def test_an_existing_real_package_is_not_replaced(tmp_path):
    """`plugins` may already be a genuine package. Overwriting it would redirect
    every later import in the process to the plugin tree."""
    plugin_dir = _make_plugin(tmp_path, with_sibling_import=True)
    sentinel = sys.modules["plugins"] = type(sys)("plugins")
    sentinel.__path__ = ["/somewhere/real"]

    PluginLoader(plugin_dirs=[tmp_path])._import_from_file(_ENTRY, plugin_dir)

    assert sys.modules["plugins"] is sentinel
    assert sys.modules["plugins"].__path__ == ["/somewhere/real"]


def test_the_real_core_plugins_import_through_the_fallback():
    """End-to-end against the shipped tree, not a fixture.

    Both plugins named in #10294 logged "File-path fallback failed" before this.
    They import here — recognising the CLASS afterwards is a separate defect
    (the plugins subclass a second copy of BasePlugin), tracked in #13677.
    """
    repo_root = Path(__file__).resolve().parents[2]
    plugins_root = repo_root / "plugins"
    if not (plugins_root / "core-plugins").is_dir():
        pytest.skip("core-plugins tree not present")

    loader = PluginLoader(plugin_dirs=[plugins_root])
    for name in ("image-generation-plugin", "video-generation-plugin"):
        entry = f"plugins.core_plugins.{name.replace('-', '_')}.main"
        plugin_dir = plugins_root / "core-plugins" / name
        saved = {k: sys.modules.get(k) for k in (entry, *_PARENTS[:2])}
        try:
            module = loader._import_from_file(entry, plugin_dir)
            assert module is not None, f"{name} still fails the file-path fallback"
        finally:
            for key, value in saved.items():
                if value is None:
                    sys.modules.pop(key, None)
                else:
                    sys.modules[key] = value
