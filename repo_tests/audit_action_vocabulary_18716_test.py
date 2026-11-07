# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#18716 -- one audit action vocabulary: the dotted ``AuditAction`` enum.

Before this, one concept had up to eight stored spellings (login: ``auth.login``,
``login_successful``, ``user.login``, ``login_success``, ``login``, ...), and every reader matched
exactly one of them. The owner chose the dotted ``<resource>.<verb>`` form (2026-10-20). This guard
keeps it from re-forking: every action a writer passes is

* an ``AuditAction`` member value (``autobot-backend/services/audit/taxonomy.py``), or
* an open-ended family (``llm_command_parser:*``, ``ai_line.*``, ``execute_task_*``), or
* passed to a *boundary* writer (``audit_row`` / ``_audit_log``) that maps it through
  ``autobot_shared.audit_actions`` -- the identity services keep their public
  ``IdentityAuditAction`` constants, or
* listed in ``audit_action_vocabulary_baseline_18716.LEGACY_SPELLINGS`` with a reason (shrink-only).

Scope of the reading: writer *calls* in ``autobot-backend``, ``autobot_shared`` and
``autobot-slm-backend`` (see ``_audit_action_scan`` for what is and is not resolvable). It says
nothing about stored rows; those are rewritten only through the approved data migration (#17038).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from repo_tests._audit_action_scan import BOUNDARY_WRITERS, Written, read_enums, scan_source
from repo_tests._audit_action_vocabulary_scope import ROOTS, scoped_sources, source_python
from repo_tests._paths import repo_root
from repo_tests._reach import declare
from repo_tests.audit_action_vocabulary_baseline_18716 import LEGACY_SPELLINGS, OPEN_ENDED_PREFIXES

from autobot_shared.audit_actions import ACTION_ALIASES, canonical_action, spellings_of
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_ENUMS = {"AuditAction": {"LOGIN": "auth.login"}, "IdentityAuditAction": {"LOGIN_SUCCESS": "login_success"}}


def _population(root: Path) -> list[str]:
    try:
        return scoped_sources(root)
    except EmptyEnumeration:
        return []


def _all_python(root: Path) -> int:
    try:
        return sum(1 for rel in tracked_paths(root, *ROOTS) if rel.endswith(".py"))
    except EmptyEnumeration:
        return 0


#: ~60% of tracked python under the three roots is non-test source when measured; 0.4 leaves room for tests to grow.
REACH = declare(
    "audit-action-vocabulary",
    discover=_population,
    reference=_all_python,
    min_fraction=0.4,
    what="non-test python source scanned for audit writer calls",
    roots=ROOTS,
)


def _unaccepted(written: list[Written], members: set[str]) -> list[Written]:
    bad = []
    for w in written:
        if w.kind == "unresolved" or w.value.startswith(OPEN_ENDED_PREFIXES) or w.value in LEGACY_SPELLINGS:
            continue
        mapped = w.writer in BOUNDARY_WRITERS and canonical_action(w.value) in members
        if w.kind == "prefix" or not (w.value in members or mapped):
            bad.append(w)
    return bad


@pytest.fixture(scope="module")
def live() -> tuple[list[Written], set[str]]:
    root = repo_root()
    REACH.verify_floor(root)
    enums = read_enums(root)
    written: list[Written] = []
    done = []
    for rel in REACH.examined(root):
        written.extend(scan_source(rel, (root / rel).read_text(encoding="utf-8"), enums))
        done.append(rel)
    REACH.completed(len(done), root)
    return written, set(enums["AuditAction"].values())


def test_every_written_action_is_canonical_or_listed(live) -> None:
    written, members = live
    assert members, "the AuditAction enum parsed empty: the guard read nothing (#18716)"
    bad = _unaccepted(written, members)
    assert not bad, "audit writers pass a spelling outside AuditAction (add the member, then write it):\n" + "\n".join(
        f"  {w.rel}:{w.line} {w.writer}({w.value!r})" for w in bad
    )


def test_the_baseline_only_shrinks(live) -> None:
    written, members = live
    seen = {w.value for w in written if w.kind == "literal"}
    stale = sorted(s for s in LEGACY_SPELLINGS if s not in seen)
    promoted = sorted(s for s in LEGACY_SPELLINGS if s in members or s in ACTION_ALIASES)
    assert not stale, f"baseline entries no writer passes any more -- delete them: {stale}"
    assert not promoted, f"baseline entries that are now members or aliases -- delete them: {promoted}"


def test_the_scan_saw_the_concept_writers(live) -> None:
    written, _ = live
    seen = {(w.rel, w.value) for w in written}
    for rel, value in (
        ("autobot-backend/auth_middleware.py", "auth.login"),
        ("autobot-backend/auth_middleware.py", "auth.logout"),
        ("autobot-backend/api/files.py", "file.delete"),
        ("autobot-backend/middleware/audit_middleware.py", "auth.login"),
        ("autobot-slm-backend/api/sso_auth.py", "auth.login"),
        ("autobot_shared/user_management/user_service_access.py", "login_success"),
    ):
        assert (rel, value) in seen, f"control: {rel} passes {value!r} and the scan did not see it"


def test_every_alias_targets_an_audit_action_member(live) -> None:
    _, members = live
    assert not {new for new in ACTION_ALIASES.values() if new not in members}
    assert not {old for old in ACTION_ALIASES if old in members}, "an alias must not shadow a canonical spelling"


@pytest.mark.parametrize(
    ("old", "canonical"),
    [
        ("login_successful", "auth.login"),
        ("user.login", "auth.login"),
        ("login_success", "auth.login"),
        ("login", "auth.login"),
        ("logout", "auth.logout"),
        ("user.logout", "auth.logout"),
        ("config.changed", "config.update"),
        ("file_delete", "file.delete"),
        ("conversation_file_delete", "file.delete"),
        ("user_created", "user.create"),
        ("role_assigned", "role.assign"),
        ("password_changed", "password.change"),
        ("api_key_created", "api_key.create"),
        ("api_key_revoked", "api_key.revoke"),
    ],
)
def test_every_spelling_of_a_concept_resolves_to_one_member(old: str, canonical: str) -> None:
    assert canonical_action(old) == canonical
    assert old in spellings_of(canonical)
    assert canonical_action(canonical) == canonical


def test_slm_key_gate_decisions_stay_out_of_the_lifecycle_vocabulary() -> None:
    for decision in ("api_key_request", "api_key_rejected", "api_key_refused_expired"):
        assert canonical_action(decision) == decision


def test_bare_knowledge_verbs_are_not_aliased() -> None:
    assert all(canonical_action(v) == v for v in ("create", "delete", "update", "view", "search"))


# --- contrast fixtures: the guard must be able to fail --------------------------------------------------


def _scan(src: str) -> list[Written]:
    return scan_source("pkg/mod.py", src, _ENUMS)


def test_a_legacy_literal_on_a_plain_writer_is_flagged() -> None:
    assert _unaccepted(_scan('security_layer.audit_log("login_successful", "u", "success", {})'), {"auth.login"})


def test_the_canonical_literal_and_member_pass() -> None:
    src = 'a.audit_log("auth.login", "u")\nb.audit_log(action=AuditAction.LOGIN.value)'
    assert not _unaccepted(_scan(src), {"auth.login"})


def test_a_legacy_constant_on_a_boundary_writer_passes_but_not_on_another() -> None:
    legacy = "self._audit_log(IdentityAuditAction.LOGIN_SUCCESS, 'user')"
    assert not _unaccepted(_scan(legacy), {"auth.login"})
    assert _unaccepted(_scan("x.audit_log(IdentityAuditAction.LOGIN_SUCCESS)"), {"auth.login"})


def test_a_module_constant_and_a_dict_lookup_are_resolved() -> None:
    src = 'OP = "file_delete"\nTABLE = {"a": "secret.x", "b": "auth.login"}\nx.audit_log(OP)\ny.audit_log(TABLE[k])\n'
    values = {w.value for w in _scan(src)}
    assert values == {"file_delete", "secret.x", "auth.login"}


def test_an_unknown_f_string_prefix_is_flagged_and_a_known_family_passes() -> None:
    assert _unaccepted(_scan('x.audit_log(f"made_up_{k}")'), set())
    assert not _unaccepted(_scan('x.audit_log(f"ai_line.{k}")'), set())


def test_a_forwarder_is_reported_unresolved_not_guessed() -> None:
    found = _scan("def f(action):\n    x.audit_log(action)\n")
    assert [w.kind for w in found] == ["unresolved"]


def test_exclusion_is_judged_on_the_repo_relative_path_not_the_checkout_location() -> None:
    # A checkout that lives under a directory called "tests" must not make every file look like a test (#18972).
    assert source_python("autobot-backend/api/files.py")
    assert not source_python("autobot-backend/tests/test_x.py")
    assert not source_python("autobot-backend/api/files_test.py")
    assert source_python("autobot-backend/api/latest.py")
