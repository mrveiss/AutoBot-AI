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

A module whose only use of the class is ``SecretsCoordinator(<service>)`` is not
listed: injecting a service into the enforcement point is the remediation, and a
guard that flagged it would penalise the fix it is asking for. The two #17773
callers holding a ``root_key`` can reach the coordinator no other way.

The set only shrinks. A new entry means a new bypass of the coordinator; route it
through ``SecretsCoordinator`` or, if it is genuinely a principal the coordinator
does not model, record the verdict on #17773 and add it here with the reason.
"""

from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

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


#: The enforcement point. A service handed to *this* constructor is being routed
#: THROUGH the coordinator, which is the remediation -- not a bypass of it.
_COORDINATOR = "SecretsCoordinator"


def _injected_into_the_coordinator(module: ast.Module) -> set[int]:
    """``id()`` of every ``Name`` node sitting inside a ``SecretsCoordinator(...)`` call.

    ``SecretsCoordinator(service=...)`` takes an injected service, and the two
    callers of #17773 that hold a ``root_key`` can only reach the coordinator by
    passing ``EnvelopeSecretsService(root_key=...)`` into it. They therefore keep
    importing the class while no longer calling it -- so an import-only check
    would report the **remediated** caller as an unremediated bypass, which is
    how a baseline teaches people to add an entry instead of fixing the code.

    Two narrowings, both from #17776 review:

    **The coordinator is recognised through an alias.** Keying on the literal name
    meant ``import SecretsCoordinator as Coordinator`` was not seen as injection, so
    a caller that HAD been remediated still read as a bypass -- the baseline pushing
    someone to add an entry rather than fix the code, which is the failure this
    docstring already warns about, reached by a different route.

    **The exemption no longer swallows the whole call.** Marking every ``Name``
    below ``SecretsCoordinator(...)`` exempted a direct service call that merely sat
    in an argument: ``SecretsCoordinator(EnvelopeSecretsService(k).read(...))`` runs
    the read before the coordinator receives anything, and that is exactly the
    unscoped call this guard exists to freeze. Only the service reference being
    *constructed and handed over* is injection, so the exemption is limited to an
    argument that is a bare service name or a direct ``Service(...)`` construction.
    A method call on a service is a call, wherever it is written.
    """
    coordinators = _coordinator_bindings(module)
    injected: set[int] = set()
    for node in ast.walk(module):
        if not (isinstance(node, ast.Call) and _refers_to_coordinator(node.func, coordinators)):
            continue
        for arg in [*node.args, *(kw.value for kw in node.keywords)]:
            if isinstance(arg, ast.Name):
                injected.add(id(arg))  # a service instance held in a local, handed over
            elif isinstance(arg, ast.Call) and isinstance(arg.func, ast.Name):
                injected.add(id(arg.func))  # `Service(...)` constructed inline as the argument
    return injected


def _coordinator_bindings(module: ast.Module) -> set[str]:
    """Every local name bound to ``SecretsCoordinator``, including import aliases."""
    names = {_COORDINATOR}
    for node in ast.walk(module):
        if isinstance(node, ast.ImportFrom):
            names.update(alias.asname or alias.name for alias in node.names if alias.name == _COORDINATOR)
    return names


def _refers_to_coordinator(func: ast.expr, coordinators: set[str]) -> bool:
    """``Coordinator(...)`` or ``module.SecretsCoordinator(...)``."""
    if isinstance(func, ast.Name):
        return func.id in coordinators
    return isinstance(func, ast.Attribute) and func.attr == _COORDINATOR


def _imports_a_service_class(source: str) -> bool:
    """True when *source* reaches a secrets service class other than by injection.

    ``from services.envelope_secrets_service import EnvelopeSecretsService`` is
    the only import form present today; the module form is handled too so this
    guard has no hole waiting for the first caller to spell it differently.

    A module whose ONLY use of the class is inside ``SecretsCoordinator(...)`` is
    not a direct caller: it is injecting a service into the enforcement point.
    Any other use counts, including a bare annotation, because a module typing a
    service parameter is receiving one in order to call it.

    Raises ``SyntaxError`` on a source that will not parse. It used to return
    ``False`` there, which made an unparseable module indistinguishable from one
    that imports nothing -- a skip wearing a clean verdict. ``_scan`` records it
    as a skip instead, and ``test_every_module_in_the_population_parses`` makes
    it loud.
    """
    module = ast.parse(source)

    imported: set[str] = set()
    for node in ast.walk(module):
        if isinstance(node, ast.ImportFrom):
            imported.update(alias.asname or alias.name for alias in node.names if alias.name in _SERVICE_CLASSES)
        elif isinstance(node, ast.Import):
            if any(alias.name.rsplit(".", 1)[-1].endswith("secrets_service") for alias in node.names):
                return True
    if not imported:
        return False

    injected = _injected_into_the_coordinator(module)
    return any(
        isinstance(node, ast.Name) and node.id in imported and id(node) not in injected for node in ast.walk(module)
    )


def _is_production(rel: str) -> bool:
    return not (rel.endswith("_test.py") or "/tests/" in rel or "/test_" in rel)


def _discover(root: Path) -> list[str]:
    """The guard's population: production modules under ``_TREES``.

    ``_scan`` iterates exactly what this returns, so the enumeration and the
    count are one code path. Two walks that must agree by inspection is how a
    floor ends up measured against one question and asserted against another --
    the defect this guard's own subject is an instance of.

    Returns ``[]`` on an empty tree rather than raising: ``reach_declarations_test``
    hands every declaration an empty repository and needs an empty *result* to
    prove the floor can fire.
    """
    found: list[str] = []
    for tree in _TREES:
        for path in (root / tree).rglob("*.py"):
            rel = path.relative_to(root).as_posix()
            if _is_production(rel) and rel not in _SERVICE_MODULES:
                found.append(rel)
    return sorted(found)


#: Migrated from a hand-rolled ``_MIN_SCANNED = 2000`` (#15928 requires
#: ``declare``; the meta-test caught this one). The old constant was NOT carried
#: across -- 2000 was never measured, and against the real population it left 704
#: files of slack, enough to lose ``autobot_shared`` whole and still read clean.
#:
#: Measured 2026-09-30 on this branch at 601bd5a0, by a throwaway script running
#: this same filter: **2704** files (autobot-backend 2493, autobot_shared 211),
#: of which 0 fail to parse, so ``completed`` == ``discover`` today.
#:
#: Do not reconcile this against the 3,027 in ``model_revision_pinning_enforced_
#: 17804_test``. That floor counts tracked python files repo-wide; this one counts
#: two trees, production only, minus the two service definitions. Different
#: populations, so neither number validates the other.
#:
#: floor=2600 against a measured 2704 leaves **104 files of downward margin** --
#: the number to watch when re-pinning. It is chosen to still fire on the failure
#: this guard exists to catch: losing ``autobot_shared`` drops the walk to 2493
#: and losing the backend drops it to 211, both well under the floor. growth=200
#: (~7% of the population, this repo's rough maintenance interval) keeps
#: ``verify_floor`` quiet until the tree reaches 2800. skips=0 is measured, not
#: assumed: nothing is skipped silently, because an unparseable file fails
#: ``test_every_module_in_the_population_parses`` outright.
REACH = declare(
    "direct-secrets-service-callers",
    discover=_discover,
    floor=2600,
    growth=200,
    what="production modules under the backend and shared trees",
)


@lru_cache(maxsize=1)
def _scan() -> tuple[frozenset[str], int, tuple[str, ...]]:
    """(modules importing a service class, files examined, files that would not parse).

    Non-vacuity lives in ``REACH.examined`` (the walk reached the trees) and
    ``REACH.completed`` (it finished reading them), rather than in a floor of
    this module's own -- candidates are not coverage.

    **Memoised, and that is a cost fix rather than a style one.** Four tests in
    this module need the same sweep, and each one re-read and re-parsed all 2,704
    files: measured 12-15s per test, 40.7s for the module. One sweep serves all
    four at 14.6s. `Reach.population` already memoises the *walk*; the parse is
    the expensive half and was repeated. Returns immutable types so a cached
    result cannot be mutated by one test and observed by the next.
    """
    root = repo_root()
    population = REACH.examined(root)
    found: set[str] = set()
    unparsed: list[str] = []
    for rel in population:
        try:
            if _imports_a_service_class((root / str(rel)).read_text(encoding="utf-8", errors="replace")):
                found.add(str(rel))
        except SyntaxError:
            unparsed.append(str(rel))
    REACH.completed(len(population) - len(unparsed))
    return frozenset(found), len(population), tuple(unparsed)


def test_every_module_in_the_population_parses() -> None:
    """A file that will not parse is a skip, not a clean file."""
    _, _, unparsed = _scan()
    assert not unparsed, (
        "these modules could not be parsed, so the freeze below says nothing about them:\n  "
        + "\n  ".join(unparsed)
        + "\n\nA syntax error here is a hole in the sweep, not a clean module."
    )


def test_no_new_module_reaches_a_secrets_service_directly() -> None:
    found, _, _ = _scan()
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
    found, _, _ = _scan()
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
        (
            "from services.envelope_secrets_service import EnvelopeSecretsService\n"
            "raw = EnvelopeSecretsService().read(s, secret_id=i, accessible_vaults=v)\n",
            True,
        ),
        (
            "from services.secrets_service import SecretsService\n"
            "rows = SecretsService().list_for_vaults(s, accessible_vaults=v)\n",
            True,
        ),
        # An import with no use is dead code, not a caller -- `flake8` F821/F401 owns that,
        # and this guard is about modules that REACH a service. Pinned so the distinction is
        # a decision rather than an accident of the detector requiring a Name load.
        ("from services.envelope_secrets_service import EnvelopeSecretsService\n", False),
        ("from services.envelope_secrets_service import SecretAccessError\n", False),
        ('"""A docstring naming EnvelopeSecretsService in prose."""\n', False),
        ("# EnvelopeSecretsService is discussed in this comment\n", False),
        ("x = 'EnvelopeSecretsService'\n", False),
        (
            "from services.envelope_secrets_service import EnvelopeSecretsService\n"
            "c = SecretsCoordinator(EnvelopeSecretsService(root_key=k))\n",
            False,
        ),
        (
            "from services.envelope_secrets_service import EnvelopeSecretsService\n"
            "c = SecretsCoordinator(EnvelopeSecretsService(root_key=k))\n"
            "raw = EnvelopeSecretsService().read(s, secret_id=i, accessible_vaults=v)\n",
            True,
        ),
        # #17776 review: injection through an import alias is still injection.
        (
            "from services.secrets_coordinator import SecretsCoordinator as Coordinator\n"
            "from services.envelope_secrets_service import EnvelopeSecretsService\n"
            "c = Coordinator(EnvelopeSecretsService(root_key=k))\n",
            False,
        ),
        # ...and the contrast: a direct read does not become injection by sitting in an
        # argument. It runs before the coordinator receives anything.
        (
            "from services.envelope_secrets_service import EnvelopeSecretsService\n"
            "c = SecretsCoordinator(EnvelopeSecretsService(k).read(s, secret_id=i, accessible_vaults=v))\n",
            True,
        ),
        # The conservative boundary, pinned as a decision rather than left to chance:
        # constructing the service into a local and handing THAT over is still a finding.
        # Exempting it needs dataflow, and the same dataflow would hide `svc.read(...)`
        # -- the detector cannot see a call through a local alias either, so a rule that
        # exempted the construction would make the whole module invisible. A false
        # positive here costs a conversation; that false negative costs the freeze.
        (
            "from services.envelope_secrets_service import EnvelopeSecretsService\n"
            "svc = EnvelopeSecretsService(root_key=k)\n"
            "c = SecretsCoordinator(svc)\n",
            True,
        ),
        # A module-qualified coordinator is still the coordinator.
        (
            "import services.secrets_coordinator as sc\n"
            "from services.envelope_secrets_service import EnvelopeSecretsService\n"
            "c = sc.SecretsCoordinator(EnvelopeSecretsService(root_key=k))\n",
            False,
        ),
    ],
    ids=[
        "imported-and-called",
        "imported-and-called-base",
        "imported-but-unused",
        "exception-only",
        "docstring",
        "comment",
        "string-literal",
        "injected-into-the-coordinator",
        "injected-and-also-called-directly",
        "injected-through-an-import-alias",
        "direct-read-inside-a-coordinator-argument",
        "instance-built-into-a-local-stays-a-finding",
        "module-qualified-coordinator",
    ],
)
def test_the_detector_reads_imports_not_prose(source: str, expected: bool) -> None:
    """Four real modules only discuss these classes; freezing those would be wrong."""
    assert _imports_a_service_class(source) is expected
