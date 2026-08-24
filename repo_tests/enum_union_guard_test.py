# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#13845/#13846/#13597/#13578 — the unioned enums may not lose a member again.

Four enum families had been forked, and in every case the *divergent tail* was
the functionality:

* ``CommandRisk`` / ``CommandRiskLevel`` — pick a survivor and ``FORBIDDEN``
  (or ``DANGEROUS``) stops existing.
* ``SecretType`` / ``SecretRequirement`` / a third copy in the API schemas —
  pick a survivor and an agent can never again state that it needs OAuth
  credentials, only ``ANY``, the blanket grant.
* ``AlertSeverity`` / ``ErrorSeverity`` vs the canonical ``Severity``.
* ``service_type`` — no enum at all, and two spellings of postgres.

So these tests pin **member sets**, not names. A rename is a member-set change
and fails here by name; a member quietly dropped fails here by name. Both
directions were mutation-checked before this file was committed.

Three traps this file is deliberately built against:

* *An empty result reads as clean.* Every scan asserts it reached something
  before it asserts anything about what it found.
* *A guard fed a hand-written list guards that list only.* The severity-literal
  ratchet derives its population from the tree with the same matcher the count
  came from, and floors the file enumeration.
* *A guard whose target is missing reports a false PASS.* Each mapping test
  asserts the target table exists and is non-empty first.
"""

from __future__ import annotations

import ast
import functools
import re
import subprocess  # nosec B404  # fixed argv, no shell, no caller input
from pathlib import Path

import pytest

from autobot_shared.status_enums import CommandRisk, SecretType, Severity

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "autobot-backend"
SLM = REPO_ROOT / "autobot-slm-backend"


def _members(enum_cls) -> set[tuple[str, str]]:
    """(name, value) pairs — the identity a rename cannot survive."""
    return {(member.name, member.value) for member in enum_cls}


# --------------------------------------------------------------------------
# #13845 — CommandRisk carries both tails
# --------------------------------------------------------------------------

# Every member of every side of the fork. FORBIDDEN and CRITICAL came from
# the executor's enum; DANGEROUS from the terminal wire schema; SAFE/MODERATE/
# HIGH were the three that already matched.
COMMAND_RISK_UNION = {
    ("SAFE", "safe"),
    ("MODERATE", "moderate"),
    ("HIGH", "high"),
    ("CRITICAL", "critical"),
    ("DANGEROUS", "dangerous"),
    ("FORBIDDEN", "forbidden"),
}


def test_command_risk_is_exactly_the_union_of_both_forks():
    assert _members(CommandRisk) == COMMAND_RISK_UNION


@pytest.mark.parametrize("name", sorted(name for name, _ in COMMAND_RISK_UNION))
def test_every_command_risk_member_is_present_by_name(name):
    """Presence, asserted one member at a time, so a loss names itself."""
    assert hasattr(CommandRisk, name), f"#13845: CommandRisk lost {name}"


def test_the_wire_spellings_of_both_forks_still_parse():
    """Values already emitted by the API and stored in logs must resolve."""
    assert CommandRisk("dangerous") is CommandRisk.DANGEROUS
    assert CommandRisk("forbidden") is CommandRisk.FORBIDDEN


def test_rank_covers_every_member_and_is_strictly_ascending():
    ranks = [risk.rank for risk in CommandRisk]
    assert len(ranks) == len(CommandRisk)
    assert ranks == sorted(ranks) == list(range(len(CommandRisk)))


def test_both_blocking_verdicts_block_and_nothing_else_does():
    """The whole point of ``.blocks``: neither producer's verdict is missed."""
    blocking = {risk for risk in CommandRisk if risk.blocks}
    assert blocking == {CommandRisk.DANGEROUS, CommandRisk.FORBIDDEN}


# Deliberately distinct, verified by reading its docstring — not a fork.
# ``InjectionRisk`` grades a piece of *text* for injection patterns; CommandRisk
# grades a *command* for execution policy. Different subject, and the scales
# differ at both ends (LOW only there, DANGEROUS/FORBIDDEN only here).
KNOWN_DISTINCT_RISK_ENUMS = {
    "autobot-backend/security/prompt_injection_detector.py::InjectionRisk",
}


def test_no_second_command_risk_enum_has_regrown():
    """A same-concept fork is what this issue was; catch the next copy."""
    found = set(_enums_matching(lambda members: {"SAFE", "MODERATE", "HIGH"} <= members))
    assert found, "scan reached no enum at all — the matcher is broken, not the tree"
    assert found - KNOWN_DISTINCT_RISK_ENUMS == {
        "autobot_shared/status_enums.py::CommandRisk"
    }, f"#13845: a second command-risk enum exists: {sorted(found - KNOWN_DISTINCT_RISK_ENUMS)}"


def test_every_known_distinct_entry_still_names_a_real_enum():
    """An allowlist entry stranded by a rename exempts nothing, silently."""
    declared = {f"{rel}::{name}" for rel, name, _ in _declared_enums()}
    stale = KNOWN_DISTINCT_RISK_ENUMS - declared
    assert not stale, f"#13845: allowlist entries name no enum any more: {sorted(stale)}"


# --------------------------------------------------------------------------
# #13846 — SecretType carries every kind plus the wildcard
# --------------------------------------------------------------------------

SECRET_TYPE_UNION = {
    ("SSH_KEY", "ssh_key"),
    ("PASSWORD", "password"),
    ("API_KEY", "api_key"),
    ("TOKEN", "token"),
    ("OAUTH_REFRESH_TOKEN", "oauth_refresh_token"),
    ("CONNECTOR_OAUTH_TOKEN", "connector_oauth_token"),
    ("CERTIFICATE", "certificate"),
    ("DATABASE_URL", "database_url"),
    ("INFRASTRUCTURE_HOST", "infrastructure_host"),
    ("OTHER", "other"),
    ("ANY", "any"),
}


def test_secret_type_is_exactly_the_union_of_all_three_forks():
    assert _members(SecretType) == SECRET_TYPE_UNION


@pytest.mark.parametrize("name", sorted(name for name, _ in SECRET_TYPE_UNION))
def test_every_secret_kind_is_present_by_name(name):
    assert hasattr(SecretType, name), f"#13846: SecretType lost {name}"


def test_an_agent_requirement_can_name_oauth_without_falling_back_to_any():
    """The functional gap #13846 was filed for, asserted as behaviour.

    ``SecretRequirement`` had no OAuth member, so an OAuth-authenticating agent
    could only be described as ANY — the broadest possible grant standing in
    for the most specific request.
    """
    requirement = {SecretType.OAUTH_REFRESH_TOKEN}
    resolved = SecretType.expand(requirement)
    assert resolved == {SecretType.OAUTH_REFRESH_TOKEN}
    assert SecretType.ANY not in resolved
    assert resolved != SecretType.expand({SecretType.ANY})


def test_the_wildcard_is_preserved_and_expands_to_the_whole_taxonomy():
    assert SecretType.ANY in SecretType
    expanded = SecretType.expand({SecretType.ANY})
    assert expanded == set(SecretType.concrete())
    assert SecretType.ANY not in expanded


def test_the_wildcard_is_never_a_storable_kind():
    assert SecretType.ANY not in SecretType.concrete()
    assert len(SecretType.concrete()) == len(SecretType) - 1


def test_no_second_secret_kind_enum_has_regrown():
    found = _enums_matching(lambda members: {"SSH_KEY", "API_KEY", "TOKEN"} <= members)
    assert found, "scan reached no enum at all — the matcher is broken, not the tree"
    assert sorted(found) == ["autobot_shared/status_enums.py::SecretType"], (
        f"#13846: a second secret-kind enum exists: {sorted(found)}"
    )


# --------------------------------------------------------------------------
# #13845 — the boundary table into the DELIBERATE #7258 fork stays total
# --------------------------------------------------------------------------


def test_the_risk_level_boundary_table_covers_every_command_risk():
    """``map_risk_to_level`` used to default to MEDIUM for an unmapped member.

    Read by AST rather than imported: ``services.agent_terminal.utils`` pulls in
    the SQLAlchemy models, and this guard must not depend on a database.
    """
    source = (BACKEND / "services" / "agent_terminal" / "utils.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    mapped: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key in node.keys:
                if (
                    isinstance(key, ast.Attribute)
                    and isinstance(key.value, ast.Name)
                    and key.value.id == "CommandRisk"
                ):
                    mapped.add(key.attr)
    assert mapped, "target table not found — the guard would pass on an empty scan"
    assert mapped == {member.name for member in CommandRisk}, (
        f"#13845: _COMMAND_RISK_TO_RISK_LEVEL is missing {sorted({m.name for m in CommandRisk} - mapped)}"
    )


# --------------------------------------------------------------------------
# #13578 — the backup service vocabulary
# --------------------------------------------------------------------------

BACKUP_SERVICE_TYPE_UNION = {("REDIS", "redis"), ("POSTGRES", "postgres")}


def _enum_members_from_source(path: Path, class_name: str) -> set[tuple[str, str]] | None:
    """Member (name, value) pairs read by AST — no import, no DB, no app config."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {
                (target.id, stmt.value.value)
                for stmt in node.body
                if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Constant)
                for target in stmt.targets
                if isinstance(target, ast.Name) and not target.id.startswith("_")
            }
    return None


def test_backup_service_type_exists_and_names_both_engines():
    members = _enum_members_from_source(SLM / "models" / "database.py", "BackupServiceType")
    assert members is not None, "#13578: BackupServiceType is gone from models/database.py"
    assert members == BACKUP_SERVICE_TYPE_UNION


def test_the_postgres_alias_is_declared_next_to_the_enum():
    """"postgresql" was a live dispatch key, so it is already in stored rows."""
    source = (SLM / "models" / "database.py").read_text(encoding="utf-8")
    assert "_BACKUP_SERVICE_TYPE_ALIASES" in source
    assert '"postgresql"' in source


def test_the_backup_dispatch_no_longer_carries_two_spellings():
    source = (SLM / "api" / "stateful.py").read_text(encoding="utf-8")
    assert "BackupServiceType.POSTGRES: backup_service.execute_postgres_backup" in source
    assert '"postgresql": backup_service' not in source


# --------------------------------------------------------------------------
# #13597 — the severity literals may not grow back
# --------------------------------------------------------------------------

# Bare `"severity": "<literal>"` dict entries. Not converted in this change —
# see the issue trail — but ratcheted so the population cannot grow while the
# conversion is outstanding.
_SEVERITY_LITERAL = re.compile(r"""["']severity["']\s*:\s*["'][A-Za-z_]+["']""")

# Measured on this tree at the time of writing. #13597 filed it as 119; it had
# grown to this before anything stopped it. Lower it as literals are converted;
# never raise it.
SEVERITY_LITERAL_CEILING = 169

# Floor for the enumeration itself. An empty walk must not read as "clean".
_TRACKED_PY_FLOOR = 3000

# Floor for the enum scan (measured at 300+ on this tree). A parse pass that
# silently stopped matching would otherwise report every fork as collapsed.
_DECLARED_ENUM_FLOOR = 150


@functools.lru_cache(maxsize=1)
def _tracked_python_files() -> tuple[str, ...]:
    out = subprocess.run(  # nosec B603  # fixed argv, no shell
        ["git", "ls-files", "*.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return tuple(line for line in out.stdout.splitlines() if line)


def _severity_literal_hits() -> list[str]:
    hits = []
    for rel in _tracked_python_files():
        if not (rel.startswith("autobot-backend/") or rel.startswith("autobot_shared/")):
            continue
        try:
            text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        except OSError:
            continue
        for match in _SEVERITY_LITERAL.finditer(text):
            hits.append(f"{rel}:{match.group(0)}")
    return hits


def test_the_enumeration_reaches_the_repo():
    """Guards every scan below: an empty file list agrees with anything."""
    assert len(_tracked_python_files()) >= _TRACKED_PY_FLOOR


def test_the_severity_literal_matcher_still_matches():
    """A regex that stopped matching would report a clean tree (#13597)."""
    assert _SEVERITY_LITERAL.search('{"severity": "high"}')
    assert _SEVERITY_LITERAL.search("{'severity': 'critical'}")
    assert not _SEVERITY_LITERAL.search('{"severity": severity_value}')


def test_bare_severity_literals_do_not_grow():
    hits = _severity_literal_hits()
    assert hits, "matcher reached nothing — broken matcher, not a clean tree"
    assert len(hits) <= SEVERITY_LITERAL_CEILING, (
        f"#13597: bare severity literals grew to {len(hits)} (ceiling "
        f"{SEVERITY_LITERAL_CEILING}). Use autobot_shared.status_enums.Severity."
    )


@pytest.mark.parametrize(
    ("rel", "alias"),
    [
        ("autobot-backend/utils/monitoring_alerts.py", "AlertSeverity"),
        ("autobot-backend/utils/error_boundaries/types.py", "ErrorSeverity"),
    ],
)
def test_the_severity_aliases_still_point_at_the_canonical_enum(rel, alias):
    """#13597's first half, already landed — assert it stayed landed.

    Read by AST: importing these pulls the whole backend app in. The assertion
    is on the binding, so re-declaring a local ``class AlertSeverity(Enum)``
    fails here even though the name would still exist.
    """
    path = REPO_ROOT / rel
    assert path.exists(), f"#13597: {rel} is gone — the guard has no target"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    bindings = [
        node.value.id
        for node in tree.body
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Name)
        for target in node.targets
        if isinstance(target, ast.Name) and target.id == alias
    ]
    redeclared = [
        node.name for node in tree.body if isinstance(node, ast.ClassDef) and node.name == alias
    ]
    assert not redeclared, f"#13597: {alias} was re-declared as its own enum in {rel}"
    assert bindings == ["Severity"], (
        f"#13597: {alias} in {rel} is bound to {bindings or 'nothing'}, not Severity"
    )


def test_the_canonical_severity_still_carries_every_aliased_member():
    """The aliases are only safe while Severity is a superset of both forks."""
    for name in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
        assert hasattr(Severity, name), f"#13597: Severity lost {name}"


# --------------------------------------------------------------------------
# Shared scan helper
# --------------------------------------------------------------------------


_ENUM_BASES = {"Enum", "IntEnum", "StrEnum", "Flag", "IntFlag"}


def _local_enum_names(tree: ast.Module) -> set[str]:
    """Local names in this module that are bound to an ``enum`` base class.

    Resolving the *import* rather than matching the literal word "Enum" is what
    makes the scan survive ``from enum import Enum as _E``. Matching the word
    alone reported a re-declared ``CommandRiskLevel`` as absent — a fail-open
    found by mutating this guard, not by reading it.
    """
    local = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "enum":
            for alias in node.names:
                if alias.name in _ENUM_BASES:
                    local.add(alias.asname or alias.name)
    return local


def _base_names(node: ast.ClassDef) -> set[str]:
    """Base names as written: bare ``Enum`` and dotted ``enum.Enum`` alike."""
    names = set()
    for base in node.bases:
        if isinstance(base, ast.Name):
            names.add(base.id)
        elif isinstance(base, ast.Attribute):
            names.add(base.attr)
    return names


def _enums_in_tree(tree: ast.Module) -> list[tuple[str, frozenset[str]]]:
    """(class name, member names) for every enum declared in one module."""
    local = _local_enum_names(tree) | _ENUM_BASES
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or not (_base_names(node) & local):
            continue
        names = frozenset(
            target.id
            for stmt in node.body
            if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Constant)
            for target in stmt.targets
            if isinstance(target, ast.Name)
        )
        if names:
            found.append((node.name, names))
    return found


@functools.lru_cache(maxsize=1)
def _declared_enums() -> tuple[tuple[str, str, frozenset[str]], ...]:
    """Every enum under the Python roots, with its member names.

    Parsed once for the whole module — the two fork scans below would otherwise
    re-read several thousand files each.
    """
    declared: list[tuple[str, str, frozenset[str]]] = []
    for rel in _tracked_python_files():
        if not (rel.startswith("autobot-backend/") or rel.startswith("autobot_shared/")):
            continue
        try:
            tree = ast.parse((REPO_ROOT / rel).read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        declared.extend((rel, name, members) for name, members in _enums_in_tree(tree))
    return tuple(declared)


def test_the_scan_sees_an_enum_whose_base_was_imported_under_an_alias():
    """The fail-open this guard shipped with, pinned against synthetic source.

    Mutation M9 re-declared ``CommandRiskLevel`` with ``from enum import Enum
    as _E`` and the fork scan stayed green: it matched the literal word "Enum"
    in the base list, which an alias removes. Run against a string here, so the
    check does not depend on the tree containing an example.
    """
    aliased = ast.parse(
        "from enum import Enum as _E\n\n\nclass Regrown(_E):\n    SAFE = 'safe'\n"
    )
    assert _enums_in_tree(aliased) == [("Regrown", frozenset({"SAFE"}))]

    dotted = ast.parse("import enum\n\n\nclass Dotted(enum.Enum):\n    SAFE = 'safe'\n")
    assert _enums_in_tree(dotted) == [("Dotted", frozenset({"SAFE"}))]

    plain = ast.parse("from enum import Enum\n\n\nclass Plain(Enum):\n    SAFE = 'safe'\n")
    assert _enums_in_tree(plain) == [("Plain", frozenset({"SAFE"}))]

    assert _enums_in_tree(ast.parse("class NotAnEnum:\n    SAFE = 'safe'\n")) == []


def _enums_matching(predicate) -> list[str]:
    """Enums whose MEMBER SET matches — never their class name.

    A same-name sweep is exactly what missed these forks: each pair used
    different names for one concept.
    """
    return [
        f"{rel}::{name}" for rel, name, members in _declared_enums() if predicate(members)
    ]


def test_the_enum_scan_reaches_the_repo():
    """A scan that parsed nothing would agree with every assertion above."""
    declared = _declared_enums()
    assert len(declared) >= _DECLARED_ENUM_FLOOR, (
        f"enum scan found only {len(declared)} enums — the matcher is broken, "
        f"not the tree"
    )
