# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The five filtered-install deploy commands, pinned as an identity (#17166).

A separate module from test_role_registry.py, which is grandfathered at 846
lines and may not grow (#14236). It reuses that module's bootstrap by importing
from it -- the bootstrap is 100 lines of sys.modules surgery to get the real
role_registry past conftest's MagicMock stubs, and a second copy of it here
would be precisely the duplication this issue is about.
"""

from pathlib import Path as _Path

import pytest

from .test_role_registry import _role, _rr

# ---------------------------------------------------------------------------
# post_sync_cmd built by one helper (#17166)
# ---------------------------------------------------------------------------
#
# Five roles hand-wrote the same build-filtered-requirements.sh invocation.
# These are deploy commands: nothing executes them until a real deploy, so a
# wrong character survives every test the suite has. The strings below are the
# ones that were in the file before the helper existed, recorded verbatim, so
# the refactor is pinned as an identity rather than described as one.

_EXPECTED_POST_SYNC = {
    "slm-backend": (
        "cd {b}/autobot-slm-backend && "
        "bash {b}/code_source/scripts/build-filtered-requirements.sh "
        "requirements.txt {b}/code_source > /tmp/requirements-filtered-slm-backend.txt && "
        "venv/bin/pip install -r /tmp/requirements-filtered-slm-backend.txt && venv/bin/alembic upgrade head"
    ),
    "backend": (
        "cd {b}/autobot-backend && "
        "bash {b}/code_source/scripts/build-filtered-requirements.sh "
        "requirements.txt {b}/code_source > /tmp/requirements-filtered-slm.txt && "
        "PIP_USE_DEPRECATED=legacy-resolver PIP_DEFAULT_TIMEOUT=120 "
        "venv/bin/pip install -r /tmp/requirements-filtered-slm.txt && venv/bin/alembic upgrade head"
    ),
    "ai-stack": (
        "cd {b}/autobot-ai-stack && "
        "bash {b}/code_source/scripts/build-filtered-requirements.sh "
        "requirements-ai.txt {b}/code_source > /tmp/requirements-filtered-ai-stack.txt && "
        "venv/bin/pip install -r /tmp/requirements-filtered-ai-stack.txt"
    ),
    "npu-worker": (
        "cd {b}/autobot-npu-worker && "
        "bash {b}/code_source/scripts/build-filtered-requirements.sh "
        "requirements.txt {b}/code_source > /tmp/requirements-filtered-npu-worker.txt && "
        "venv/bin/pip install -r /tmp/requirements-filtered-npu-worker.txt"
    ),
    "tts-worker": (
        "cd {b}/autobot-tts-worker && "
        "bash {b}/code_source/scripts/build-filtered-requirements.sh "
        "requirements.txt {b}/code_source > /tmp/requirements-filtered-tts-worker.txt && "
        "venv/bin/pip install -r /tmp/requirements-filtered-tts-worker.txt"
    ),
}


@pytest.mark.parametrize("name", sorted(_EXPECTED_POST_SYNC))
def test_filtered_install_command_is_unchanged_by_the_helper(name: str) -> None:
    base = _rr._BASE_DIR
    assert _role(name)["post_sync_cmd"] == _EXPECTED_POST_SYNC[name].format(b=base)


def test_the_backend_role_keeps_its_differently_named_temp_file() -> None:
    """Reads like a typo, is not one.

    The backend role writes /tmp/requirements-filtered-slm.txt while slm-backend
    writes ...-slm-backend.txt. Deriving the tag from the working directory --
    the obvious simplification -- would silently change two live deploy
    commands, so the helper takes it as an argument and this pins why.
    """
    assert "/tmp/requirements-filtered-slm.txt" in _role("backend")["post_sync_cmd"]
    assert "/tmp/requirements-filtered-slm-backend.txt" in _role("slm-backend")["post_sync_cmd"]


def test_no_role_still_hand_writes_the_filter_invocation() -> None:
    """The point of the change: one definition, not five.

    Counts call sites in the source rather than trusting that the five known
    ones were all of them -- a sixth added later by copy-paste is exactly the
    regression this closes.
    """
    src = _Path(_rr.__file__).read_text(encoding="utf-8")
    # An invocation always carries `bash`; prose that merely names the script
    # -- comments, and the helper's own docstring -- does not.
    invocations = [
        line
        for line in src.splitlines()
        if "build-filtered-requirements.sh" in line and "bash " in line and not line.lstrip().startswith("#")
    ]
    assert len(invocations) == 1, (
        f"build-filtered-requirements.sh is invoked on {len(invocations)} lines; "
        "it should be invoked only inside _filtered_pip_install"
    )
