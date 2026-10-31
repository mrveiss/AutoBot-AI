# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The #18094 section-2 copied constants each have ONE home; a second definition fails.

Homes: the install root, the agent dir and the agent heartbeat interval in
``autobot_shared/fleet_constants.py``; the semantic similarity bands in
``autobot-backend/code_intelligence/similarity_thresholds.py``.

The env-fork sweep (``tools/lint/_env_fork_scan.py``) already flags a MODULE-LEVEL literal constant that
restates a ``fleet_constants`` name. This file pins what that sweep cannot see:

1. a similarity band assigned anywhere but its owner -- including inside ``try``/``except``, where the
   ``0.7`` fallbacks lived -- or restated as a conditional fallback (``SIMILARITY_MEDIUM if ok else 0.7``);
2. the install root in any string outside ``fleet_constants``: bare (``"/opt/autobot"``) or as a prefix
   inside a path, command or f-string piece (``"cd /opt/autobot/autobot-backend && ..."``). Docstrings
   are prose and are not read;
3. the SLM settings restating the heartbeat interval as a literal;
4. the Ansible copies (``autobot.base_dir``, ``slm_agent_dir``, ``slm_heartbeat_interval``) disagreeing.

The contrast tests rebuild each shape #18094 found and require the detector to flag it, so a clean live
run cannot come from a detector that lost its teeth.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import yaml
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from autobot_shared import fleet_constants
from tools.lint import check_getenv_ssot_drift  # noqa: F401 -- puts tools/lint on sys.path for the sibling import

from tools.lint import _env_fork_scan as scan_mod  # isort: skip
from tools.lint._scan_helpers import EmptyEnumeration  # isort: skip

_ROOT = repo_root()
_FLEET_HOME = "autobot_shared/fleet_constants.py"
_SIMILARITY_HOME = "autobot-backend/code_intelligence/similarity_thresholds.py"
_SIMILARITY_NAMES = frozenset({"SIMILARITY_HIGH", "SIMILARITY_MEDIUM", "SIMILARITY_LOW"})
_SLM_SETTINGS = "autobot-slm-backend/config.py"
_ANSIBLE = "autobot-slm-backend/ansible"

#: Install-root literals that predate this guard or genuinely mean something else: file -> (how many, reason).
#: Counted per occurrence, so a NEW literal in a listed file fails, and shrink-only: a file stating fewer
#: than its count fails as stale until the count is lowered (or the entry deleted at zero).
KNOWN_INSTALL_ROOT_LITERALS: dict[str, tuple[int, str]] = {
    "autobot-backend/security/enterprise/compliance_manager.py": (
        1,
        "historical: the literal junk-directory NAME the unexpanded #13658 placeholder created, matched "
        "verbatim to find that legacy tree -- not a path resolved under the install root",
    ),
}

#: Files that cannot import autobot_shared and so restate FLEET_INSTALL_ROOT once, under this name.
#: Each is held equal to fleet_constants and may state the root nowhere else.
STANDALONE_COPIES: dict[str, str] = {
    "autobot-slm-backend/scripts/autobot-admin.py": "_INSTALL_ROOT",  # copied alone to /usr/local/bin
}

#: Files the sweep must reach, or a clean run says nothing: each home and each former restatement.
_WITNESSES = (
    _FLEET_HOME,
    _SIMILARITY_HOME,
    _SLM_SETTINGS,
    "autobot-backend/code_intelligence/shared/analysis_base.py",
    "autobot-slm-backend/services/role_registry.py",
    "autobot-slm-backend/slm/agent/agent.py",
    "autobot-npu-worker/resources/windows-npu-worker/app/utils/backend_telemetry.py",
)


def _sources(root: Path) -> dict[str, str]:
    """Tracked production ``.py`` under the env-fork sweep's roots -- the same population and test rule."""
    out: dict[str, str] = {}
    for rel in scan_mod.tracked_paths(root, "*.py"):
        if rel.split("/")[0] not in scan_mod.SCAN_ROOTS or rel.endswith("_test.py") or "/tests/" in rel:
            continue
        try:
            out[rel] = (root / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
    return out


def _scanned_files(root: Path) -> list[str]:
    """The population the live sweep reads: production Python under the env-fork sweep's roots.

    An empty tree returns ``[]`` rather than raising, so the floor below refuses it as the typed
    ``ReachFloorError`` the reach meta-test hands every declaration (as excluded_tree_size_debt_test).
    """
    try:
        return sorted(_sources(root))
    except EmptyEnumeration:
        return []


#: ONE population (``_sources``) and its floor; ``reach_declarations_test`` proves the floor against it.
FILES = declare(
    "defined-twice-18094-scan",
    discover=_scanned_files,
    floor=3684,  # mid-window; the arithmetic is in the commit message, which cannot drift from the tree
    growth=150,
    what="production python files swept for a second definition of a #18094 value",
    roots=scan_mod.SCAN_ROOTS,
)


def _is_number(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool)


def _band_name(node: ast.AST) -> str | None:
    return node.id if isinstance(node, ast.Name) and node.id in _SIMILARITY_NAMES else None


def similarity_restatements(rel: str, source: str) -> list[str]:
    """A band assigned outside its home (at any depth), or paired with a literal fallback."""
    out: list[str] = []
    for node in ast.walk(ast.parse(source)):
        targets = node.targets if isinstance(node, ast.Assign) else []
        targets = [node.target] if isinstance(node, (ast.AnnAssign, ast.AugAssign)) else targets
        for name in filter(None, map(_band_name, targets)):
            if rel != _SIMILARITY_HOME:
                out.append(f"{rel}:{node.lineno}: assigns {name} -- import it from {_SIMILARITY_HOME}")
        if isinstance(node, ast.IfExp):
            pair = (node.body, node.orelse)
            name = _band_name(pair[0]) or _band_name(pair[1])
            if name and (_is_number(pair[0]) or _is_number(pair[1])):
                out.append(f"{rel}:{node.lineno}: {name} with a literal fallback")
    return out


def _docstrings(tree: ast.Module) -> set[int]:
    """ids of the docstring constants in *tree*: prose that names a path is documentation."""
    holders = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    return {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, holders) and node.body and isinstance(node.body[0], ast.Expr)
        if isinstance(node.body[0].value, ast.Constant)
    }


def _states_root(node: ast.AST, root: str) -> bool:
    """A string constant -- a whole literal or one f-string piece -- that is, or embeds, the install root."""
    if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
        return False
    return re.search(re.escape(root) + r"(?![\w.-])", node.value) is not None


def install_root_literals(rel: str, source: str) -> list[str]:
    """Every non-docstring string constant outside ``fleet_constants`` that states the install root."""
    if rel == _FLEET_HOME:
        return []
    tree, root = ast.parse(source), fleet_constants.FLEET_INSTALL_ROOT
    prose = _docstrings(tree)
    return [
        f"{rel}:{node.lineno}: the install root as a literal -- import FLEET_INSTALL_ROOT from {_FLEET_HOME}"
        for node in ast.walk(tree)
        if _states_root(node, root) and id(node) not in prose
    ]


def string_constants(source: str) -> int:
    """How many string constants a file holds: the reach of the install-root check over it."""
    return sum(isinstance(n, ast.Constant) and isinstance(n.value, str) for n in ast.walk(ast.parse(source)))


def settings_heartbeat_literals(rel: str, source: str) -> list[str]:
    """An SLM-side ``heartbeat_interval`` field whose default is a literal, not the shared constant."""
    if not rel.startswith("autobot-slm-backend/"):
        return []
    return [
        f"{rel}:{node.lineno}: heartbeat_interval restated -- use DEFAULT_HEARTBEAT_INTERVAL from {_FLEET_HOME}"
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "heartbeat_interval"
        and _is_number(node.value)
    ]


def _over_baseline(rel: str, found: list[str]) -> list[str]:
    """A listed file's literals when it states MORE than its baseline count (which one is new is unknowable)."""
    allowed = KNOWN_INSTALL_ROOT_LITERALS.get(rel, (0, ""))[0]
    return found if len(found) > allowed else []


def findings(sources: dict[str, str]) -> list[str]:
    """Every restatement in *sources*, minus the shrink-only, per-occurrence install-root baseline."""
    out: list[str] = []
    for rel, source in sorted(sources.items()):
        out += similarity_restatements(rel, source) + settings_heartbeat_literals(rel, source)
        out += _beyond_the_copy(rel, _over_baseline(rel, install_root_literals(rel, source)), source)
    return out


def stale_baseline_entries(sources: dict[str, str]) -> list[str]:
    """Baseline entries whose file now states the root FEWER times than counted: lower or delete them."""
    return [
        f"{rel}: baseline {count}, file states {len(install_root_literals(rel, sources.get(rel, '')))}"
        for rel, (count, _) in KNOWN_INSTALL_ROOT_LITERALS.items()
        if len(install_root_literals(rel, sources.get(rel, ""))) < count
    ]


def _copy_line(source: str, name: str) -> int | None:
    """Line of the module-level ``name = <the install root>`` a standalone copy declares, else None."""
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and [getattr(t, "id", None) for t in node.targets] == [name]:
            if isinstance(node.value, ast.Constant) and node.value.value == fleet_constants.FLEET_INSTALL_ROOT:
                return node.lineno
    return None


def _beyond_the_copy(rel: str, found: list[str], source: str) -> list[str]:
    """For a STANDALONE_COPIES file, drop its one declared copy; any other statement still counts."""
    if rel not in STANDALONE_COPIES:
        return found
    line = _copy_line(source, STANDALONE_COPIES[rel])
    return [f for f in found if not f.startswith(f"{rel}:{line}:")]


def test_each_value_has_one_home_on_the_live_tree() -> None:
    tracked = [rel for rel in scan_mod.tracked_paths(_ROOT, "*.py") if rel.split("/")[0] in scan_mod.SCAN_ROOTS]
    sources = _sources(_ROOT)
    assert len(FILES.examined(_ROOT)) >= FILES.floor, "the sweep read fewer files than its floor"
    missing = [rel for rel in _WITNESSES if rel not in sources]
    assert missing == [], f"the sweep never reached {missing} -- a clean result would be blind"
    unread = [rel for rel in tracked if rel not in sources and not (rel.endswith("_test.py") or "/tests/" in rel)]
    assert unread == [], f"{len(unread)} production file(s) in scope were not read: {unread[:5]}"
    reach = sum(string_constants(text) for text in sources.values())
    found = findings(sources)
    summary = f"checked {len(sources)} files and {reach} string constants: {len(found)} restatement(s)"
    assert found == [], summary + "\n" + "\n".join(found)


def test_the_install_root_baseline_only_shrinks() -> None:
    stale = stale_baseline_entries(_sources(_ROOT))
    assert stale == [], f"{stale} -- lower the KNOWN_INSTALL_ROOT_LITERALS count, or delete the entry at zero"


def test_each_standalone_copy_is_declared_once_and_equal() -> None:
    sources = _sources(_ROOT)
    undeclared = [rel for rel, name in STANDALONE_COPIES.items() if _copy_line(sources.get(rel, ""), name) is None]
    assert undeclared == [], f"{undeclared}: no module-level copy equal to FLEET_INSTALL_ROOT under its declared name"


def _yaml(rel: str) -> dict:
    return yaml.safe_load((_ROOT / _ANSIBLE / rel).read_text(encoding="utf-8"))


def test_the_ansible_copies_agree_with_fleet_constants() -> None:
    base_dir = _yaml("inventory/group_vars/all.yml")["autobot"]["base_dir"]
    agent = _yaml("roles/slm_agent/defaults/main.yml")
    agent_suffix = agent["slm_agent_dir"].replace("{{ autobot.base_dir }}", "")

    assert base_dir == fleet_constants.FLEET_INSTALL_ROOT
    assert fleet_constants.FLEET_AGENT_DIR == fleet_constants.FLEET_INSTALL_ROOT + agent_suffix
    assert agent["slm_heartbeat_interval"] == fleet_constants.DEFAULT_HEARTBEAT_INTERVAL
    code_source = _yaml("roles/autobot_shared/defaults/main.yml")["code_source_dir"]
    assert code_source.replace("{{ autobot.base_dir }}", base_dir) == fleet_constants.FLEET_CODE_SOURCE_DIR  # #15708


# --- contrast: each shape #18094 found must be flagged -------------------------------------------


def test_a_try_except_band_fallback_is_flagged() -> None:
    source = "try:\n    from x import SIMILARITY_MEDIUM\nexcept ImportError:\n    SIMILARITY_MEDIUM = 0.7\n"
    assert len(findings({"autobot-backend/code_intelligence/shared/analysis_base.py": source})) == 1


def test_a_conditional_band_fallback_is_flagged() -> None:
    source = "f(min_similarity=(SIMILARITY_MEDIUM if HAS else 0.7))\n"
    assert len(findings({"autobot-backend/code_intelligence/security/analyzer.py": source})) == 1


def test_the_owner_may_define_its_bands() -> None:
    assert findings({_SIMILARITY_HOME: "SIMILARITY_MEDIUM = 0.70\n"}) == []


def test_a_restated_install_root_fallback_is_flagged() -> None:
    source = 'import os\n_BASE = os.environ.get("AUTOBOT_BASE_DIR", "/opt/autobot")\n'
    assert len(findings({"autobot-slm-backend/services/role_registry.py": source})) == 1


def test_an_embedded_install_root_in_a_command_or_fstring_is_flagged() -> None:
    source = 'CMD = "cd /opt/autobot/autobot-backend && run"\nDEST = f"/opt/autobot/{component}/"\n'
    source += 'NOTE = "ReadWritePaths=/opt/autobot"\nOTHER = "/opt/autobot-legacy"\n'
    assert len(findings({"autobot-slm-backend/services/service_orchestrator.py": source})) == 3


def test_a_docstring_naming_the_install_root_is_prose() -> None:
    source = '"""Deploys to /opt/autobot/autobot-backend."""\n'
    assert findings({"autobot-slm-backend/services/service_orchestrator.py": source}) == []


def test_a_standalone_copy_may_state_the_root_once_only() -> None:
    rel = "autobot-slm-backend/scripts/autobot-admin.py"
    once = '_INSTALL_ROOT = "/opt/autobot"\nENV = f"{_INSTALL_ROOT}/x/.env"\n'
    twice = once + 'OTHER = "/opt/autobot/y"\n'
    assert findings({rel: once}) == []
    assert len(findings({rel: twice})) == 1


def test_a_literal_settings_heartbeat_is_flagged() -> None:
    source = "class Settings:\n    heartbeat_interval: int = 30\n"
    assert len(findings({_SLM_SETTINGS: source})) == 1


def test_a_shared_settings_heartbeat_is_allowed() -> None:
    source = "class Settings:\n    heartbeat_interval: int = DEFAULT_HEARTBEAT_INTERVAL\n"
    assert findings({_SLM_SETTINGS: source}) == []


def test_a_new_literal_in_a_baselined_file_is_flagged_and_a_removed_one_is_stale() -> None:
    rel = "autobot-backend/security/enterprise/compliance_manager.py"  # any file still on the baseline at a count of 1
    one = 'REPO = "/opt/autobot"\n'

    def stale(source: str) -> list[str]:
        return [entry for entry in stale_baseline_entries({rel: source}) if entry.startswith(rel)]

    assert findings({rel: one}) == [] and stale(one) == []
    assert len(findings({rel: one + 'OTHER = "/opt/autobot/x"\n'})) == 2, "a second literal hid behind the entry"
    assert stale("REPO = None\n"), "a removed literal must make its entry stale"
