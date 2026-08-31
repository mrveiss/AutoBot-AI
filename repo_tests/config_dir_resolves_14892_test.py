# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#14892: ``PATH.CONFIG_DIR`` must name a directory that is actually there.

The constant read ``PROJECT_ROOT / "infrastructure" / "shared" / "config"`` for
its whole life. No project root — checkout or deployed install — has ever had an
``infrastructure/`` directory; the real one is ``autobot-infrastructure/``. So
every consumer resolved a path that could not exist, and because a missing
config is indistinguishable from a loaded one in most of them, nothing said so.

These assertions are the ones the original value would have failed on the day it
was written.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from autobot_shared.config_file_loading import SOURCE_BUILTIN_DEFAULTS, SOURCE_FILE, load_config_file
from autobot_shared.paths import project_root
from autobot_shared.ssot_constants import PATH

#: Files a consumer reaches through ``CONFIG_DIR`` that are present in a checkout.
#: Named individually so a rename fails here rather than silently shrinking the
#: sweep to nothing.
TRACKED_CONFIG_FILES = (
    "error_messages.yaml",
    "config.yaml",
    "security/compliance.yaml",
    "security/domain_security.yaml",
    "security/threat_detection.yaml",
)


class TestConfigDirIsReal:
    def test_config_dir_exists_in_a_checkout(self) -> None:
        assert PATH.CONFIG_DIR.is_dir(), (
            f"PATH.CONFIG_DIR resolves to {PATH.CONFIG_DIR}, which is not a directory. "
            "Nine consumers read config through this constant."
        )

    def test_config_dir_does_not_name_the_nonexistent_infrastructure_spelling(self) -> None:
        """The specific wrong value, asserted by name so it cannot come back."""
        assert "autobot-infrastructure" in PATH.CONFIG_DIR.parts, "the real dir is under autobot-infrastructure"
        assert "infrastructure" not in PATH.CONFIG_DIR.parts, "the bare `infrastructure` spelling is the #14892 bug"
        assert not (project_root() / "infrastructure").exists(), (
            "an `infrastructure/` directory now exists at the project root, so this "
            "test's premise changed — re-check which spelling CONFIG_DIR should use."
        )
        assert PATH.CONFIG_DIR == project_root() / "autobot-infrastructure" / "shared" / "config"

    def test_config_dir_derives_from_the_canonical_project_root(self) -> None:
        """#13149: not a second open-coded ``Path(__file__).parent.parent``.

        Asserted through ``project_root()`` so that running from a worktree —
        which is how all work here happens — resolves inside the worktree.
        """
        assert PATH.PROJECT_ROOT == project_root()
        assert PATH.CONFIG_DIR.is_relative_to(project_root())

    @pytest.mark.parametrize("relative", TRACKED_CONFIG_FILES)
    def test_each_tracked_config_file_is_reachable(self, relative: str) -> None:
        resolved = PATH.get_config_path(*relative.split("/"))
        assert resolved.is_file(), f"{relative} is not reachable through PATH.get_config_path: {resolved}"

    def test_the_tracked_file_population_is_not_empty(self) -> None:
        """Floor asserted separately from the parametrised sweep above.

        An empty ``TRACKED_CONFIG_FILES`` would collect zero test cases and the
        parametrised assertion would pass by never running — the failure mode
        that let a two-pathspec guard here pass for years on one empty half.
        """
        assert len(TRACKED_CONFIG_FILES) >= 5
        assert len(set(TRACKED_CONFIG_FILES)) == len(TRACKED_CONFIG_FILES), "duplicate entries inflate the floor"


class TestAMissIsDistinguishable:
    """#14892 AC3: a config that is absent must not read as one that was loaded."""

    def test_missing_file_reports_builtin_defaults_and_writes_nothing(self, tmp_path: Path) -> None:
        target = tmp_path / "security" / "absent.yaml"

        loaded = load_config_file(target, lambda: {"policy": "built-in"}, "test")

        assert loaded.source == SOURCE_BUILTIN_DEFAULTS
        assert loaded.loaded_from_file is False
        assert loaded.searched_path == target
        assert loaded.values == {"policy": "built-in"}
        # The decoy write is the half that made this permanent: the old miss
        # branch mkdir'd and dumped defaults into the path it had just failed to
        # read, so the next boot loaded them back and reported success.
        assert list(tmp_path.rglob("*")) == [], "a miss must not create anything on disk"

    def test_present_file_reports_the_file(self, tmp_path: Path) -> None:
        target = tmp_path / "present.yaml"
        target.write_text("policy: from-file\n", encoding="utf-8")

        loaded = load_config_file(target, lambda: {"policy": "built-in"}, "test")

        assert loaded.source == SOURCE_FILE
        assert loaded.loaded_from_file is True
        assert loaded.values == {"policy": "from-file"}

    def test_an_empty_file_is_not_treated_as_a_loaded_config(self, tmp_path: Path) -> None:
        """``yaml.safe_load`` returns None for an empty file — an empty policy."""
        target = tmp_path / "empty.yaml"
        target.write_text("# only a comment\n", encoding="utf-8")

        loaded = load_config_file(target, lambda: {"policy": "built-in"}, "test")

        assert loaded.source == SOURCE_BUILTIN_DEFAULTS
        assert loaded.values == {"policy": "built-in"}


#: Trees swept for consumers that name a config file through the constant.
#: Anchored on the project root so a worktree checks its own copy.
_SWEPT_TREES = ("autobot-backend", "autobot_shared", "autobot-infrastructure/shared/scripts")

#: Named through ``PATH.CONFIG_DIR`` but not present in the tree, each with the
#: issue that decides what the file should say. Pinned by name, and the count is
#: asserted below, so this is a ratchet and not a hole: a NEW absent filename
#: fails, and removing one of these without deleting its entry also fails.
#:
#: Both are enterprise-security policy files that no commit on any branch has
#: ever added, so ``SecurityPolicyManager`` and ``SSOIntegrationFramework`` have
#: only ever run their built-in defaults. #14892 made that distinguishable
#: (``config_source`` plus a WARNING naming the path); deciding what the
#: reviewed policy should actually contain is a security decision, not a
#: refactor, and is tracked separately in #15154.
_KNOWN_ABSENT_CONFIG_FILES = {
    "security/security_policies.yaml",
    "security/sso_config.yaml",
}


def _iter_named_config_files() -> list[tuple[Path, int, str]]:
    """Every config filename a consumer names literally through the constant.

    Parsed rather than grepped: this module and several consumers discuss these
    call shapes in prose, and a line regex cannot tell a docstring from a call.
    """
    root = project_root()
    found: list[tuple[Path, int, str]] = []
    for tree in _SWEPT_TREES:
        for source in sorted((root / tree).rglob("*.py")):
            if "node_modules" in source.parts:
                continue
            try:
                tree_ast = ast.parse(source.read_text(encoding="utf-8"))
            except SyntaxError:  # pragma: no cover - a broken file is another gate's failure
                continue
            for node in ast.walk(tree_ast):
                named = _named_config_file(node)
                if named is not None:
                    found.append((source, node.lineno, named))
    return found


def _is_path_attribute(node: ast.AST, attr: str) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == attr
        and isinstance(node.value, ast.Name)
        and node.value.id == "PATH"
    )


def _named_config_file(node: ast.AST) -> str | None:
    """``PATH.CONFIG_DIR / "x"`` or ``PATH.get_config_path("a", "b")`` -> ``"a/b"``."""
    if (
        isinstance(node, ast.BinOp)
        and isinstance(node.op, ast.Div)
        and _is_path_attribute(node.left, "CONFIG_DIR")
        and isinstance(node.right, ast.Constant)
        and isinstance(node.right.value, str)
    ):
        return node.right.value
    if isinstance(node, ast.Call) and _is_path_attribute(node.func, "get_config_path"):
        parts = [a.value for a in node.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]
        if len(parts) == len(node.args) and parts:
            return "/".join(parts)
    return None


class TestEveryNamedConfigFileExists:
    """#14892: a consumer must not name a config file that is not in the tree.

    ``utils/service_discovery.py`` resolved ``CONFIG_DIR / "services.json"``,
    stored it and never read it again. No commit on any branch has ever added a
    ``services.json``. That is the failure this guard makes loud: a path to a
    file that has never existed reads exactly like live configuration, and
    fixing the constant under it changes nothing at all.
    """

    def test_the_sweep_finds_consumers_at_all(self) -> None:
        """An empty sweep must go red rather than pass by asserting over nothing.

        Without this, deleting every consumer — or breaking the AST matcher, or
        renaming a swept tree — would leave the assertion below iterating an
        empty list and reporting success.
        """
        found = _iter_named_config_files()
        assert len(found) >= 5, f"the CONFIG_DIR consumer sweep found {len(found)} call sites; it has always found more"
        assert (
            len({relative for _, _, relative in found}) >= 5
        ), "distinct filenames, not one consumer matched five times"

    def test_no_consumer_names_a_config_file_that_is_absent(self) -> None:
        found = _iter_named_config_files()
        assert found, "empty sweep — see test_the_sweep_finds_consumers_at_all"
        missing = sorted(
            f"{source.relative_to(project_root())}:{lineno} names {relative!r}"
            for source, lineno, relative in found
            if relative not in _KNOWN_ABSENT_CONFIG_FILES and not PATH.get_config_path(*relative.split("/")).is_file()
        )
        assert not missing, "config files named through PATH.CONFIG_DIR that do not exist:\n" + "\n".join(missing)

    def test_the_known_absent_files_are_still_absent_and_still_named(self) -> None:
        """The exemption shrinks or fails; it never quietly outlives its cause."""
        named = {relative for _, _, relative in _iter_named_config_files()}
        for relative in sorted(_KNOWN_ABSENT_CONFIG_FILES):
            assert relative in named, f"{relative} is no longer named by any consumer — drop it from the exemption"
            assert not PATH.get_config_path(
                *relative.split("/")
            ).is_file(), (
                f"{relative} now exists — delete its entry from _KNOWN_ABSENT_CONFIG_FILES so the guard covers it"
            )
        assert len(_KNOWN_ABSENT_CONFIG_FILES) == 2, "this exemption is a ratchet: it may shrink, never grow"


class TestServiceDiscoveryKeepsNoDeadConfigPath:
    """#14892 AC3, the `services.json` consumer specifically.

    Asserted on the class rather than on the file text so that reintroducing the
    field under any spelling fails here.
    """

    def test_service_discovery_takes_no_config_file_argument(self) -> None:
        import inspect

        from utils.service_discovery import ServiceDiscovery

        parameters = set(inspect.signature(ServiceDiscovery.__init__).parameters)
        assert parameters == {"self"}, f"ServiceDiscovery.__init__ grew arguments again: {sorted(parameters)}"

    def test_service_discovery_stores_no_config_file_attribute(self) -> None:
        from utils.service_discovery import service_discovery

        assert not hasattr(service_discovery, "config_file"), (
            "ServiceDiscovery.config_file is back. It named "
            "CONFIG_DIR/services.json, a file no commit has ever added, and nothing read it."
        )


class TestEventManagerDistinguishesAMiss:
    """#14892 AC3, the `config.yaml` consumer.

    ``event_manager`` returned the same ``{"agent_behavior": {"debug_mode":
    False}}`` on a miss, on a parse error, and on a file that simply had no
    ``agent_behavior`` section — which ``config.yaml`` did not have for its whole
    life. Every one of those read as "debug is off", so the setting was
    unreachable and nothing said so.
    """

    def test_the_configured_key_is_present_in_the_checked_in_file(self) -> None:
        """The knob has to exist in the file the consumer actually reads."""
        loaded = load_config_file(PATH.CONFIG_DIR / "config.yaml", dict, "event manager")
        assert loaded.loaded_from_file, f"config.yaml was not read from {loaded.searched_path}"
        assert "agent_behavior" in loaded.values, (
            "config.yaml has no 'agent_behavior' section, so event_manager.debug_publish() "
            "can never be enabled through it (#14892)."
        )
        assert "debug_mode" in loaded.values["agent_behavior"]

    def test_a_miss_is_reported_as_builtin_defaults(self, tmp_path: Path) -> None:
        loaded = load_config_file(tmp_path / "absent.yaml", lambda: {"agent_behavior": {}}, "event manager")
        assert loaded.source == SOURCE_BUILTIN_DEFAULTS
        assert loaded.loaded_from_file is False

    def test_an_empty_config_file_does_not_become_a_none_config(self, tmp_path: Path) -> None:
        """``yaml.safe_load`` returns None here; the old body returned it verbatim
        and the next ``.get()`` raised ``AttributeError``."""
        target = tmp_path / "config.yaml"
        target.write_text("", encoding="utf-8")

        loaded = load_config_file(target, lambda: {"agent_behavior": {"debug_mode": False}}, "event manager")

        assert isinstance(loaded.values, dict)
        assert loaded.source == SOURCE_BUILTIN_DEFAULTS
