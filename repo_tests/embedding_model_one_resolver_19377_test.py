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

from repo_tests._paths import repo_root

from tools.lint._comment_syntax import code_lines
from tools.lint._scan_helpers import tracked_paths

_DIRECT = re.compile(
    r"llm\.embedding_model\b"
    r"|getattr\([^)]*\.llm,\s*[\"']embedding_model[\"']"
    # the env var the SSOT field is read from, read again past the resolver
    r"|os\.(?:environ(?:\.get)?|getenv)\s*[\[(]\s*[\"']AUTOBOT_EMBEDDING_MODEL[\"']"
)
#: A name bound to the SSOT ``llm`` section (``cfg = config.llm``, ``llm_cfg = get_config().llm``).
#: Its ``.embedding_model`` is the same bypass as ``config.llm.embedding_model``. Matching only
#: names bound this way keeps per-org configs and the memory graph's resolver-backed property out.
_LLM_ALIAS = re.compile(r"^\s*(\w+)\s*(?::[^=]+)?=\s*[\w.()]*\bllm\s*(?:#.*)?$", re.M)


def _alias_reads(text: str) -> re.Pattern[str] | None:
    aliases = sorted({m.group(1) for m in _LLM_ALIAS.finditer(text)})
    if not aliases:
        return None
    names = "|".join(map(re.escape, aliases))
    return re.compile(rf"\b(?:{names})\.embedding_model\b|getattr\(\s*(?:{names}),\s*[\"']embedding_model[\"']")


#: Each with its reason. The resolver itself; the SSOT field's own documentation map; the
#: ConfigRegistry default table, which no reader asks for this key.
_ALLOWED = {
    "autobot_shared/embedding_model.py": "the resolver",
    "autobot-backend/config/ssot_mappings.py": "documents the SSOT field, reads nothing",
    "autobot-backend/config/registry_defaults.py": "registry default table; no reader asks for this key",
}


def _python_files() -> list[str]:
    out = tracked_paths(repo_root(), "*.py")
    return [
        p for p in out if not (p.endswith("_test.py") or "/tests/" in p or p.rsplit("/", 1)[-1].startswith("test_"))
    ]


def _offenders(files: list[str]) -> list[str]:
    root = repo_root()
    hits = []
    for rel in files:
        if rel in _ALLOWED:
            continue
        text = (root / rel).read_text(encoding="utf-8", errors="replace")
        alias = _alias_reads(text)
        for n, line in code_lines(text, name=rel):
            if _DIRECT.search(line) or (alias is not None and alias.search(line)):
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


def test_the_detector_sees_an_llm_section_alias_and_not_another_config(tmp_path, monkeypatch):
    """`cfg = config.llm; cfg.embedding_model` is a bypass. A per-org config or `self.` is not."""
    (tmp_path / "planted.py").write_text(
        "cfg = config.llm\n"
        "a = cfg.embedding_model\n"
        'b = getattr(cfg, "embedding_model", "")\n'
        "org_cfg = await store.get(org_id)\n"
        "c = org_cfg.embedding_model\n"
        "d = self.embedding_model\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("repo_tests.embedding_model_one_resolver_19377_test.repo_root", lambda: tmp_path)
    hits = _offenders(["planted.py"])
    assert [h.split(":")[1] for h in hits] == ["2", "3"], hits


def test_the_detector_sees_the_env_var_read_and_not_a_longer_name(tmp_path, monkeypatch):
    """os.environ / os.getenv of AUTOBOT_EMBEDDING_MODEL is a bypass; a different variable is not."""
    (tmp_path / "planted.py").write_text(
        'a = os.environ["AUTOBOT_EMBEDDING_MODEL"]\n'
        "b = os.environ.get('AUTOBOT_EMBEDDING_MODEL', '')\n"
        'c = os.getenv("AUTOBOT_EMBEDDING_MODEL")\n'
        'd = os.getenv("AUTOBOT_EMBEDDING_MODEL_DIR")\n',
        encoding="utf-8",
    )
    monkeypatch.setattr("repo_tests.embedding_model_one_resolver_19377_test.repo_root", lambda: tmp_path)
    hits = _offenders(["planted.py"])
    assert [h.split(":")[1] for h in hits] == ["1", "2", "3"], hits
