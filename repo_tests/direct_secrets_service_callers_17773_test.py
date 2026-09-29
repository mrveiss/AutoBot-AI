# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Freeze the set of production modules that reach a secrets service directly (#17773).

``SecretsCoordinator`` is the enforcement point: it asks the secret's own scope
(#17772) before the vault grant decides. A module that imports a service class
instead bypasses that, and #17773 found **seven** such callers where the issue
had named two.

**Why this is keyed on the callee and not on an argument.** The obvious key is
``accessible_vaults=`` -- the keyword only a direct service read passes. It finds
the read callers and is blind to the one that matters most:
``EnvelopeSecretsService.delete`` takes **no authorizing vault at all**, so an
argument-keyed freeze would leave the only unscoped destructive call outside the
frozen set. That is the same narrow-population defect #17773 is about, reproduced
inside its own guard, so the key is the **class being imported**: a direct caller
must import it, whatever arguments it goes on to pass.

**Why imports and not a name search.** A text search over these files returns
four modules that merely *discuss* the classes in comments and docstrings
(``api/secrets.py``, ``api/envelope_secrets.py``, ``services/secrets_authz.py``,
``services/legacy_secrets_migrator.py``) and would freeze documentation as if it
were a call. Parsed instead, so prose about a service is not a use of it.

The set only shrinks. A new entry means a new bypass of the coordinator; route it
through ``SecretsCoordinator`` or, if it is genuinely a principal the coordinator
does not model, record the verdict on #17773 and add it here with the reason.
"""

from __future__ import annotations

import ast

import pytest
from repo_tests._paths import repo_root

#: Class names whose import means "this module talks to a secrets service directly".
_SERVICE_CLASSES = frozenset({"EnvelopeSecretsService", "SecretsService"})

#: Modules those classes are DEFINED in -- importing from yourself is not a bypass.
_SERVICE_MODULES = frozenset(
    {
        "autobot-backend/services/envelope_secrets_service.py",
        "autobot-backend/services/secrets_service.py",
    }
)

_TREES = ("autobot-backend", "autobot_shared")

#: Floor for the walk. A moved or renamed tree would scan nothing, and an empty
#: scan equals the frozen set minus everything -- which fails loudly, but for the
#: wrong reason. This makes "the walk stopped reaching the tree" its own failure.
_MIN_SCANNED = 2000

#: Every production module reaching a secrets service directly, with its #17773
#: verdict. ONLY SHRINKS.
_FROZEN_DIRECT_CALLERS = {
    # The enforcement point itself -- the one module that SHOULD hold the service.
    "autobot-backend/services/secrets_coordinator.py": "the coordinator; this is where the scope check lives",
    # Verdicts recorded on #17773.
    "autobot-backend/services/credential_reconcile.py": "cross-owner system sweep; no principal the coordinator models (#17773)",
    "autobot-backend/llm_shared/provider_auth.py": "tautological grant, unreachable today, latent (#17773)",
    "autobot-backend/services/credential_read.py": "owner is the row's, not the caller's; admin-gated, #13702's remaining half",
    "autobot-backend/services/llc_secrets_read.py": "sound: company_id validated against ctx.org_id by a route dependency",
    "autobot-backend/services/json_secrets_read.py": "SYSTEM-vault service read; should move to service_read (#17773)",
    "autobot-backend/services/provider_key_vault.py": "SYSTEM-vault service read; should move to service_read (#17773)",
    "autobot-backend/services/github_service_credential.py": "SYSTEM-vault service read; should move to service_read (#17773)",
    # Reached by the #17773 sweep but not yet given a per-caller verdict.
    "autobot-backend/services/credential_write.py": "no verdict yet (#17773)",
    "autobot-backend/services/orphan_repair_types.py": "no verdict yet (#17773)",
    "autobot-backend/services/workflow_secret_service.py": "no verdict yet (#17773)",
    "autobot-backend/services/agent_secrets_integration.py": "no verdict yet (#17773)",
    "autobot-backend/api/user_provider_credentials.py": "no verdict yet (#17773)",
    "autobot-backend/llm_shared/run_credential_loader.py": "no verdict yet (#17773)",
}


def _imports_a_service_class(source: str) -> bool:
    """True when *source* imports a secrets service class, by either import form.

    ``from services.envelope_secrets_service import EnvelopeSecretsService`` is
    the only form present today; the module form is handled too so this guard has
    no hole waiting for the first caller to spell it differently.
    """
    try:
        module = ast.parse(source)
    except SyntaxError:
        return False
    for node in ast.walk(module):
        if isinstance(node, ast.ImportFrom):
            if any(alias.name in _SERVICE_CLASSES for alias in node.names):
                return True
        elif isinstance(node, ast.Import):
            if any(alias.name.rsplit(".", 1)[-1].endswith("secrets_service") for alias in node.names):
                return True
    return False


def _is_production(rel: str) -> bool:
    return not (rel.endswith("_test.py") or "/tests/" in rel or "/test_" in rel)


def _scan() -> tuple[set[str], int]:
    """(modules importing a service class, production files scanned)."""
    root = repo_root()
    found: set[str] = set()
    scanned = 0
    for tree in _TREES:
        for path in (root / tree).rglob("*.py"):
            rel = path.relative_to(root).as_posix()
            if not _is_production(rel) or rel in _SERVICE_MODULES:
                continue
            scanned += 1
            if _imports_a_service_class(path.read_text(encoding="utf-8", errors="replace")):
                found.add(rel)
    return found, scanned


def test_the_walk_reaches_the_trees_it_claims() -> None:
    """Non-vacuity: an empty scan must fail as an empty scan, not as a diff."""
    _, scanned = _scan()
    assert scanned >= _MIN_SCANNED, (
        f"only {scanned} production .py file(s) reached under {_TREES}, expected at least "
        f"{_MIN_SCANNED} — the walk has stopped reaching these trees, which would make every "
        "entry below look removed"
    )


def test_no_new_module_reaches_a_secrets_service_directly() -> None:
    found, _ = _scan()
    added = sorted(found - set(_FROZEN_DIRECT_CALLERS))
    assert not added, (
        "these modules reach a secrets service directly and are not recorded:\n  "
        + "\n  ".join(added)
        + "\n\nRoute them through SecretsCoordinator, whose read/list ask the secret's own "
        "scope (#17772). If the caller is a principal the coordinator does not model, record "
        "the verdict on #17773 and add it here with the reason."
    )


def test_recorded_callers_that_no_longer_reach_the_service_are_removed() -> None:
    """The list only shrinks, so a stale entry has to be deleted, not left."""
    found, _ = _scan()
    stale = sorted(set(_FROZEN_DIRECT_CALLERS) - found)
    assert not stale, "recorded direct callers that no longer import a service class — remove them:\n  " + "\n  ".join(
        stale
    )


def test_every_recorded_caller_carries_a_reason() -> None:
    blank = sorted(path for path, reason in _FROZEN_DIRECT_CALLERS.items() if not reason.strip())
    assert not blank, "a recorded bypass without a reason is a bypass nobody decided:\n  " + "\n  ".join(blank)


def test_the_delete_path_still_takes_no_authorizing_vault() -> None:
    """The reason this guard is keyed on the class rather than on ``accessible_vaults=``.

    If ``delete`` ever gains a vault parameter, an argument-keyed freeze becomes
    viable and this guard's central justification changes — so that is a change
    this test should force someone to notice, not one that passes quietly.
    """
    source = (repo_root() / "autobot-backend/services/envelope_secrets_service.py").read_text(encoding="utf-8")
    delete = next(
        (
            node
            for node in ast.walk(ast.parse(source))
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "delete"
        ),
        None,
    )
    assert delete is not None, "EnvelopeSecretsService.delete not found — this guard's premise moved"
    params = {a.arg for a in delete.args.args} | {a.arg for a in delete.args.kwonlyargs}
    assert not (params & {"accessible_vaults", "actor_vaults"}), (
        "delete now takes an authorizing vault — an argument-keyed freeze is viable, so revisit "
        "this guard's docstring and the #17773 recommendation that it be keyed on the callee"
    )


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("from services.envelope_secrets_service import EnvelopeSecretsService\n", True),
        ("from services.secrets_service import SecretsService\n", True),
        ("from services.envelope_secrets_service import SecretAccessError\n", False),
        ('"""A docstring naming EnvelopeSecretsService in prose."""\n', False),
        ("# EnvelopeSecretsService is discussed in this comment\n", False),
        ("x = 'EnvelopeSecretsService'\n", False),
    ],
    ids=["from-import", "from-import-base", "exception-only", "docstring", "comment", "string-literal"],
)
def test_the_detector_reads_imports_not_prose(source: str, expected: bool) -> None:
    """Four real modules only discuss these classes; freezing those would be wrong."""
    assert _imports_a_service_class(source) is expected
