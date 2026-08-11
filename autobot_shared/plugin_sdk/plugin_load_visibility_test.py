# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""All 7 core plugins failed and it looked like "no plugins installed" (#13677).

Two independent defects, and the second is what made the first invisible.

**The plugins could not be recognised.** `docs/developer/PLUGIN_SDK.md` tells
authors to write ``from plugin_sdk.base import BasePlugin``, and every core
plugin does. That name resolves — autobot_shared is installed editable and
exposes ``plugin_sdk`` as a second top-level package over the same source — but
to a SECOND set of module objects. So ``plugin_sdk.base.BasePlugin`` and
``autobot_shared.plugin_sdk.base.BasePlugin`` are different classes, the loader's
``issubclass`` check against the canonical one returns False, and it reports
"No plugin class found in module" for a class sitting in the module it just
imported.

**Nothing totalled the result.** `startup()` logged discovery and per-plugin
successes, and the far commoner failure — ``load_plugin`` returning None rather
than raising — logged nothing at all at that level. A run where every plugin
failed produced the same shape of output as a healthy one, and a host with no
plugins produced the same shape as a host where all seven were broken.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from autobot_shared.plugin_sdk.loader import canonicalise_plugin_sdk
from autobot_shared.plugin_sdk.plugin_manager import PluginManager

_MANIFEST = """{
  "name": "%(name)s",
  "version": "1.0.0",
  "display_name": "%(name)s",
  "description": "fixture",
  "author": "test",
  "entry_point": "plugins.core_plugins.%(mod)s.main"
}"""

_PLUGIN_SOURCE = """
from plugin_sdk.base import BasePlugin


class FixturePlugin(BasePlugin):
    async def initialize(self):
        return None

    async def shutdown(self):
        return None
"""


@pytest.fixture(autouse=True)
def _fresh_plugin_modules():
    """Drop cached plugin modules between tests.

    The loader registers each plugin under its entry-point name in sys.modules,
    and these fixtures reuse entry points across tmp_paths — so without this a
    later test resolves a module built from an earlier test's directory and
    passes or fails for reasons that have nothing to do with it. Real startup
    gets a fresh process; the tests should too.
    """
    before = set(sys.modules)
    yield
    for name in set(sys.modules) - before:
        if name.startswith("plugins"):
            sys.modules.pop(name, None)

    # Also un-alias plugin_sdk, so the NEXT test starts from the split state a
    # real process starts in and the loader has to canonicalise for itself.
    # Without this the alias persisted process-wide after the first direct call
    # to canonicalise_plugin_sdk(), and deleting the loader's call left every
    # load test still passing — a guard that could not fail, in a file about
    # guards that cannot fail.
    for name in [n for n in sys.modules if n == "plugin_sdk" or n.startswith("plugin_sdk.")]:
        sys.modules.pop(name, None)


def _make_plugin(root: Path, name: str, source: str = _PLUGIN_SOURCE) -> None:
    d = root / name
    d.mkdir(parents=True)
    (d / "plugin.json").write_text(_MANIFEST % {"name": name, "mod": name.replace("-", "_")}, encoding="utf-8")
    (d / "main.py").write_text(source, encoding="utf-8")


class TestTheDocumentedImportIsRecognised:
    """The plugins were never wrong — the loader was."""

    def test_the_documented_import_is_what_plugins_actually_use(self):
        """If the SDK docs ever stop saying `from plugin_sdk...`, the
        canonicalisation below is solving a problem nobody has."""
        docs = Path(__file__).resolve().parents[2] / "docs" / "developer" / "PLUGIN_SDK.md"
        if not docs.is_file():
            pytest.skip("SDK docs not present")
        assert "from plugin_sdk.base import BasePlugin" in docs.read_text(encoding="utf-8")

    def test_canonicalise_binds_the_bare_name_to_the_same_module(self):
        import autobot_shared.plugin_sdk as canonical

        canonicalise_plugin_sdk()

        assert sys.modules["plugin_sdk"] is canonical

    def test_the_base_submodule_is_the_same_object_too(self):
        """Aliasing only the parent is not enough: a later `import
        plugin_sdk.base` would load a fresh module from the canonical path and
        reintroduce exactly the split this closes."""
        import autobot_shared.plugin_sdk.base as canonical_base

        canonicalise_plugin_sdk()

        assert sys.modules["plugin_sdk.base"] is canonical_base

    def test_a_class_using_the_documented_import_passes_issubclass(self):
        """The actual failing condition, reduced: this returned False, so the
        loader said "No plugin class found" for a class that was right there."""
        canonicalise_plugin_sdk()

        import plugin_sdk.base as documented
        from autobot_shared.plugin_sdk.base import BasePlugin as canonical

        assert documented.BasePlugin is canonical

        class Demo(documented.BasePlugin):  # type: ignore[misc, name-defined]
            pass

        assert issubclass(Demo, canonical)

    def test_the_loader_canonicalises_before_importing_a_plugin(self, tmp_path):
        """The LOADER must do this, not just the helper.

        Asserted directly on sys.modules rather than inferred from a successful
        load: whether an un-canonicalised import actually splits depends on how
        the package happens to be installed in the running environment, so a
        load-based assertion can pass for reasons unrelated to the fix. This
        fails the moment the loader stops calling canonicalise_plugin_sdk().
        """
        import autobot_shared.plugin_sdk as canonical
        from autobot_shared.plugin_sdk.loader import PluginLoader

        for name in [n for n in list(sys.modules) if n == "plugin_sdk" or n.startswith("plugin_sdk.")]:
            sys.modules.pop(name, None)
        assert "plugin_sdk" not in sys.modules, "precondition: the bare name must be unbound"

        # Any entry point will do — the binding happens before the import is tried.
        PluginLoader(plugin_dirs=[tmp_path])._import_plugin_class("nonexistent.module.main", tmp_path)

        assert sys.modules.get("plugin_sdk") is canonical, (
            "the loader must bind the documented plugin_sdk name to the canonical "
            "modules BEFORE importing a plugin, or the plugin subclasses a second "
            "copy of BasePlugin and fails issubclass (#13677)"
        )
        assert sys.modules.get("plugin_sdk.base") is sys.modules["autobot_shared.plugin_sdk.base"]


class TestLoadedNOfM:
    """0-of-7 and "no plugins installed" must not be the same observation.

    Plugin names are unique per test on purpose: `get_registry()` is a process
    global that keeps every successfully-registered plugin, so a shared name
    makes the second test fail with "Plugin already registered" — a failure
    about test wiring wearing the costume of a product bug.
    """

    @pytest.mark.asyncio
    async def test_a_total_failure_is_critical_not_a_quiet_stream(self, tmp_path, caplog):
        _make_plugin(tmp_path, "broken-plugin", source="raise RuntimeError('boom')\n")

        manager = PluginManager([tmp_path])
        with caplog.at_level("CRITICAL", logger="autobot_shared.plugin_sdk.plugin_manager"):
            await manager.startup()

        assert "loaded 0 of 1" in caplog.text
        assert manager.get_load_report()["loaded"] == 0

    @pytest.mark.asyncio
    async def test_a_partial_failure_warns_and_names_the_casualties(self, tmp_path, caplog):
        _make_plugin(tmp_path, "partial-good-plugin")
        _make_plugin(tmp_path, "partial-bad-plugin", source="raise RuntimeError('boom')\n")

        manager = PluginManager([tmp_path])
        with caplog.at_level("WARNING", logger="autobot_shared.plugin_sdk.plugin_manager"):
            await manager.startup()

        assert "loaded 1 of 2" in caplog.text
        assert "partial-bad-plugin" in caplog.text

    @pytest.mark.asyncio
    async def test_no_plugins_is_distinguishable_from_all_plugins_broken(self, tmp_path, caplog):
        """The headline confusion. An empty tree must NOT read as a failure, and
        a fully-broken tree must not read as an empty one."""
        manager = PluginManager([tmp_path])
        with caplog.at_level("INFO", logger="autobot_shared.plugin_sdk.plugin_manager"):
            await manager.startup()

        assert "no plugins discovered" in caplog.text
        assert "loaded 0 of" not in caplog.text
        assert manager.get_load_report() == {
            "discovered": 0,
            "loaded": 0,
            "failed": [],
            "conflicts": [],
            "started": True,
            "completed": True,
        }

    @pytest.mark.asyncio
    async def test_a_plugin_that_returns_none_is_reported(self, tmp_path, caplog):
        """`load_plugin` returns None far more often than it raises, and that
        branch logged nothing — the loader's own error names a module, not a
        plugin. Six of seven core plugins failed exactly here."""
        _make_plugin(tmp_path, "no-class-plugin", source="VALUE = 1\n")  # no BasePlugin subclass

        manager = PluginManager([tmp_path])
        with caplog.at_level("ERROR", logger="autobot_shared.plugin_sdk.plugin_manager"):
            await manager.startup()

        assert "no-class-plugin" in caplog.text
        assert "did not load" in caplog.text
        assert manager.get_load_report()["failed"] == ["no-class-plugin"]

    @pytest.mark.asyncio
    async def test_the_report_is_queryable_not_only_logged(self, tmp_path):
        """#13852's acceptance: a service running but not working must be
        distinguishable by something a check can QUERY. A log line is not that."""
        _make_plugin(tmp_path, "queryable-good-plugin")

        manager = PluginManager([tmp_path])
        await manager.startup()

        report = manager.get_load_report()
        assert report["discovered"] == 1
        assert report["loaded"] == 1
        assert report["started"] is True

    @pytest.mark.asyncio
    async def test_the_report_says_started_false_before_startup(self, tmp_path):
        """Otherwise "0 loaded" before startup is indistinguishable from
        "0 loaded, everything failed" — the same conflation one level up."""
        assert PluginManager([tmp_path]).get_load_report()["started"] is False


class TestTheSignalDoesNotManufactureFailures:
    """#13677 review: the live backend passes TWO overlapping plugin dirs.

    `lifespan.py` passes the deployed root AND the dev fallback — this issue's
    own title says "discovery runs twice". Undeduped, the second registration of
    a HEALTHY plugin raises "Plugin already registered", is swallowed by the
    loader, returns None, and lands in `failed`. The live config reported
    discovered=14 with five perfectly-loaded plugins named as casualties.

    A signal built to end a misdiagnosis must not manufacture one.
    """

    @pytest.mark.asyncio
    async def test_overlapping_plugin_dirs_do_not_invent_casualties(self, tmp_path, caplog):
        _make_plugin(tmp_path, "dedupe-good-plugin")

        manager = PluginManager([tmp_path, tmp_path])  # the shape lifespan.py uses
        with caplog.at_level("WARNING", logger="autobot_shared.plugin_sdk.plugin_manager"):
            await manager.startup()

        report = manager.get_load_report()
        assert report["discovered"] == 1, "the same plugin found twice is one plugin"
        assert report["loaded"] == 1
        assert report["failed"] == [], "a healthy plugin must never be named a casualty"
        assert "dedupe-good-plugin" not in caplog.text


class TestCanonicalisationDoesNotSplitTheRegistry:
    """#13677 review: binding the parent first re-created the #11636 split.

    A submodule imported during the alias loop that does `from plugin_sdk.X
    import ...` loads a fresh X from the canonical path AND sets it as an
    attribute on the parent — which is by then the canonical package. Repairing
    sys.modules does not repair that attribute, so
    `autobot_shared.plugin_sdk.registry` held a SECOND Registry class with its
    own singleton.
    """

    def test_parent_attributes_still_point_at_the_canonical_submodules(self):
        import autobot_shared.plugin_sdk as canonical

        canonicalise_plugin_sdk()

        clobbered = [
            name
            for name in ("base", "registry", "hooks", "loader")
            if f"autobot_shared.plugin_sdk.{name}" in sys.modules
            and getattr(canonical, name, None) is not sys.modules[f"autobot_shared.plugin_sdk.{name}"]
        ]
        assert not clobbered, f"canonicalisation replaced parent attributes: {clobbered} (#11636 regression)"

    def test_a_clobbered_parent_attribute_is_repaired(self):
        """The `setattr` is belt-and-braces and needs its own trigger.

        Filtering out the package's own tests removes TODAY's only clobber
        source, so without constructing the condition this guard passes whatever
        the loader does. Any future submodule doing `from plugin_sdk.X import
        ...` during the alias loop reintroduces it.
        """
        import autobot_shared.plugin_sdk as canonical

        real = sys.modules["autobot_shared.plugin_sdk.base"]
        impostor = type(sys)("autobot_shared.plugin_sdk.base")
        canonical.base = impostor  # what a mid-loop import does
        try:
            canonicalise_plugin_sdk()
            assert canonical.base is real, (
                "canonicalisation must re-assert the parent attribute, or "
                "autobot_shared.plugin_sdk.base holds a duplicate module (#11636)"
            )
        finally:
            canonical.base = real

    def test_the_package_tests_are_not_imported_into_the_process(self):
        """Importing them drags pytest into production (~100ms), and where
        pytest is absent the import fails and retries on every plugin."""
        canonicalise_plugin_sdk()

        assert not [m for m in sys.modules if m.startswith("plugin_sdk.") and m.endswith("_test")]


class TestTheReportCannotMisleadTheCaller:
    """#13677 review: three properties with no test at all."""

    @pytest.mark.asyncio
    async def test_a_crashed_discovery_is_not_an_empty_tree(self, tmp_path, monkeypatch):
        """Both report discovered=0, loaded=0. Deriving `started` from the
        manager's own flag made them byte-identical — "the subsystem delivered
        nothing" reading exactly like "there is nothing to deliver", which is
        this issue's headline defect one level up."""
        manager = PluginManager([tmp_path])
        monkeypatch.setattr(manager._loader, "discover_plugins", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        with pytest.raises(RuntimeError):
            await manager.startup()

        crashed = manager.get_load_report()

        empty_manager = PluginManager([tmp_path])
        await empty_manager.startup()
        empty = empty_manager.get_load_report()

        assert crashed != empty, "a crashed discovery must not look like an empty tree"
        assert crashed["completed"] is False
        assert empty["completed"] is True

    @pytest.mark.asyncio
    async def test_mutating_the_returned_report_cannot_corrupt_the_manager(self, tmp_path):
        """`dict()` is shallow, so a caller appending to report["failed"] was
        editing the manager's own tally."""
        _make_plugin(tmp_path, "copy-guard-plugin", source="raise RuntimeError('boom')\n")
        manager = PluginManager([tmp_path])
        await manager.startup()

        manager.get_load_report()["failed"].append("fabricated")

        assert "fabricated" not in manager.get_load_report()["failed"]

    @pytest.mark.asyncio
    async def test_a_name_claimed_by_two_directories_is_reported(self, tmp_path):
        """The blocker: manifest first-wins and directory last-wins meant one
        plugin's CODE ran under another's MANIFEST, reported as loaded 1 of 1
        with no failures. First still wins; it is no longer silent."""
        core = tmp_path / "core"
        community = tmp_path / "community"
        _make_plugin(core, "collide-demo")
        _make_plugin(community, "collide-demo")

        manager = PluginManager([core, community])
        await manager.startup()
        report = manager.get_load_report()

        assert report["conflicts"] == ["collide-demo"], "a shadowed plugin must be named"
        assert (
            manager._loader._manifest_dirs["collide-demo"].resolve() == (core / "collide-demo").resolve()
        ), "the directory kept must be the one whose manifest was registered"


class TestNonProductionModulesAreNeverImported:
    """The filter's rule, asserted where it can fail.

    Inlined in the alias loop it was untestable: the package has no conftest.py,
    so the `conftest` clause had no trigger and survived deletion with the whole
    suite green.
    """

    @pytest.mark.parametrize(
        "name",
        ["plugin_sdk_test", "loader_file_fallback_test", "test_something", "conftest"],
    )
    def test_non_production_names_are_skipped(self, name):
        from autobot_shared.plugin_sdk.loader import is_non_production_module

        assert is_non_production_module(name) is True

    @pytest.mark.parametrize("name", ["base", "registry", "hooks", "loader", "manifest_contract"])
    def test_real_submodules_are_not_skipped(self, name):
        """Over-filtering would silently drop a submodule from canonicalisation
        and reintroduce the split for anything importing it."""
        from autobot_shared.plugin_sdk.loader import is_non_production_module

        assert is_non_production_module(name) is False


class TestRepeatedDiscoveryDoesNotAccumulate:
    """#13988 review: two new lines survived deletion with the suite green.

    The `/plugins/discover` admin endpoint calls `discover_plugins()` repeatedly
    on a module-level singleton loader, so state that is never reset grows
    across calls — and `_manifest_dirs` growing past the manifest list
    re-establishes exactly the "these two must agree" invariant this work exists
    to enforce.
    """

    def test_conflicts_do_not_grow_across_calls(self, tmp_path):
        from autobot_shared.plugin_sdk.loader import PluginLoader

        core, community = tmp_path / "core", tmp_path / "community"
        _make_plugin(core, "repeat-demo")
        _make_plugin(community, "repeat-demo")
        loader = PluginLoader(plugin_dirs=[core, community])

        loader.discover_plugins()
        first = list(loader.name_conflicts)
        loader.discover_plugins()

        assert loader.name_conflicts == first, "conflicts accumulated across discovery calls"

    def test_manifest_dirs_never_outlives_its_manifests(self, tmp_path):
        """A plugin deleted from disk must not leave a stale directory entry —
        that entry is what the file-path import fallback resolves against."""
        import shutil

        from autobot_shared.plugin_sdk.loader import PluginLoader

        _make_plugin(tmp_path, "ghost-plugin")
        loader = PluginLoader(plugin_dirs=[tmp_path])
        assert loader.discover_plugins()

        shutil.rmtree(tmp_path / "ghost-plugin")
        manifests = loader.discover_plugins()

        assert manifests == []
        assert "ghost-plugin" not in loader._manifest_dirs

    @pytest.mark.asyncio
    async def test_mutating_conflicts_cannot_corrupt_the_manager(self, tmp_path):
        """Sibling of the `failed` copy guard — same shallow-dict hazard."""
        core, community = tmp_path / "core", tmp_path / "community"
        _make_plugin(core, "conflict-copy-demo")
        _make_plugin(community, "conflict-copy-demo")

        manager = PluginManager([core, community])
        await manager.startup()
        manager.get_load_report()["conflicts"].append("fabricated")

        assert "fabricated" not in manager.get_load_report()["conflicts"]

    @pytest.mark.asyncio
    async def test_three_directories_claiming_one_name_count_once(self, tmp_path):
        """`conflicts` names shadowed PLUGINS, not shadowed directories — a check
        doing len() read two where there is one."""
        dirs = []
        for name in ("a", "b", "c"):
            d = tmp_path / name
            _make_plugin(d, "tri-demo")
            dirs.append(d)

        manager = PluginManager(dirs)
        await manager.startup()

        assert manager.get_load_report()["conflicts"] == ["tri-demo"]

    def test_a_relative_plugin_dir_still_stores_an_absolute_path(self, tmp_path, monkeypatch):
        """lifespan.py's dev fallback passes two RELATIVE plugin dirs, so an
        unresolved parent let `_synthesise_parent_packages` walk off the top of
        the path — yielding repeated `.` and pointing a synthesised package's
        __path__ at the CWD. The nearest existing assertion calls .resolve() on
        its own left-hand side, so it structurally cannot catch this."""
        from autobot_shared.plugin_sdk.loader import PluginLoader

        _make_plugin(tmp_path / "core", "rel-demo")
        monkeypatch.chdir(tmp_path)
        loader = PluginLoader(plugin_dirs=[Path("core")])

        assert loader.discover_plugins()

        stored = loader._manifest_dirs["rel-demo"]
        assert stored.is_absolute(), f"stored plugin dir must be resolved, got {stored}"
