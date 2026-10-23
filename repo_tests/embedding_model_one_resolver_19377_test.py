# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No production code reads the embedding model past the one resolver (#19377).

`autobot_shared.embedding_model.active_embedding_model()` carries the user's runtime override
over the SSOT default. A reader of `config.llm.embedding_model` directly would ignore a switch
and embed with the old model against the new index.
"""

from __future__ import annotations

import re
import subprocess  # nosec B404  # fixed argv, no shell

from repo_tests._paths import repo_root

from autobot_shared.paths import scrubbed_git_env

_DIRECT = re.compile(r"llm\.embedding_model\b|getattr\([^)]*\.llm,\s*[\"']embedding_model[\"']")
#: Each with its reason. The resolver itself; the SSOT field's own documentation map; the
#: ConfigRegistry default table, which no reader asks for this key.
_ALLOWED = {
    "autobot_shared/embedding_model.py": "the resolver",
    "autobot-backend/config/ssot_mappings.py": "documents the SSOT field, reads nothing",
    "autobot-backend/config/registry_defaults.py": "registry default table; no reader asks for this key",
}


def _python_files() -> list[str]:
    out = subprocess.run(  # nosec B603 B607  # fixed argv, no shell
        ["git", "ls-files", "*.py"], cwd=repo_root(), capture_output=True, text=True, check=True, env=scrubbed_git_env()
    ).stdout.split()
    return [
        p for p in out if not (p.endswith("_test.py") or "/tests/" in p or p.rsplit("/", 1)[-1].startswith("test_"))
    ]


def _offenders(files: list[str]) -> list[str]:
    root = repo_root()
    hits = []
    for rel in files:
        if rel in _ALLOWED:
            continue
        for n, line in enumerate((root / rel).read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if _DIRECT.search(line) and not line.lstrip().startswith("#"):
                hits.append(f"{rel}:{n}: {line.strip()}")
    return hits


def test_no_production_reader_bypasses_the_resolver():
    files = _python_files()
    assert len(files) > 1000, f"enumerated only {len(files)} files -- the sweep did not run"
    offenders = _offenders(files)
    assert not offenders, "read active_embedding_model() instead (#19377):\n  " + "\n  ".join(offenders)


def test_the_detector_sees_both_spellings(tmp_path, monkeypatch):
    planted = tmp_path / "planted.py"
    planted.write_text(
        'a = config.llm.embedding_model\nb = getattr(ssot.llm, "embedding_model", "")\n', encoding="utf-8"
    )
    monkeypatch.setattr("repo_tests.embedding_model_one_resolver_19377_test.repo_root", lambda: tmp_path)
    assert len(_offenders(["planted.py"])) == 2
