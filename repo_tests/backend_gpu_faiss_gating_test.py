# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#15163: GPU-built faiss must install whenever a GPU is present, vLLM or not.

Same shape as `backend_gpu_torch_gating_test.py` (#15162), for the sibling
defect: `gpu_vector_search.py`'s GPU-accelerated search (#387) has been
unreachable since introduction, because every automated install path only
ever provided `faiss-cpu` — the module's own `FAISS_GPU_AVAILABLE` flag is
always `False`. This pins the fix: `requirements-gpu-faiss.txt` installs
on `backend_gpu_available` alone, and `faiss-cpu` is removed first since
`faiss-cpu`/`faiss-gpu` are two different package names that both provide the
top-level `faiss` module (unlike torch's single-package, index-url-selected
CPU/CUDA split) — installing one on top of the other risks their files
conflicting.
"""

from __future__ import annotations

from typing import Any

import pytest
from repo_tests._paths import repo_root

yaml = pytest.importorskip("yaml")

REPO_ROOT = repo_root()
ANSIBLE_TASKS = REPO_ROOT / "autobot-slm-backend" / "ansible" / "roles" / "backend" / "tasks" / "main.yml"
REQUIREMENTS_GPU_FAISS = REPO_ROOT / "requirements-gpu-faiss.txt"
REQUIREMENTS_ROOT = REPO_ROOT / "requirements.txt"


def _tasks() -> list[dict[str, Any]]:
    """Every task in the backend role, including those nested in block/rescue/always."""
    assert ANSIBLE_TASKS.is_file(), f"{ANSIBLE_TASKS} missing — this guard would pass vacuously"
    loaded = yaml.safe_load(ANSIBLE_TASKS.read_text(encoding="utf-8"))
    out: list[dict[str, Any]] = []

    def walk(items: Any) -> None:
        if not isinstance(items, list):
            return
        for item in items:
            if not isinstance(item, dict):
                continue
            out.append(item)
            for key in ("block", "rescue", "always"):
                walk(item.get(key))

    walk(loaded)
    assert out, "parsed no tasks — the guard would pass on an empty set"
    return out


def _task_named(fragment: str) -> dict[str, Any]:
    matches = [t for t in _tasks() if fragment in str(t.get("name", ""))]
    assert len(matches) == 1, (
        f"expected exactly one task named like {fragment!r}, found {len(matches)}: "
        f"{[t.get('name') for t in matches]}"
    )
    return matches[0]


def _when_text(task: dict[str, Any]) -> str:
    when = task.get("when")
    if when is None:
        return ""
    if isinstance(when, list):
        return " ".join(str(x) for x in when)
    return str(when)


def _requirement_pins(text: str) -> list[str]:
    """The actual pip-installable lines -- pip strips from ``#`` onward, so this must too."""
    pins = []
    for line in text.splitlines():
        pin = line.split("#", 1)[0].strip()
        if pin:
            pins.append(pin)
    return pins


def test_faiss_cpu_is_removed_before_the_gpu_build_installs() -> None:
    """faiss-cpu and faiss-gpu are different packages sharing the `faiss` import name."""
    task = _task_named("Remove CPU-only faiss")
    pip = task.get("ansible.builtin.pip")
    assert isinstance(pip, dict)
    assert pip.get("name") == "faiss-cpu"
    assert pip.get("state") == "absent"
    when_text = _when_text(task)
    assert "backend_gpu_available" in when_text
    assert "backend_vllm_enabled" not in when_text, (
        f"faiss-cpu removal is gated on backend_vllm_enabled ({when_text!r}); "
        "a GPU host with vLLM disabled would keep faiss-cpu installed alongside faiss-gpu"
    )


def test_gpu_faiss_install_is_gated_on_gpu_only() -> None:
    task = _task_named("Install GPU faiss requirements")
    pip = task.get("ansible.builtin.pip")
    assert isinstance(pip, dict)
    assert "requirements-gpu-faiss.txt" in str(
        pip.get("requirements", "")
    ), "the GPU-faiss install task does not point at requirements-gpu-faiss.txt"
    when_text = _when_text(task)
    assert "backend_gpu_available" in when_text
    assert "backend_vllm_enabled" not in when_text, (
        f"GPU faiss is gated on backend_vllm_enabled ({when_text!r}); "
        "a GPU host with vLLM disabled would silently keep CPU-only faiss (#15163)"
    )


def test_faiss_cpu_removal_runs_before_the_gpu_install() -> None:
    """Order matters: installing faiss-gpu before removing faiss-cpu risks the same conflict."""
    names = [str(t.get("name", "")) for t in _tasks()]
    remove_idx = next(i for i, n in enumerate(names) if "Remove CPU-only faiss" in n)
    install_idx = next(i for i, n in enumerate(names) if "Install GPU faiss requirements" in n)
    assert remove_idx < install_idx, "faiss-cpu must be removed before faiss-gpu installs, not after"


def test_deploy_reports_the_gpu_faiss_decision() -> None:
    """Silence is the actual defect (#15162's own framing, same shape here): say what was chosen."""
    task = _task_named("Report GPU/CUDA-torch deploy decision")
    debug = task.get("ansible.builtin.debug")
    assert isinstance(debug, dict)
    msg = str(debug.get("msg", ""))
    assert "faiss_gpu" in msg, f"deploy decision message is missing faiss_gpu: {msg!r}"


def test_requirements_gpu_faiss_file_carries_the_gpu_pin() -> None:
    assert REQUIREMENTS_GPU_FAISS.is_file(), f"{REQUIREMENTS_GPU_FAISS} missing"
    pins = _requirement_pins(REQUIREMENTS_GPU_FAISS.read_text(encoding="utf-8"))
    assert any(pin.startswith("faiss-gpu==") for pin in pins), pins
    assert not any(pin.startswith("faiss-cpu") for pin in pins), (
        f"requirements-gpu-faiss.txt pins faiss-cpu too ({pins!r}); "
        "installing both in the same file would race with the ansible removal step"
    )


def test_root_requirements_no_longer_points_at_conda() -> None:
    """#15163: the whole point of this fix -- conda was never a real install path."""
    text = REQUIREMENTS_ROOT.read_text(encoding="utf-8")
    assert (
        "conda" not in text.lower()
    ), "requirements.txt still mentions conda for faiss-gpu — the dead comment #15163 fixed is back"
