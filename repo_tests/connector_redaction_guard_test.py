# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every KB connector's content reaches redact_content before persistence (#16985).

#13708/#16895 built the credential redactor and found gdrive/onedrive's
fetch_content bypassing it. Rather than repeat that per-connector patch across
the other 11 connectors, redaction moved to the one place every connector's
fetched content already converges: AbstractConnector._ingest_content
(knowledge/connectors/base.py), called by _process_change (the standard sync
path), and also directly by external_adapter.py's message-stream handler and
web_crawler.py's batch-result handler -- both bypass _process_change but still
route through _ingest_content, so the chokepoint covers them too.

This guard does NOT hand-enumerate connector names (repo_tests/
ingestion_redaction_guard_test.py, #16895's guard, did that deliberately for a
fixed 3-item list; this one is the opposite case, precisely because 66 asked
for a 12th connector to be unable to skip it). Discovery is by CLASS: every
*.py file in knowledge/connectors/ (except tests/__init__) is imported so its
class definitions run, then every AbstractConnector subclass actually defined
is checked against the running interpreter's own class hierarchy -- so a new
connector file lands in this sweep automatically, with no list to update.

A connector could still defeat the chokepoint by overriding _ingest_content
itself; the sweep catches that too (checked per-class below), and the
negative control proves the override-detection line, not just the "did every
class get imported" line -- those are different failure modes and a guard
that only tested one would report the same green for both.
"""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

REPO_ROOT = repo_root()


def _is_importable_module(rel: str) -> bool:
    name = Path(rel).name
    return not name.startswith("test_") and not name.endswith("_test.py") and name != "__init__.py"


def _connector_module_files(root: Path) -> list[str]:
    """Every importable *.py directly under knowledge/connectors/ (not tests/testing/).

    ``*.py`` on tracked_paths does not descend into subdirectories, so this
    naturally excludes the tests/ and testing/ packages without listing them.
    """
    try:
        tracked = tracked_paths(root, "autobot-backend/knowledge/connectors/*.py")
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if _is_importable_module(rel)]


#: Bound at the 22 importable files (connector implementations plus shared
#: helpers like auth.py/registry.py/scheduler.py -- importing a non-connector
#: helper is harmless, it just contributes no new AbstractConnector subclass)
#: measured when this guard was added.
REACH = declare(
    "connector-redaction-sweep",
    discover=_connector_module_files,
    floor=22,
    growth=3,
    skips=0,
    what="importable files under knowledge/connectors/",
)


def _module_name(rel: str) -> str:
    # "autobot-backend/knowledge/connectors/gdrive.py" -> "knowledge.connectors.gdrive"
    # (autobot-backend/ is on pythonpath -- see pytest.ini -- so it is not part of the name)
    without_prefix = rel.removeprefix("autobot-backend/")
    return without_prefix[: -len(".py")].replace("/", ".")


def _import_all_connector_modules() -> int:
    """Import every discovered file so its class bodies (and @register decorators) run.

    Returns the count actually imported, for REACH.completed() -- a module
    that fails to import is a real gap in this sweep's coverage, not a skip.
    """
    imported = 0
    for rel in REACH.examined(REPO_ROOT):
        importlib.import_module(_module_name(rel))
        imported += 1
    return imported


def _all_connector_subclasses(base: type) -> set[type]:
    """Every subclass of *base*, transitively (GiteaConnector-style multi-level trees included)."""
    direct = set(base.__subclasses__())
    return direct | {sub for cls in direct for sub in _all_connector_subclasses(cls)}


def _overrides_ingest_content(cls: type, base: type) -> bool:
    """True if *cls* defines its own _ingest_content instead of inheriting *base*'s."""
    return cls._ingest_content is not base._ingest_content


def test_the_base_chokepoint_itself_calls_redact_content():
    from knowledge.connectors.base import AbstractConnector

    source = inspect.getsource(AbstractConnector._ingest_content)
    assert "redact_content(" in source, (
        "AbstractConnector._ingest_content no longer calls redact_content(...) -- every "
        "connector's fetched content converges here before kb.store_fact(); losing this call "
        "means every connector loses redaction at once (#16985)."
    )


def test_every_discovered_connector_class_routes_through_the_chokepoint():
    _import_all_connector_modules()
    REACH.completed(len(REACH.population(REPO_ROOT)))

    from knowledge.connectors.base import AbstractConnector

    subclasses = _all_connector_subclasses(AbstractConnector)
    assert subclasses, "no AbstractConnector subclasses found after importing every connector module"

    overriding = {cls.__module__ + "." + cls.__qualname__ for cls in subclasses if _overrides_ingest_content(cls, AbstractConnector)}
    assert not overriding, (
        f"connector class(es) override _ingest_content instead of inheriting the redaction "
        f"chokepoint: {sorted(overriding)}. Either remove the override, or -- if it is "
        f"genuinely needed -- confirm its own body calls redact_content(...) and add it to an "
        f"explicit exception list here with that evidence, not a silent pass (#16985)."
    )


def test_negative_control_an_overriding_connector_is_caught():
    """Proves the override-detection line above can fail, not just always pass.

    A synthetic subclass, never registered, never imported by production code
    -- exists only so this test can show the detector actually sees an
    override when one is there.
    """
    from knowledge.connectors.base import AbstractConnector

    class _FakeConnectorThatSkipsRedaction(AbstractConnector):
        async def test_connection(self) -> bool:
            return True

        async def discover_sources(self):
            return []

        async def fetch_content(self, source_id: str):
            return None

        async def detect_changes(self, since=None):
            return []

        async def _ingest_content(self, content) -> None:  # overrides, no redact_content call
            pass

    assert _overrides_ingest_content(_FakeConnectorThatSkipsRedaction, AbstractConnector)
    assert not _overrides_ingest_content(AbstractConnector, AbstractConnector)


def test_the_audio_api_bypass_also_redacts():
    """#16985: AudioConnector.fetch_content is also called directly from
    api/knowledge.py's _ingest_audio_source, bypassing _process_change (and
    therefore the class-hierarchy sweep above) entirely -- a separate call
    site the class sweep cannot see, so it needs its own explicit check.
    """
    from api.knowledge import _ingest_audio_source

    source = inspect.getsource(_ingest_audio_source)
    assert "redact_content(" in source, (
        "_ingest_audio_source (api/knowledge.py) calls AudioConnector.fetch_content directly, "
        "bypassing AbstractConnector._ingest_content's chokepoint -- it needs its own "
        "redact_content(...) call, which is missing (#16985)."
    )


def test_negative_control_a_bypass_helper_that_skips_redaction_is_caught():
    def _fake_bypass_helper(content_result):
        return content_result.content

    source = inspect.getsource(_fake_bypass_helper)
    assert "redact_content(" not in source, "negative control itself contains a redact_content(...) call"
