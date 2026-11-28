# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Point every test session at an empty, offline HuggingFace cache (#16994).

CI runners have no model cache, so a test that constructs a model-loading
class (``MultiModalProcessor`` -> ``VisionProcessor``) fails its load fast and
moves on. A developer machine that has run the product has a populated
``~/.cache/huggingface``: the same test then loads the real weights and
``verify_cached_model`` SHA-256s every multi-GB file -- about 43 s per test
(measured 2026-10-17) -- and the online/offline outcome differs from CI's.
The suite's verdict depended on the machine, not the code.

Loaded through ``pytest_plugins`` in the rootdir conftest, so it runs before
any test module can import ``huggingface_hub``, which reads these variables
into module constants at import time. Each process (xdist worker) gets its own
directory, removed at the end of the session.
"""

import os
import shutil
import tempfile
from pathlib import Path

import pytest

#: The variables huggingface_hub and transformers read for their cache roots.
CACHE_ENV_VARS = ("HF_HOME", "HF_HUB_CACHE", "TRANSFORMERS_CACHE")
#: Offline as well as empty: an empty cache with network access downloads the
#: weights on first load (16 GB in a measured run), which is worse, not hermetic.
OFFLINE_ENV_VARS = ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")

_CACHE_ROOT = tempfile.mkdtemp(prefix="autobot-test-hf-")
os.environ["HF_HOME"] = _CACHE_ROOT
os.environ["HF_HUB_CACHE"] = os.path.join(_CACHE_ROOT, "hub")
os.environ["TRANSFORMERS_CACHE"] = os.path.join(_CACHE_ROOT, "hub")
for _var in OFFLINE_ENV_VARS:
    os.environ[_var] = "1"

#: The only models a test may download, each by declaring
#: ``@pytest.mark.hf_model("<repo id>")``. Small, and fetched by CI before this
#: plugin existed; the reason names the test that needs the real weights. A model
#: not listed here fails the test that asks for it: the 16 GB case stays shut.
ALLOWED_DOWNLOADS = {
    "sentence-transformers/all-MiniLM-L6-v2": (
        "~90 MB embedding model; utils/semantic_chunking_test.py asserts real semantic "
        "splitting, which the single-chunk fallback cannot show (#14927)"
    ),
}


def cache_root() -> str:
    """The empty cache directory this session's tests see."""
    return _CACHE_ROOT


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "hf_model(repo_id): the test downloads this HuggingFace model; it must be in "
        "repo_tests.hermetic_model_cache.ALLOWED_DOWNLOADS (#16994)",
    )


def require_allowed(repo_id: str) -> None:
    """Fail the asking test unless ``repo_id`` is an allow-listed download."""
    if repo_id not in ALLOWED_DOWNLOADS:
        pytest.fail(f"{repo_id!r} is not in ALLOWED_DOWNLOADS (repo_tests/hermetic_model_cache.py)")


@pytest.fixture(autouse=True)
def _allow_declared_hf_download(request, monkeypatch):
    """Lift offline mode for a test that declares an allow-listed model."""
    marker = request.node.get_closest_marker("hf_model")
    if marker is None:
        yield
        return
    require_allowed(marker.args[0])
    for var in OFFLINE_ENV_VARS:
        monkeypatch.setenv(var, "0")
    constants = pytest.importorskip("huggingface_hub.constants")
    # huggingface_hub reads this at import; is_offline_mode() returns it at call time.
    monkeypatch.setattr(constants, "HF_HUB_OFFLINE", False)
    yield
    # Online only for this test: anything beyond the allow-list it fetched is its fault.
    extra = unexpected_models(Path(os.environ["HF_HUB_CACHE"]))
    if extra:
        pytest.fail(f"downloaded models outside ALLOWED_DOWNLOADS: {extra}")


def unexpected_models(hub: Path) -> list[str]:
    """Cached ``models--*`` entries in ``hub`` that no allow-listed repo id accounts for."""
    allowed = {"models--" + repo.replace("/", "--") for repo in ALLOWED_DOWNLOADS}
    if not hub.is_dir():
        return []
    return sorted(p.name for p in hub.iterdir() if p.name.startswith("models--") and p.name not in allowed)


def pytest_unconfigure(config):
    shutil.rmtree(_CACHE_ROOT, ignore_errors=True)
