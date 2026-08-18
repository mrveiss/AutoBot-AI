# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Guards for the two live defects in ``autobot-infrastructure/shared/scripts`` that
no flake8 code can see (#14507).

Both went live when #14504 (#14405) repaired the F821s that had made these
modules raise ``NameError`` at import. Neither is reachable by pyflakes:

* a shell placeholder pasted into a **plain** string literal is just a string
  — the two sibling sites #14504 fixed were f-strings, where the undefined
  name was visible;
* pyflakes never checks that an import target *resolves*, so a script can be
  F821-clean and still die on its own import block.

These tests live under ``repo_tests/`` rather than beside the scripts because
``autobot-infrastructure/`` is in no pytest ``testpaths`` entry and in no CI
pytest invocation — a test placed next to the module would never run.
"""

import ast
import asyncio
import importlib.util
import logging
import pathlib
import sys
from unittest.mock import create_autospec

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
_SCRIPTS = _REPO_ROOT / "autobot-infrastructure" / "shared" / "scripts"
_BACKEND = _REPO_ROOT / "autobot-backend"


def _load_by_path(path: pathlib.Path, module_name: str):
    """Import a standalone script by path — its directory is not a package."""
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def report_processing(tmp_path_factory):
    """Load ``report_processing_system`` with the project root pinned to a temp tree.

    The module calls ``logging.basicConfig`` with a ``FileHandler`` under
    ``project_root()`` at import time, so an unpinned import would drop a log
    file into the checkout.  ``project_root()`` is deliberately uncached and
    honours ``AUTOBOT_PROJECT_ROOT`` first, so setting it redirects the write.
    """
    root = tmp_path_factory.mktemp("project_root")
    monkey = pytest.MonkeyPatch()
    monkey.setenv("AUTOBOT_PROJECT_ROOT", str(root))
    before = list(logging.getLogger().handlers)
    try:
        module = _load_by_path(
            _SCRIPTS / "utilities" / "report_processing_system.py",
            "infra_scripts_report_processing_system_14507",
        )
        yield module, root
    finally:
        for handler in list(logging.getLogger().handlers):
            if handler not in before:
                logging.getLogger().removeHandler(handler)
                handler.close()
        monkey.undo()


# --------------------------------------------------------------------------
# Defect 1 — an unexpanded shell placeholder as a Python string default
# --------------------------------------------------------------------------


def test_default_coordinator_base_path_is_a_resolved_directory(report_processing):
    """The default ``base_path`` resolves through ``project_root()``, not a shell literal.

    Pre-fix: ``base_path`` defaults to the literal
    ``"${AUTOBOT_PROJECT_ROOT:-/opt/autobot/code_source}"``, so the equality
    against the resolved root fails (and the directory named by that string
    can never exist).  Post-fix: the coordinator — and both agents it builds —
    point at the real root.
    """
    module, root = report_processing

    coordinator = module.ReportProcessingCoordinator()

    assert "${" not in str(coordinator.base_path)
    assert pathlib.Path(coordinator.base_path) == root
    assert coordinator.discovery_agent.base_path == root
    assert coordinator.archive_agent.base_path == root


# --------------------------------------------------------------------------
# Defect 1, second half — is an all-empty discovery a success?
# --------------------------------------------------------------------------


def test_discovery_raises_when_the_base_path_is_not_a_directory(report_processing):
    """A discovery root that does not exist is an error, not an empty result.

    ``Path.rglob`` yields nothing for a missing directory rather than raising,
    which is what let a coordinator aimed at an unexpanded shell expression
    report full success having found nothing.

    Pre-fix: ``discover_reports()`` returns ``{"test_results": [], ...}`` and
    raises nothing, so ``pytest.raises`` fails.  Post-fix: ``NotADirectoryError``.
    """
    module, root = report_processing

    agent = module.ReportDiscoveryAgent(str(root / "does-not-exist"))

    with pytest.raises(NotADirectoryError) as excinfo:
        agent.discover_reports()
    assert "does-not-exist" in str(excinfo.value)


def test_an_empty_but_readable_root_is_a_warning_not_a_failure(report_processing, caplog):
    """A readable root holding no reports stays a success — and says so out loud.

    This is the legitimate empty case: a fresh checkout, or a tree whose
    reports a previous run already archived.  Failing on it would be wrong, so
    the honest signal is a warning that names the directory.

    Pre-fix: the run is silent — no warning is emitted — so the ``caplog``
    assertion fails while the "returns empty" half passes.  Post-fix: every
    category is empty, nothing raises, and the warning names the path.
    """
    module, root = report_processing
    empty_root = root / "empty-tree"
    empty_root.mkdir()

    agent = module.ReportDiscoveryAgent(str(empty_root))

    with caplog.at_level(logging.WARNING, logger=agent.logger.name):
        discovered = agent.discover_reports()

    assert discovered and all(files == [] for files in discovered.values())
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings, "an all-empty discovery must announce itself"
    assert str(empty_root) in warnings[0].getMessage()


def test_a_populated_root_still_discovers_its_reports(report_processing):
    """The guard does not swallow the working case it is wrapped around.

    It also pins the de-duplication: ``security_report.json`` matches both the
    ``*report*`` and ``*.json`` patterns, and the scan used to append it once
    per matching pattern — inflating every count the mission reports and
    queueing a second archival of a file the first one had already moved.

    Pre-fix: the file is discovered twice, so the count assertion fails.
    Post-fix: exactly one entry.  (The category is not asserted:
    ``_categorize_file`` matches on the whole path, and pytest's own temp
    directory contains "pytest".)
    """
    module, root = report_processing
    populated = root / "populated"
    populated.mkdir()
    report = populated / "security_report.json"
    report.write_text("{}", encoding="utf-8")

    discovered = module.ReportDiscoveryAgent(str(populated)).discover_reports()

    found = [f.path for files in discovered.values() for f in files]
    assert found == [str(report)]


# --------------------------------------------------------------------------
# Defect 2 — an import target that does not resolve, and two dead call sites
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def populate_kb():
    """Import ``populate_knowledge_base``, restoring ``sys.path`` afterwards.

    Pre-fix this raises ``ModuleNotFoundError: No module named 'knowledge_base'``
    at module scope: the script inserted its own grandparent
    (``autobot-infrastructure/shared``) on ``sys.path`` and the module it wanted
    lives in ``autobot-backend``, which was never on the path.
    """
    before = list(sys.path)
    try:
        yield _load_by_path(_SCRIPTS / "populate_knowledge_base.py", "infra_scripts_populate_knowledge_base_14507")
    finally:
        sys.path[:] = before


@pytest.fixture(scope="module")
def fresh_kb_setup():
    """Import ``setup/knowledge/fresh_kb_setup``, restoring ``sys.path`` afterwards.

    Same defect as ``populate_knowledge_base``: pre-fix its KB import target is
    ``knowledge_base``, reachable only from ``autobot-backend``, which the
    script never put on the path.  Its own success message tells the operator
    to run ``populate_knowledge_base.py`` next, so the pair broke together.
    """
    before = list(sys.path)
    try:
        yield _load_by_path(
            _SCRIPTS / "setup" / "knowledge" / "fresh_kb_setup.py",
            "infra_scripts_fresh_kb_setup_14507",
        )
    finally:
        sys.path[:] = before


@pytest.mark.parametrize(
    ("script", "loader"),
    [
        ("populate_knowledge_base.py", "populate_kb"),
        ("setup/knowledge/fresh_kb_setup.py", "fresh_kb_setup"),
    ],
)
def test_every_absolute_import_target_in_the_script_resolves(request, script, loader):
    """Each top-level import target the script names is locatable after its own path setup.

    pyflakes reports F401/F821 but never checks that an import *resolves*, so
    "0 findings" and "cannot run" were both true of this script at once.

    Pre-fix: the fixture itself raises ``ModuleNotFoundError`` on
    ``knowledge_base``, so this errors out.  Post-fix: the script has put
    ``autobot-backend`` on ``sys.path`` and every target — including the
    function-scoped ``knowledge`` import — is found.
    """
    request.getfixturevalue(loader)  # the script performs its own sys.path setup
    source = (_SCRIPTS / script).read_text(encoding="utf-8")
    targets = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            targets.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            targets.add(node.module.split(".")[0])

    assert "knowledge" in targets, "the knowledge-base import must still be exercised"
    unresolvable = sorted(name for name in targets if importlib.util.find_spec(name) is None)
    assert unresolvable == []


def test_the_script_ingests_through_a_method_knowledge_base_actually_has(populate_kb, tmp_path):
    """``add_single_file`` calls an ingest method that exists on the real mixin.

    The fake is ``create_autospec`` of the real ``DocumentsMixin``, so it
    answers exactly the names that class defines and raises ``AttributeError``
    for anything else — and produces an ``AsyncMock`` for an ``async def``, so
    a missing ``await`` could not pass either.

    Pre-fix: the script called ``kb.add_file(...)``, which the mixin chain
    defines nowhere, so the autospec raises ``AttributeError``.  Post-fix: it
    calls ``add_document_from_file`` with the category it computed.
    """
    if str(_BACKEND) not in sys.path:
        sys.path.insert(0, str(_BACKEND))
    from knowledge.documents import DocumentsMixin

    assert not hasattr(DocumentsMixin, "add_file")

    kb = create_autospec(DocumentsMixin, instance=True)
    kb.add_document_from_file.return_value = {"status": "success"}
    doc = tmp_path / "docs" / "developer" / "CLAUDE_GIT.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("# git\n", encoding="utf-8")

    success, result = asyncio.run(populate_kb.add_single_file(str(doc), tmp_path, kb))

    assert success is True and result == {"status": "success"}
    kwargs = kb.add_document_from_file.await_args.kwargs
    assert kwargs["file_path"] == str(doc)
    assert kwargs["category"] == "developer-docs"


def test_the_search_smoke_test_uses_the_canonical_search_parameter(populate_kb):
    """The post-ingest smoke queries call ``search`` with a parameter it accepts.

    The fake mirrors the real basic-path signature (#10666 consolidated the
    three search paths onto ``top_k``); it takes no ``n_results``.

    Pre-fix: the script passed ``n_results=2`` and this raises ``TypeError``.
    Post-fix: every smoke query runs and is recorded.
    """
    seen = []

    class FakeKnowledgeBase:
        async def search(self, query, top_k=10, similarity_top_k=None, filters=None, mode="auto"):
            seen.append((query, top_k))
            return [{"metadata": {"relative_path": "README.md"}}]

    asyncio.run(populate_kb.run_search_smoke_tests(FakeKnowledgeBase()))

    assert seen == [(query, 2) for query in populate_kb.SEARCH_SMOKE_QUERIES]


def test_fresh_kb_setup_smoke_test_uses_the_real_knowledge_base_surface(fresh_kb_setup):
    """``fresh_kb_setup``'s post-init smoke test calls methods the real KB defines.

    The ingest half is ``create_autospec`` of the real ``DocumentsMixin``, so
    it raises ``AttributeError`` for any name that class does not define and
    produces an ``AsyncMock`` for an ``async def``.  The search half mirrors the
    real basic-path signature, which takes ``top_k`` and no ``n_results``.

    Pre-fix: the script called ``kb.add_file(...)`` (``AttributeError``) and
    ``kb.search(..., n_results=2)`` (``TypeError``).  Post-fix: both land, and
    the FT.INFO walk the sibling test already covers reports success.
    """
    if str(_BACKEND) not in sys.path:
        sys.path.insert(0, str(_BACKEND))
    from knowledge.documents import DocumentsMixin

    searches = []

    class FakeKnowledgeBase:
        def __init__(self):
            self._docs = create_autospec(DocumentsMixin, instance=True)
            self._docs.add_document_from_file.return_value = {"status": "success"}

        def __getattr__(self, name):
            return getattr(self._docs, name)

        async def search(self, query, top_k=10, similarity_top_k=None, filters=None, mode="auto"):
            searches.append((query, top_k))
            return []

    class FakeRedis:
        def execute_command(self, *args):
            if args[0] == "FT._LIST":
                return ["llama_index"]
            if args[0] == "FT.INFO":
                return ["attributes", [["identifier", "vector", "attribute", "vector", "dim", "768"]]]
            return "OK"

    kb = FakeKnowledgeBase()

    assert asyncio.run(fresh_kb_setup._test_knowledge_base(kb, FakeRedis())) is True
    assert kb._docs.add_document_from_file.await_args.kwargs["category"] == "documentation"
    assert searches == [("AutoBot features", 2)]
