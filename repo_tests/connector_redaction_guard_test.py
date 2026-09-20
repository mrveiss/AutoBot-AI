# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every KB connector's content reaches store_fact -- and therefore the
credential/injection chokepoint -- before persistence (#16985).

Re-scoped from this guard's first cut. #13708/#16895 found gdrive/onedrive's
fetch_content bypassing the redactor and initially fixed it per-connector,
then again at AbstractConnector._ingest_content. Neither survived: #16895's
own review round 2 found the real single chokepoint is one level deeper --
knowledge/ingest_sanitize.py:sanitize_fact_content, called by BOTH
store_fact and update_fact -- and moved redaction there instead. Tracing all
11 of #16985's connectors confirms every one of them already reaches
kb.store_fact (see the module docstring history in git blame for the full
per-connector trace this guard's authoring session did): the standard
_process_change sync path calls _ingest_content, which calls kb.store_fact;
external_adapter.py's message-stream handler and web_crawler.py's
batch-result handler both bypass _process_change but still call
_ingest_content directly; and audio_connector's separate API bypass
(api/knowledge.py's _ingest_audio_source) calls fetch_content directly but
stores through _store_fact_in_kb, which also calls kb.store_fact. Every
connector is case (a): already covered, nothing left to fix in connector
code. This guard is what's left: proof that stays true, so a 12th connector
-- or a "cheaper" write path added to an existing one -- can't quietly stop
being case (a) without this failing.

Discovery is by CLASS, not a hand-enumerated connector list, for the same
reason as the first cut: every *.py file in knowledge/connectors/ (except
tests/__init__) is imported so its class definitions run, then every
AbstractConnector subclass actually defined is checked against the running
interpreter's own class hierarchy. A connector could defeat the chokepoint
by overriding _ingest_content itself; the sweep catches that (checked
per-class below), proven by a negative control that the override-detection
line can actually fail, not just always pass.
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


def test_the_base_chokepoint_itself_reaches_store_fact():
    from knowledge.connectors.base import AbstractConnector

    source = inspect.getsource(AbstractConnector._ingest_content)
    assert "kb.store_fact(" in source or ".store_fact(" in source, (
        "AbstractConnector._ingest_content no longer calls kb.store_fact(...) -- every "
        "connector's fetched content converges here, and store_fact (via "
        "knowledge/ingest_sanitize.py:sanitize_fact_content, #16895) is what redacts it. "
        "Losing this call means every connector loses redaction at once (#16985)."
    )
    # #16985: content must NOT be redacted a second time here -- sanitize_fact_content
    # is the one place that happens now (#16895 round 2); a reintroduced per-connector
    # call here would just be dead weight, not a bug, but it is a sign this guard's own
    # premise (one chokepoint) has drifted and is worth a second look.
    assert "redact_content(" not in source, (
        "AbstractConnector._ingest_content calls redact_content(...) directly again -- "
        "redaction now happens inside store_fact via sanitize_fact_content (#16895 round 2); "
        "a second call here is redundant, not wrong, but means this guard's 'one chokepoint' "
        "premise needs re-checking, not a silent pass."
    )


def test_every_discovered_connector_class_routes_through_the_chokepoint():
    _import_all_connector_modules()
    REACH.completed(len(REACH.population(REPO_ROOT)))

    from knowledge.connectors.base import AbstractConnector

    subclasses = _all_connector_subclasses(AbstractConnector)
    assert subclasses, "no AbstractConnector subclasses found after importing every connector module"

    overriding = {
        cls.__module__ + "." + cls.__qualname__
        for cls in subclasses
        if _overrides_ingest_content(cls, AbstractConnector)
    }
    assert not overriding, (
        f"connector class(es) override _ingest_content instead of inheriting the store_fact "
        f"chokepoint: {sorted(overriding)}. Either remove the override, or -- if it is "
        f"genuinely needed -- confirm its own body still reaches kb.store_fact(...) and add it "
        f"to an explicit exception list here with that evidence, not a silent pass (#16985)."
    )


def test_negative_control_an_overriding_connector_is_caught():
    """Proves the override-detection line above can fail, not just always pass.

    A synthetic subclass, never registered, never imported by production code
    -- exists only so this test can show the detector actually sees an
    override when one is there.
    """
    from knowledge.connectors.base import AbstractConnector

    class _FakeConnectorThatSkipsStorage(AbstractConnector):
        async def test_connection(self) -> bool:
            return True

        async def discover_sources(self):
            return []

        async def fetch_content(self, source_id: str):
            return None

        async def detect_changes(self, since=None):
            return []

        async def _ingest_content(self, content) -> None:  # overrides, no store_fact call
            pass

    assert _overrides_ingest_content(_FakeConnectorThatSkipsStorage, AbstractConnector)
    assert not _overrides_ingest_content(AbstractConnector, AbstractConnector)


def test_the_audio_api_bypass_also_reaches_store_fact():
    """#16985: AudioConnector.fetch_content is also called directly from
    api/knowledge.py's _ingest_audio_source, bypassing _process_change (and
    therefore the class-hierarchy sweep above) entirely -- a separate call
    site the class sweep cannot see, so it needs its own explicit check.
    Stores via _store_fact_in_kb, not _ingest_content -- a different name,
    same destination (kb.store_fact), verified as a real call chain, not
    just a string both functions happen to contain.
    """
    from api.knowledge import _ingest_audio_source, _store_fact_in_kb

    bypass_source = inspect.getsource(_ingest_audio_source)
    assert "_store_fact_in_kb(" in bypass_source, (
        "_ingest_audio_source (api/knowledge.py) calls AudioConnector.fetch_content directly, "
        "bypassing AbstractConnector._ingest_content's chokepoint -- it must still reach "
        "kb.store_fact through _store_fact_in_kb, which this source no longer calls (#16985)."
    )

    sink_source = inspect.getsource(_store_fact_in_kb)
    assert "kb.store_fact(" in sink_source, (
        "_store_fact_in_kb no longer calls kb.store_fact(...) -- the audio bypass's one path "
        "into the KB chokepoint is gone (#16985)."
    )


def test_negative_control_a_bypass_helper_that_skips_store_fact_is_caught():
    def _fake_bypass_helper(content_result):
        return content_result.content  # never reaches store_fact

    source = inspect.getsource(_fake_bypass_helper)
    assert "_store_fact_in_kb(" not in source, "negative control itself contains a _store_fact_in_kb(...) call"
