# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""User-facing docs name only models the installer provisions, one spelling each (#15219).

The local-Ollama guide was built around `llama3:8b`, which the installer never pulls, and wrote
`mistral:7b` where the provisioned tag is `mistral:7b-instruct` -- a user following it hit
"model not found". The allowed set is read from the installer's own list
(`ollama_models` in roles/agent_config/defaults/main.yml, the same set TIERED_MODEL_ROUTING.md
documents), so a model added there is allowed here with no edit. Any other Ollama-style
`family:tag`, and the bare Phi / CodeLlama spellings, must be labelled "not provisioned" on
the line or within the three lines above it.
"""

from __future__ import annotations

import re
import subprocess  # nosec B404  # fixed argv, no shell

import yaml
from repo_tests._paths import repo_root

from autobot_shared.paths import scrubbed_git_env

_SSOT = "autobot-slm-backend/ansible/roles/agent_config/defaults/main.yml"
_FAMILIES = (
    r"(?:llama|mistral|mixtral|phi|gemma|qwen|deepseek|codellama|dolphin-llama|nomic-embed|tinyllama"
    r"|starcoder|vicuna|llava|command-r)"
)
_TAG = re.compile(r"(?<![\w/.@-])(" + _FAMILIES + r"[\w.-]*:[\w.-]+)", re.IGNORECASE)
_BARE = re.compile(r"(?<![\w/.-])(phi-?[23](?![\w:])|codellama(?!\w))", re.IGNORECASE)
_LABEL = re.compile(r"not provision", re.IGNORECASE)
_LABEL_WINDOW = 3  # a label on the line, or on one of this many lines above it (a block comment)
#: History and research record what was true then; these two developer docs hold a grep
#: pattern and a code-site table, not advice.
_SKIP = ("docs/archive/", "docs/archives/", "docs/research/", "docs/adr/", "changelog/")
_SKIP_FILES = {"docs/developer/MODEL_REVISION_PINNING.md", "docs/developer/CONFIG_MIGRATION_CHECKLIST.md"}


def _allowed() -> set[str]:
    models = yaml.safe_load((repo_root() / _SSOT).read_text(encoding="utf-8"))["ollama_models"]
    return set(models) | {m.removesuffix(":latest") for m in models}


def _docs() -> list[str]:
    out = subprocess.run(  # nosec B603 B607  # fixed argv, no shell
        ["git", "ls-files", "*.md"], cwd=repo_root(), capture_output=True, text=True, check=True, env=scrubbed_git_env()
    ).stdout.split()
    return [
        p
        for p in out
        if (p.startswith("docs/") or p in {"README.md", "INSTALL.md"})
        and not p.startswith(_SKIP)
        and p not in _SKIP_FILES
    ]


def _offenders(texts: dict[str, str], allowed: set[str]) -> list[str]:
    found = []
    for path, text in texts.items():
        lines = text.splitlines()
        for i, line in enumerate(lines):
            bad = [t for t in _TAG.findall(line) if t.rstrip(".,)`'\"") not in allowed] + _BARE.findall(line)
            labelled = any(_LABEL.search(x) for x in lines[max(0, i - _LABEL_WINDOW) : i + 1])
            if bad and not labelled:
                found.append(f"{path}:{i + 1}: {bad}")
    return found


def test_the_allowed_set_comes_from_the_installer():
    allowed = _allowed()
    assert {"qwen3.5:9b", "mistral:7b-instruct", "phi3:mini", "nomic-embed-text"} <= allowed


def test_docs_name_only_provisioned_model_tags():
    files = _docs()
    assert len(files) > 100, f"enumerated only {len(files)} docs"
    root = repo_root()
    offenders = _offenders({p: (root / p).read_text(encoding="utf-8", errors="replace") for p in files}, _allowed())
    assert not offenders, (
        "use a provisioned tag (the installer's ollama_models, documented in TIERED_MODEL_ROUTING.md), "
        "or label the model 'not provisioned' on the line or just above it (#15219):\n  " + "\n  ".join(offenders)
    )


def test_the_detector_flags_unprovisioned_tags_and_respects_labels():
    allowed = {"qwen3.5:9b", "mistral:7b-instruct", "phi3:mini", "dolphin-llama3:8b"}
    texts = {
        # The old denylist, kept as the contrast fixture: each of these must still be caught...
        "wrong.md": "pull llama3:8b\nuse mistral:7b now\nphi-3 is fast\ntry deepseek-r1:latest\nor llama3:70b\n",
        # ...and nothing here may be: provisioned tags, a same-line label, a label two lines up.
        "fine.md": "qwen3.5:9b and dolphin-llama3:8b\nmistral:7b-instruct, phi3:mini\n"
        "llama3:70b, not provisioned\n# not provisioned: the block below\n\nmodel = 'deepseek-r1:latest'\n",
    }
    hits = _offenders(texts, allowed)
    assert [h.split(":", 2)[1] for h in hits if h.startswith("wrong.md")] == ["1", "2", "3", "4", "5"]
    assert not [h for h in hits if h.startswith("fine.md")], hits
