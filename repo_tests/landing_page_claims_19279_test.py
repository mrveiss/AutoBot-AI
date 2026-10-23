# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The public landing page names no dependency the code lacks and renders no placeholder (#19279).

docs/index.html advertised "ChromaDB + fastembed (ONNX, no GPU needed)" with sub-100ms latency
-- no requirements file in the repo contains fastembed -- and rendered "TODO(human): price" to
the public. This checks the page against every requirements file and pyproject.toml for the libraries in
_CHECKED, and against placeholders.
"""

from __future__ import annotations

import re
import subprocess  # nosec B404  # fixed argv, no shell

from repo_tests._paths import repo_root

from autobot_shared.paths import scrubbed_git_env

_PAGE = "docs/index.html"
#: Python libraries a landing page could plausibly claim. The page may name any of them only if
#: some requirements file declares it.
_CHECKED = (
    "fastembed",
    "onnxruntime",
    "sentence-transformers",
    "ctransformers",
    "llama-cpp-python",
    "langchain",
    "llama-index",
    "chromadb",
    "fastapi",
    "uvicorn",
    "faiss-cpu",
)
_PLACEHOLDER = re.compile(r"TODO\(human\)|TODO:|FIXME|lorem ipsum", re.IGNORECASE)


def _declared() -> str:
    out = subprocess.run(  # nosec B603 B607  # fixed argv, no shell
        # Constraint files only pin versions of packages a requirements file already declares.
        ["git", "ls-files", "*requirements*.txt", "pyproject.toml"],
        cwd=repo_root(),
        capture_output=True,
        text=True,
        check=True,
        env=scrubbed_git_env(),
    ).stdout.split()
    return "\n".join((repo_root() / p).read_text(encoding="utf-8", errors="replace").lower() for p in out)


def _undeclared(page: str, declared: str) -> list[str]:
    text = page.lower()
    return [
        lib
        for lib in _CHECKED
        if re.search(rf"(?<![\w-]){re.escape(lib)}(?![\w-])", text)
        and not re.search(rf"(?m)^\s*{re.escape(lib)}\b", declared)
    ]


def test_the_page_names_no_library_that_no_requirements_file_declares():
    page = (repo_root() / _PAGE).read_text(encoding="utf-8")
    missing = _undeclared(page, _declared())
    assert not missing, f"{_PAGE} names libraries no requirements file declares: {missing} (#19279)"


def test_the_page_renders_no_placeholder():
    page = (repo_root() / _PAGE).read_text(encoding="utf-8")
    hits = [f"{n}: {line.strip()[:80]}" for n, line in enumerate(page.splitlines(), 1) if _PLACEHOLDER.search(line)]
    assert not hits, f"{_PAGE} renders placeholders (#19279):\n  " + "\n  ".join(hits)


def test_the_detector_has_contrast():
    assert _undeclared("ChromaDB + fastembed, FastAPI", "fastapi>=1\nchromadb==1\n") == ["fastembed"]
    assert _undeclared("ChromaDB and FastAPI", "fastapi>=1\nchromadb==1\n") == []
    assert _PLACEHOLDER.search("<span>TODO(human): price</span>")
