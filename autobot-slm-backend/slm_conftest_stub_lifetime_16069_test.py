# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The conftest's module stubs must not outlive this directory (#16069).

`autobot-slm-backend/conftest.py` installs MagicMock stubs for imports its tests
cannot satisfy. They used to stay in `sys.modules` for the whole process — **50
keys**, measured — so a test collected afterwards that imported `sqlalchemy`,
`models`, `services` or `user_management` silently received a mock. That is the
failure mode worth naming: **a test passing against a MagicMock ORM is
indistinguishable from one passing against the real thing**, so the leak did not
announce itself as a failure anywhere.

It was not theoretical. Collecting `autobot-slm-backend/` before `repo_tests/`
produced 8 collection errors in `repo_tests/`; collecting `repo_tests/` alone
produced none. After the fix: 0 leaked keys, 5 errors, and 0 new ones — the
three that cleared were `api_key_has_scope_behaviour_16040`,
`config_dir_resolves_14892` and `sdk_response_parsing`.

These tests exercise the lifetime manager directly rather than driving pytest,
because the interesting behaviour is the identity-checked withdrawal, and a test
that spawned a nested pytest session would measure the harness more than the
rule.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

import pytest

from _slm_stub_lifetime import PLUGIN_NAME, StubLifetime, register


class _Node:
    """The slice of a pytest collector/item the manager reads."""

    def __init__(self, path: Path) -> None:
        self.path = path


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    root = tmp_path / "slm"
    (root / "services").mkdir(parents=True)
    return root


@pytest.fixture
def stub() -> ModuleType:
    module = ModuleType("acme_stub_16069")
    module.__spec__ = None  # type: ignore[assignment]
    return module


def _installed(name: str = "acme_stub_16069") -> bool:
    return name in sys.modules


@pytest.fixture(autouse=True)
def _no_residue() -> None:
    """This file must not leak the key it tests with — that would be ironic."""
    yield
    sys.modules.pop("acme_stub_16069", None)


class TestTheKeyIsWithdrawnOutsideTheTree:
    def test_a_node_outside_the_tree_drops_the_stub(self, tree: Path, stub: ModuleType) -> None:
        sys.modules["acme_stub_16069"] = stub
        manager = StubLifetime(tree, {"acme_stub_16069": stub})

        manager.pytest_collectstart(_Node(tree.parent / "repo_tests"))

        assert not _installed(), "the stub outlived its directory's collection"

    def test_a_node_inside_the_tree_restores_the_stub(self, tree: Path, stub: ModuleType) -> None:
        manager = StubLifetime(tree, {"acme_stub_16069": stub})

        manager.pytest_collectstart(_Node(tree / "services" / "x_test.py"))

        assert sys.modules.get("acme_stub_16069") is stub

    def test_the_run_phase_is_covered_too(self, tree: Path, stub: ModuleType) -> None:
        # Modules are imported during COLLECTION, but `patch("services.x.y")`
        # and in-function imports resolve during the RUN, so both hooks matter.
        manager = StubLifetime(tree, {"acme_stub_16069": stub})

        manager.pytest_runtest_setup(_Node(tree / "services" / "x_test.py"))
        assert sys.modules.get("acme_stub_16069") is stub

        manager.pytest_runtest_setup(_Node(tree.parent / "repo_tests" / "y_test.py"))
        assert not _installed()

    def test_the_directory_itself_counts_as_inside(self, tree: Path, stub: ModuleType) -> None:
        manager = StubLifetime(tree, {"acme_stub_16069": stub})

        manager.pytest_collectstart(_Node(tree))

        assert sys.modules.get("acme_stub_16069") is stub


class TestRemovalIsIdentityChecked:
    def test_a_real_module_that_replaced_the_stub_is_left_alone(self, tree: Path, stub: ModuleType) -> None:
        # The guard against over-correcting: deleting a module someone else
        # legitimately imported would be a worse bug than the leak.
        real = ModuleType("acme_stub_16069")
        sys.modules["acme_stub_16069"] = real
        manager = StubLifetime(tree, {"acme_stub_16069": stub})

        manager.pytest_collectstart(_Node(tree.parent / "elsewhere"))

        assert sys.modules.get("acme_stub_16069") is real, "a foreign module was deleted"

    def test_restoring_does_not_displace_what_arrived_meanwhile(self, tree: Path, stub: ModuleType) -> None:
        real = ModuleType("acme_stub_16069")
        sys.modules["acme_stub_16069"] = real
        manager = StubLifetime(tree, {"acme_stub_16069": stub})

        manager.pytest_collectstart(_Node(tree / "services"))

        assert sys.modules.get("acme_stub_16069") is real

    def test_dropping_twice_is_harmless(self, tree: Path, stub: ModuleType) -> None:
        sys.modules["acme_stub_16069"] = stub
        manager = StubLifetime(tree, {"acme_stub_16069": stub})

        manager.drop()
        manager.drop()

        assert not _installed()


class TestNodesWithoutAPath:
    def test_a_pathless_node_is_treated_as_foreign(self, tree: Path, stub: ModuleType) -> None:
        # A session-level collector has no path. Treating it as "ours" would
        # keep the stubs alive for the whole run, which is the original defect.
        sys.modules["acme_stub_16069"] = stub
        manager = StubLifetime(tree, {"acme_stub_16069": stub})

        manager.pytest_collectstart(_Node(None))  # type: ignore[arg-type]

        assert not _installed()


class TestRegistration:
    def test_it_registers_once_and_only_once(self, tree: Path) -> None:
        class _PM:
            def __init__(self) -> None:
                self.registered: list = []

            def hasplugin(self, name: str) -> bool:
                return any(n == name for _, n in self.registered)

            def register(self, plugin: object, name: str) -> None:
                self.registered.append((plugin, name))

        class _Config:
            def __init__(self) -> None:
                self.pluginmanager = _PM()

        config = _Config()
        register(config, tree, {})
        register(config, tree, {})

        assert [n for _, n in config.pluginmanager.registered] == [PLUGIN_NAME]

    def test_the_conftest_records_every_key_it_installs(self) -> None:
        # The registry is what the manager withdraws; a key installed without
        # being recorded is invisible to it, which is how `services` survived
        # the first version of this fix (it is built by hand, not via `_stub`).
        source = (Path(__file__).parent / "conftest.py").read_text(encoding="utf-8")
        installs = source.count("sys.modules[name] = mod") + source.count('sys.modules["services"] = _services_pkg')
        records = source.count("_INSTALLED_STUBS[")

        assert records >= installs, (
            f"{installs} install site(s) but only {records} record site(s) — an unrecorded "
            "stub cannot be withdrawn and will leak"
        )
