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

Four traps this file is deliberately built against:

* *An empty result reads as clean.* Every scan asserts it reached something
  before it asserts anything about what it found.
* *A guard fed a hand-written list guards that list only.* The severity-literal
  ratchet derives its population from the tree with the same matcher the count
  came from, and floors the file enumeration.
* *A guard whose target is missing reports a false PASS.* Each mapping test
  asserts the target table exists and is non-empty first.
* *A sweep that edits by pattern edits prose too.* #14956's regex conversion
  rewrote a literal inside a docstring's ```json response body, producing
  documentation no reader could copy. Prose is exempt from the ratchet, never a
  target for it, and ``test_no_enum_read_was_written_inside_a_string`` fails if
  an enum read lands inside a string constant again.
"""

from __future__ import annotations

import ast
import functools
import importlib.util
import re
import subprocess  # nosec B404  # fixed argv, no shell, no caller input
from pathlib import Path

import pytest

from autobot_shared.paths import scrubbed_git_env
from autobot_shared.status_enums import CommandRisk, RiskLevel, SecretType, Severity

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
    assert sorted(found) == [
        "autobot_shared/status_enums.py::SecretType"
    ], f"#13846: a second secret-kind enum exists: {sorted(found)}"


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
                if isinstance(key, ast.Attribute) and isinstance(key.value, ast.Name) and key.value.id == "CommandRisk":
                    mapped.add(key.attr)
    assert mapped, "target table not found — the guard would pass on an empty scan"
    assert mapped == {
        member.name for member in CommandRisk
    }, f"#13845: _COMMAND_RISK_TO_RISK_LEVEL is missing {sorted({m.name for m in CommandRisk} - mapped)}"


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
    """ "postgresql" was a live dispatch key, so it is already in stored rows."""
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

# Bare `"severity": "<literal>"` dict entries. #14956 converted the in-process
# producers to canonical `Severity` members; what remains is ratcheted so the
# population can neither grow nor silently vanish.
_SEVERITY_LITERAL = re.compile(r"""["']severity["']\s*:\s*["'][A-Za-z_]+["']""")

# #13597 filed this at 119; it had grown to 169 before the ratchet stopped it.
# #14956 converted 144 of those 169, leaving only the entries below. Lower it as
# literals are converted; never raise it.
SEVERITY_LITERAL_CEILING = 25

# Floor for the literal population itself. Zero must FAIL, not read as clean —
# a matcher that stopped matching, a moved root, or an `OSError` swallowed per
# file would all otherwise report a spotless tree. Set just under the ceiling so
# converting one of the entries below is a deliberate edit of this guard rather
# than a silent drift.
SEVERITY_LITERAL_FLOOR = 20

# The files where a bare literal is the RIGHT thing to write, and why. Two
# reasons qualify, and nothing else does: the value crosses an external
# boundary, or the line is documentation prose rather than a producer.
DELIBERATE_SEVERITY_LITERALS = {
    # --- external boundary: writing the enum would assert it against itself ---
    # Inbound Prometheus Alertmanager webhook payloads. The literal is the
    # third party's label, replayed verbatim.
    "autobot-backend/monitoring/alertmanager_webhook_test.py",
    "autobot-backend/api/webhook_authentication_security_test.py",
    # NOAA/NWS alert feed. `properties.severity` is the CAP vocabulary
    # (Extreme/Severe/Moderate/Minor/Unknown), passed straight through by
    # NOAASource — a different taxonomy that happens to share the field name.
    "autobot-backend/tests/test_osint_engine.py",
    # --- documentation prose: the line is read, not executed ---
    # Graph node properties are caller-supplied key/value data; the docstring
    # example illustrates the shape, it does not produce a severity.
    "autobot-backend/autobot_memory_graph/property_graph.py",
    "autobot-backend/autobot_memory_graph/property_graph_mixin.py",
    # A ```json response body inside the endpoint docstring. #14956's first
    # sweep rewrote this one to an enum read and produced invalid JSON in the
    # documentation — see test_no_enum_read_was_written_inside_a_string below,
    # which exists because of it.
    "autobot-backend/api/knowledge_grounding.py",
}

# Floor for the enumeration itself. An empty walk must not read as "clean".
_TRACKED_PY_FLOOR = 3000

# Floor for the enum scan (measured at 300+ on this tree). A parse pass that
# silently stopped matching would otherwise report every fork as collapsed.
_DECLARED_ENUM_FLOOR = 150


@functools.lru_cache(maxsize=1)
def _tracked_python_files() -> tuple[str, ...]:
    out = subprocess.run(  # nosec B603  # fixed argv, no shell
        ["git", "ls-files", "*.py"], cwd=REPO_ROOT, capture_output=True, text=True, check=True, env=scrubbed_git_env()
    )
    return tuple(line for line in out.stdout.splitlines() if line)


def _severity_literal_hits() -> list[tuple[str, str]]:
    """(file, matched text) for every bare severity literal under the roots."""
    hits = []
    for rel in _tracked_python_files():
        if not (rel.startswith("autobot-backend/") or rel.startswith("autobot_shared/")):
            continue
        try:
            text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        except OSError:
            continue
        for match in _SEVERITY_LITERAL.finditer(text):
            hits.append((rel, match.group(0)))
    return hits


def test_the_enumeration_reaches_the_repo():
    """Guards every scan below: an empty file list agrees with anything."""
    assert len(_tracked_python_files()) >= _TRACKED_PY_FLOOR


def _banned_shape(quote: str, value: str) -> str:
    """Build a string this file's own matcher matches, without writing one.

    Spelling the shape out as a literal would plant an offender inside the very
    guard that bans it — the trap that has bitten fixtures in this repo before.
    ``test_this_guard_does_not_trip_its_own_matcher`` pins that it stays true.
    """
    key = quote + "severity" + quote
    return "{" + key + ": " + quote + value + quote + "}"


def test_the_severity_literal_matcher_still_matches():
    """A regex that stopped matching would report a clean tree (#13597)."""
    assert _SEVERITY_LITERAL.search(_banned_shape('"', "high"))
    assert _SEVERITY_LITERAL.search(_banned_shape("'", "critical"))
    assert _SEVERITY_LITERAL.search(_banned_shape('"', "warning"))
    assert not _SEVERITY_LITERAL.search('{"severity": severity_value}')
    assert not _SEVERITY_LITERAL.search('{"severity": Severity.HIGH.value}')


def test_this_guard_does_not_trip_its_own_matcher():
    """The self-guard for the fixture trap, asserted rather than trusted.

    ``repo_tests/`` is outside the scanned roots today, so a literal here would
    be invisible; the moment the roots widen, the guard would start reporting
    itself. Assemble fixtures, never spell them.
    """
    source = Path(__file__).read_text(encoding="utf-8")
    assert not _SEVERITY_LITERAL.search(source), (
        "this guard file contains a literal its own matcher bans — assemble it "
        "from fragments with _banned_shape() instead"
    )


def test_bare_severity_literals_do_not_grow():
    hits = _severity_literal_hits()
    assert len(hits) >= SEVERITY_LITERAL_FLOOR, (
        f"#14956: the sweep found only {len(hits)} severity literals (floor "
        f"{SEVERITY_LITERAL_FLOOR}). The sweep no longer finds what it is meant "
        f"to scan — a broken matcher or a moved root, not a clean tree. If an "
        f"entry in DELIBERATE_SEVERITY_LITERALS was genuinely converted, drop "
        f"it from that set and lower both bounds in the same commit."
    )
    assert len(hits) <= SEVERITY_LITERAL_CEILING, (
        f"#13597/#14956: bare severity literals grew to {len(hits)} (ceiling "
        f"{SEVERITY_LITERAL_CEILING}). Use autobot_shared.status_enums.Severity."
    )


def test_no_new_file_carries_a_bare_severity_literal():
    """The ceiling alone would let one file shed a literal while another gained one."""
    offenders = {rel for rel, _ in _severity_literal_hits()}
    assert offenders, "matcher reached nothing — broken matcher, not a clean tree"
    unexpected = offenders - DELIBERATE_SEVERITY_LITERALS
    assert not unexpected, (
        f"#14956: bare severity literals reappeared in {sorted(unexpected)}. Use "
        f"autobot_shared.status_enums.Severity, or add the file to "
        f"DELIBERATE_SEVERITY_LITERALS with the boundary it crosses."
    )


def test_every_deliberate_severity_literal_file_still_has_one():
    """A stale allowlist entry exempts nothing and hides that it exempts nothing."""
    offenders = {rel for rel, _ in _severity_literal_hits()}
    stale = DELIBERATE_SEVERITY_LITERALS - offenders
    assert not stale, (
        f"#14956: these files no longer carry a bare severity literal, so their "
        f"exemption is dead weight — remove them from "
        f"DELIBERATE_SEVERITY_LITERALS: {sorted(stale)}"
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
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Name)
        for target in node.targets
        if isinstance(target, ast.Name) and target.id == alias
    ]
    redeclared = [node.name for node in tree.body if isinstance(node, ast.ClassDef) and node.name == alias]
    assert not redeclared, f"#13597: {alias} was re-declared as its own enum in {rel}"
    assert bindings == ["Severity"], f"#13597: {alias} in {rel} is bound to {bindings or 'nothing'}, not Severity"


def test_the_canonical_severity_still_carries_every_aliased_member():
    """The aliases are only safe while Severity is a superset of both forks."""
    for name in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
        assert hasattr(Severity, name), f"#13597: Severity lost {name}"


# --------------------------------------------------------------------------
# #14956 — the three rungs the vocabulary was missing, and the ladder it kept
# --------------------------------------------------------------------------

# The full vocabulary after #14956. WARNING, DEGRADED and ERROR were NOT folded
# into a neighbouring rung: each is already emitted across a boundary that would
# change if it moved — a Prometheus label, an API response field, and an audit
# finding grade respectively. See the Severity docstring for the evidence.
SEVERITY_VOCABULARY = {
    ("UNKNOWN", "unknown"),
    ("INFO", "info"),
    ("MINIMAL", "minimal"),
    ("LOW", "low"),
    ("WARNING", "warning"),
    ("MEDIUM", "medium"),
    ("DEGRADED", "degraded"),
    ("HIGH", "high"),
    ("ERROR", "error"),
    ("CRITICAL", "critical"),
}

# The rungs numeric risk grading maps onto — the enum exactly as it stood BEFORE
# #14956, in order. Bug-prediction endpoints build their risk distribution from
# this, so it is a shipped API response key set, not an implementation detail.
SEVERITY_SCORE_LADDER = ("unknown", "info", "minimal", "low", "medium", "high", "critical")


def test_severity_is_exactly_the_vocabulary_union():
    assert _members(Severity) == SEVERITY_VOCABULARY


@pytest.mark.parametrize("name", sorted(name for name, _ in SEVERITY_VOCABULARY))
def test_every_severity_rung_is_present_by_name(name):
    """Presence, one rung at a time, so a loss names itself."""
    assert hasattr(Severity, name), f"#14956: Severity lost {name}"


def test_the_wire_spellings_of_the_added_rungs_resolve():
    """Values already on the wire before they had an enum member.

    ``warning`` is a Prometheus label the monitor publishes, ``degraded`` is
    serialised into the causal-analysis response, ``error`` is the grade the
    capability audit counts findings at.
    """
    assert Severity("warning") is Severity.WARNING
    assert Severity("degraded") is Severity.DEGRADED
    assert Severity("error") is Severity.ERROR


def test_the_score_ladder_is_untouched_by_the_added_vocabulary():
    """#14956's blast-radius guard: adding rungs must not reshape a response."""
    ladder = Severity.score_ladder()
    assert tuple(level.value for level in ladder) == SEVERITY_SCORE_LADDER
    assert set(ladder) < set(Severity), "the ladder must stay a strict subset"


def test_the_risk_distribution_keys_did_not_gain_the_added_rungs():
    """Asserted as the endpoints build it, not as the enum declares it.

    ``{level.value: 0 for level in RiskLevel}`` is what the bug-prediction
    endpoints shipped. Left iterating the enum, #14956 would have added three
    always-zero buckets to a live API response.
    """
    distribution = {level.value: 0 for level in RiskLevel.score_ladder()}
    assert tuple(distribution) == SEVERITY_SCORE_LADDER
    for added in ("warning", "degraded", "error"):
        assert added not in distribution, f"#14956: {added} leaked into the risk distribution"


def test_the_severity_scale_is_strictly_ascending_over_the_whole_vocabulary():
    """A rung inserted at the wrong height silently reorders every comparison."""
    scores = [Severity.to_score(level) for level in Severity]
    assert scores == sorted(scores)
    assert len(set(scores)) == len(scores), "two rungs share a score"
    assert Severity.to_score(Severity.LOW) < Severity.to_score(Severity.WARNING)
    assert Severity.to_score(Severity.WARNING) < Severity.to_score(Severity.MEDIUM)
    assert Severity.to_score(Severity.MEDIUM) < Severity.to_score(Severity.DEGRADED)
    assert Severity.to_score(Severity.HIGH) < Severity.to_score(Severity.ERROR)
    assert Severity.to_score(Severity.ERROR) < Severity.to_score(Severity.CRITICAL)


def test_from_score_still_returns_only_ladder_rungs():
    """Grading behaviour is unchanged: the added rungs are vocabulary, not output."""
    graded = {Severity.from_score(step / 100) for step in range(0, 101)}
    assert graded, "the sweep graded nothing"
    assert graded <= set(Severity.score_ladder())


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

    Boundary of what this resolves, stated so the next reader does not assume
    more: it follows a DIRECT ``from enum import ...`` in the module being
    scanned. A two-hop re-export — module A doing ``from enum import Enum as
    _E; Base = _E``, module B doing ``from A import Base`` — is not resolved
    and would be invisible. That is evasion-only rather than a shape anyone
    writes by accident, and closing it means resolving imports across modules;
    ``test_a_two_hop_re_export_is_a_known_blind_spot`` pins the limit so it is
    a documented boundary rather than a silent one. A star-import and
    subclassing an already-populated Enum are both covered.
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
    aliased = ast.parse("from enum import Enum as _E\n\n\nclass Regrown(_E):\n    SAFE = 'safe'\n")
    assert _enums_in_tree(aliased) == [("Regrown", frozenset({"SAFE"}))]

    dotted = ast.parse("import enum\n\n\nclass Dotted(enum.Enum):\n    SAFE = 'safe'\n")
    assert _enums_in_tree(dotted) == [("Dotted", frozenset({"SAFE"}))]

    plain = ast.parse("from enum import Enum\n\n\nclass Plain(Enum):\n    SAFE = 'safe'\n")
    assert _enums_in_tree(plain) == [("Plain", frozenset({"SAFE"}))]

    assert _enums_in_tree(ast.parse("class NotAnEnum:\n    SAFE = 'safe'\n")) == []


def test_a_two_hop_re_export_is_a_known_blind_spot():
    """Pin the scan's limit so it is documented rather than discovered.

    ``_local_enum_names`` resolves a direct ``from enum import ...``. It does
    not chase a base re-exported through another module. This test asserts the
    CURRENT behaviour: if someone teaches the scan to follow re-exports, this
    test goes red and should be updated to assert the enum IS found — which is
    the point. A limit nobody wrote down is the one that gets mistaken for
    coverage.
    """
    two_hop = ast.parse("from shims import Base\n\n\nclass Hidden(Base):\n    SAFE = 'safe'\n")
    assert _enums_in_tree(two_hop) == [], (
        "the scan now follows two-hop re-exports — good; update this test to "
        "assert the enum is found rather than deleting it"
    )


def _enums_matching(predicate) -> list[str]:
    """Enums whose MEMBER SET matches — never their class name.

    A same-name sweep is exactly what missed these forks: each pair used
    different names for one concept.
    """
    return [f"{rel}::{name}" for rel, name, members in _declared_enums() if predicate(members)]


def test_the_enum_scan_reaches_the_repo():
    """A scan that parsed nothing would agree with every assertion above."""
    declared = _declared_enums()
    assert len(declared) >= _DECLARED_ENUM_FLOOR, (
        f"enum scan found only {len(declared)} enums — the matcher is broken, " f"not the tree"
    )


# --------------------------------------------------------------------------
# #14956 — the sanitizers store the enum VALUE, never the member NAME
# --------------------------------------------------------------------------

# All three graded findings as "HIGH"/"CRITICAL"/"MEDIUM" — the member *name*
# in a field that carries the *value*. Anything comparing a finding against
# ``Severity.HIGH.value`` silently matched none of them.
_SANITIZERS = (
    "autobot-backend/code_analysis/auto-tools/security_sanitizer.py",
    "autobot-backend/code_analysis/auto-tools/security_deep_sanitizer.py",
    "autobot-backend/code_analysis/auto-tools/playwright_sanitizer.py",
)


def _severity_dict_values(path: Path) -> list[ast.expr]:
    """Every ``"severity": <expr>`` dict entry in one module, by AST.

    Read rather than imported: these are standalone CLI scripts that mutate
    ``sys.path`` at import time, and this guard must not depend on that.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        value
        for node in ast.walk(tree)
        if isinstance(node, ast.Dict)
        for key, value in zip(node.keys, node.values)
        if isinstance(key, ast.Constant) and key.value == "severity"
    ]


@pytest.mark.parametrize("rel", _SANITIZERS)
def test_no_sanitizer_grades_a_finding_with_a_member_name(rel):
    path = REPO_ROOT / rel
    assert path.exists(), f"#14956: {rel} is gone — the guard has no target"
    values = _severity_dict_values(path)
    assert values, f"#14956: no severity field found in {rel} — the scan missed it"
    constants = [node.value for node in values if isinstance(node, ast.Constant)]
    for value in constants:
        assert value in {level.value for level in Severity}, (
            f"#14956: {rel} grades a finding {value!r}, which is not a Severity "
            f"value. Member names ('HIGH') are not values ('high')."
        )


def _load_tool_base():
    """Load the auto-tools skeleton without putting its directory on sys.path."""
    path = REPO_ROOT / "autobot-backend" / "code_analysis" / "auto-tools" / "tool_base.py"
    spec = importlib.util.spec_from_file_location("autobot_auto_tools_base", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_report_vocabulary_lives_in_one_place_and_reads_canonical_values():
    """Three copies of the same icon table became one, keyed on the enum."""
    base = _load_tool_base()
    assert base.SEVERITY_REPORT_ORDER, "the report ladder is empty"
    assert set(base.SEVERITY_REPORT_ORDER) <= set(Severity)
    ranked = [Severity.to_score(level) for level in base.SEVERITY_REPORT_ORDER]
    assert ranked == sorted(ranked, reverse=True), "the report ladder is not worst-first"
    for level in base.SEVERITY_REPORT_ORDER:
        assert base.severity_icon(level.value) == base.SEVERITY_REPORT_ICONS[level]


def test_the_rendered_report_text_survived_the_value_change():
    """#14956 changed what is stored, deliberately not what a reader sees."""
    base = _load_tool_base()
    assert base.severity_label(Severity.HIGH.value) == "HIGH"
    assert base.severity_label(Severity.CRITICAL.value) == "CRITICAL"
    assert base.severity_icon("not-a-severity") == base.UNRANKED_SEVERITY_ICON
    assert base.severity_label("not-a-severity") == "not-a-severity"


# --------------------------------------------------------------------------
# #14956 — an enum read must never be written INSIDE a string
# --------------------------------------------------------------------------

# The sweep's own regression, caught by CI and pinned here. Rewriting every
# `"severity": "<literal>"` by regex also rewrote one inside an endpoint
# docstring, turning a documented ```json response body into invalid JSON that
# no reader could copy. A docstring is prose: it is exempt from the ratchet, not
# a target for it. Any file with a literal in prose belongs in
# DELIBERATE_SEVERITY_LITERALS instead.
_ENUM_READ_IN_PROSE = re.compile(r"\bSeverity\.[A-Z_]+\.value")

# Floor for this scan. Counted from the modules that actually mention the enum,
# so an import that stops resolving cannot quietly empty the walk.
_ENUM_MENTION_FLOOR = 25


def _modules_mentioning_severity() -> list[tuple[str, str]]:
    """(path, source) for every module under the roots that names the enum."""
    found = []
    for rel in _tracked_python_files():
        if not (rel.startswith("autobot-backend/") or rel.startswith("autobot_shared/")):
            continue
        try:
            text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        except OSError:
            continue
        if "Severity." in text:
            found.append((rel, text))
    return found


def test_the_prose_scan_reaches_the_modules_that_use_the_enum():
    """An empty walk would agree that no docstring was ever mangled."""
    mentions = _modules_mentioning_severity()
    assert len(mentions) >= _ENUM_MENTION_FLOOR, (
        f"#14956: only {len(mentions)} modules mention Severity (floor "
        f"{_ENUM_MENTION_FLOOR}) — the scan is broken, not the tree"
    )


def test_no_enum_read_was_written_inside_a_string():
    offenders = []
    for rel, text in _modules_mentioning_severity():
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            if _ENUM_READ_IN_PROSE.search(node.value):
                offenders.append(f"{rel}:{node.lineno}")
    assert not offenders, (
        f"#14956: an enum read was written inside a string literal at "
        f"{sorted(offenders)}. Prose that shows a severity keeps the plain "
        f"value; add the file to DELIBERATE_SEVERITY_LITERALS instead."
    )
