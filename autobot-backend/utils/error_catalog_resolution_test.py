# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The deployed error catalog must be found, and a fallback must say so (#12969).

The live install carried ``error_messages.yaml`` — 9794 bytes, owned by the
service user, written thirteen minutes before the log line that said it was not
found. Both the backend and celery reported ``Error catalog YAML not found;
using built-in fallback`` on every start, and every service ran on the 42
built-ins instead of the deployed file. It went unnoticed for as long as the
install existed because the built-ins happened to agree — the moment the YAML is
edited, the edit silently does not take effect.

Two separate defects, tested separately:

* the lookup was anchored only on ``PATH.STATIC_DIR``, which is derived from
  where ``autobot_shared`` happens to sit. A layout that puts it beside the
  backend rather than above it makes that path name a directory that does not
  exist;
* the fallback reported success. ``load_catalog`` returned True whether it had
  loaded the deployed YAML or silently substituted the built-ins, so no caller
  could tell "in use" from "never found".
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from utils.error_catalog import (
    CATALOG_FILENAME,
    SOURCE_BUILTIN_FALLBACK,
    SOURCE_YAML,
    ErrorCatalog,
)


def _blind_path_constants(root: Path) -> SimpleNamespace:
    """SSOT constants that resolve to nothing, as they do on the deployed layout."""
    return SimpleNamespace(STATIC_DIR=root / "no-such-static", CONFIG_DIR=root / "no-such-config")


def test_the_module_relative_candidate_exists_in_this_checkout():
    """Presence floor. The tests below prove a fallback is reported honestly —
    which they would also do if every candidate were wrong. This asserts the
    resolver has a candidate that actually resolves."""
    candidates = ErrorCatalog()._candidate_paths()

    assert candidates, "the resolver has no candidates at all"
    existing = [path for path in candidates if path.exists()]
    assert existing, f"none of the {len(candidates)} candidate paths exist — the catalog cannot load"


def test_the_catalog_loads_when_the_ssot_paths_resolve_to_nothing(monkeypatch):
    """The reproduction: PATH points nowhere, the file is still on disk.

    This is the deployed layout in miniature. Against the previous resolver both
    candidates came from ``PATH`` alone, so this case fell straight through to
    the built-ins while the real catalog sat beside the code.
    """
    import utils.error_catalog as module

    monkeypatch.setattr(module, "PATH", _blind_path_constants(Path("/nonexistent-root")))

    catalog = ErrorCatalog()
    loaded = catalog.load_catalog()

    assert loaded is True, "the deployed catalog was not found even though it is beside this module"
    assert catalog.source == SOURCE_YAML
    assert catalog.catalog_path is not None
    assert catalog.catalog_path.name == CATALOG_FILENAME
    stats = catalog.get_catalog_stats()
    # The built-ins mirror the deployed file entry-for-entry (42 either way), so
    # a count cannot tell them apart — which is exactly why this went unnoticed.
    # The YAML carries a version and a path; the built-ins carry neither.
    assert stats["source"] == SOURCE_YAML
    assert stats["version"], "loaded the built-ins (no version), not the deployed catalog"
    assert stats["catalog_path"], "no catalog path recorded"


def test_a_fallback_reports_failure_rather_than_success(monkeypatch, tmp_path):
    """Every candidate unreachable: the catalog still answers, and says it fell back."""
    import utils.error_catalog as module

    monkeypatch.setattr(module, "PATH", _blind_path_constants(tmp_path))
    # Move the module-relative anchors out of reach too, so nothing resolves.
    monkeypatch.setattr(ErrorCatalog, "_candidate_paths", lambda self: [tmp_path / "a.yaml", tmp_path / "b.yaml"])

    catalog = ErrorCatalog()
    loaded = catalog.load_catalog()

    assert loaded is False, (
        "load_catalog reported success while running on the built-in fallback — "
        "'the deployed catalog is in use' and 'it was never found' must not be "
        "the same answer (#12969)"
    )
    assert catalog.source == SOURCE_BUILTIN_FALLBACK
    assert catalog.get_error("AUTH_0001") is not None, "the fallback must still answer"


def test_the_failure_message_names_every_path_it_searched(monkeypatch, tmp_path, caplog):
    """'Not found' without saying where is why this sat unexamined in two log sweeps."""
    import utils.error_catalog as module

    searched = [tmp_path / "first.yaml", tmp_path / "second.yaml"]
    monkeypatch.setattr(module, "PATH", _blind_path_constants(tmp_path))
    monkeypatch.setattr(ErrorCatalog, "_candidate_paths", lambda self: list(searched))

    catalog = ErrorCatalog()
    with caplog.at_level("ERROR"):
        catalog.load_catalog()

    for path in searched:
        assert str(path) in caplog.text, f"the failure message does not say it looked in {path.name}"


def test_the_reported_source_survives_the_already_loaded_shortcut(monkeypatch, tmp_path):
    """The early return must report WHICH catalog, not merely that one is loaded.

    ``load_catalog`` short-circuits when already initialised. Returning True
    there would re-introduce the whole defect for the second and every later
    caller, which is most of them.
    """
    import utils.error_catalog as module

    monkeypatch.setattr(module, "PATH", _blind_path_constants(tmp_path))
    monkeypatch.setattr(ErrorCatalog, "_candidate_paths", lambda self: [tmp_path / "gone.yaml"])

    catalog = ErrorCatalog()
    assert catalog.load_catalog() is False
    assert catalog.load_catalog() is False, "the already-loaded shortcut reported success over a fallback"


@pytest.mark.parametrize("source,expected_ok", [(SOURCE_YAML, True), (SOURCE_BUILTIN_FALLBACK, False)])
def test_the_health_probe_distinguishes_the_fallback(monkeypatch, source, expected_ok):
    """The fallback is visible on the health surface, not only in a log line."""
    api_module = pytest.importorskip("api.error_resilience")

    catalog = ErrorCatalog()
    catalog.source = source
    monkeypatch.setattr(api_module, "get_error_catalog_instance", lambda: catalog)

    deployed, data = api_module._error_catalog_state()

    assert deployed is expected_ok
    assert data["error_catalog_source"] == source


def test_the_real_loader_path_finds_the_deployed_catalog():
    """No monkeypatching at all: the loader as every service calls it (#12969).

    The tests above prove the resolver copes when ``PATH`` is blind. That is the
    reproduction, not the guarantee — a resolver whose every candidate was wrong
    could still satisfy them by reporting its fallback honestly. This drives
    ``load_catalog()`` exactly as the backend and celery do, with the real SSOT
    constants in place, and asserts it lands on the YAML rather than the 42
    built-ins that happen to agree with it.
    """
    catalog = ErrorCatalog()

    assert catalog.load_catalog() is True, (
        "the deployed catalog was not loaded through the unmodified path — this is "
        "the live symptom: 'Error catalog YAML not found' about a file that exists"
    )
    assert catalog.source == SOURCE_YAML
    assert catalog.catalog_path.name == CATALOG_FILENAME
    assert catalog.catalog_path.exists()
    assert catalog.get_catalog_stats()["version"], "loaded the built-ins, which carry no version"
