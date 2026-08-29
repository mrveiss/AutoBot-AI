# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#15162: CUDA torch must not be gated behind the vLLM opt-in.

"Does this host have an NVIDIA GPU" and "does this host run in-process vLLM"
are different questions. Before this fix, `backend_gpu_available` was only
ever resolved `when: backend_vllm_enabled | bool` — so a GPU host that left
vLLM disabled (the default, `backend_vllm_enabled: false`) was never even
probed, and the CUDA-torch install below it was unreachable. The venv kept
the CPU-only torch from `autobot-backend/requirements.txt`, and nothing
reported the downgrade.

These assertions parse the actual ansible task list (walking block/rescue/
always, per the established pattern in `llc_agent_cli_provisioned_test.py`)
and inspect the real `when` conditions and requirement file contents — never
raw substring matches against the whole file, which would go green on a
comment.

Regression this guards against: re-adding `backend_vllm_enabled | bool` to
the GPU-probe, GPU-availability-fact, or CUDA-torch-install `when` clauses
re-couples GPU detection to the vLLM opt-in and silently drops back to CPU
torch on every non-vLLM GPU host.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

yaml = pytest.importorskip("yaml")

REPO_ROOT = Path(__file__).resolve().parents[1]
ANSIBLE_TASKS = (
    REPO_ROOT / "autobot-slm-backend" / "ansible" / "roles" / "backend" / "tasks" / "main.yml"
)
REQUIREMENTS_GPU_TORCH = REPO_ROOT / "requirements-gpu-torch.txt"
REQUIREMENTS_GPU_VLLM = REPO_ROOT / "requirements-gpu.txt"


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
    """Normalise ``when:`` (string, list, or absent) to one searchable string."""
    when = task.get("when")
    if when is None:
        return ""
    if isinstance(when, list):
        return " ".join(str(x) for x in when)
    return str(when)


def test_gpu_probe_is_not_gated_on_vllm() -> None:
    """The nvidia-smi probe must run whenever backend_has_gpu == "auto", vLLM or not."""
    task = _task_named("Detect NVIDIA GPU")
    when_text = _when_text(task)
    assert "backend_vllm_enabled" not in when_text, (
        f"the GPU-probe task is still gated on backend_vllm_enabled ({when_text!r}); "
        "a GPU host with vLLM disabled would never be probed for a GPU at all"
    )
    assert "backend_has_gpu" in when_text


def test_gpu_availability_fact_is_not_gated_on_vllm() -> None:
    """backend_gpu_available must be resolved independent of the vLLM opt-in."""
    task = _task_named("Resolve GPU availability")
    when_text = _when_text(task)
    assert "backend_vllm_enabled" not in when_text, (
        f"backend_gpu_available is still resolved only when: {when_text!r}; "
        "a GPU host with vLLM disabled would never get backend_gpu_available=true, "
        "which starves every consumer of that fact — not just the torch install"
    )


def test_cuda_torch_install_is_gated_on_gpu_only() -> None:
    """CUDA torch/torchvision install on GPU presence alone — this is the actual fix."""
    task = _task_named("Install CUDA torch requirements")
    pip = task.get("ansible.builtin.pip")
    assert isinstance(pip, dict)
    assert "requirements-gpu-torch.txt" in str(pip.get("requirements", "")), (
        "the CUDA-torch install task does not point at requirements-gpu-torch.txt"
    )
    when_text = _when_text(task)
    assert "backend_gpu_available" in when_text
    assert "backend_vllm_enabled" not in when_text, (
        f"CUDA torch is still gated on backend_vllm_enabled ({when_text!r}); "
        "a GPU host with vLLM disabled would silently keep CPU-only torch (#15162)"
    )


def test_vllm_install_still_requires_both_flags() -> None:
    """vllm stays genuinely opt-in: it needs the GPU present AND vLLM enabled."""
    task = _task_named("Install GPU/vLLM requirements")
    pip = task.get("ansible.builtin.pip")
    assert isinstance(pip, dict)
    assert "requirements-gpu.txt" in str(pip.get("requirements", ""))
    when_text = _when_text(task)
    assert "backend_vllm_enabled" in when_text, (
        "vllm install lost its vLLM-opt-in gate — it would now install on every GPU host"
    )
    assert "backend_gpu_available" in when_text, (
        "vllm install lost its GPU gate — it would attempt to install on CPU-only hosts"
    )


def test_deploy_reports_the_gpu_torch_decision() -> None:
    """Silence is the actual defect (#15162): the deploy must say what it chose and why."""
    task = _task_named("Report GPU/CUDA-torch deploy decision")
    debug = task.get("ansible.builtin.debug")
    assert isinstance(debug, dict)
    msg = str(debug.get("msg", ""))
    for token in ("gpu_available", "cuda_torch", "vllm_enabled", "vllm"):
        assert token in msg, f"deploy decision message is missing {token!r}: {msg!r}"


def test_requirements_gpu_torch_file_carries_cuda_torch() -> None:
    assert REQUIREMENTS_GPU_TORCH.is_file(), f"{REQUIREMENTS_GPU_TORCH} missing"
    text = REQUIREMENTS_GPU_TORCH.read_text(encoding="utf-8")
    assert "torch==" in text
    assert "torchvision==" in text
    assert "vllm" not in text.lower(), (
        "requirements-gpu-torch.txt must stay vLLM-free — it installs on every GPU host, "
        "with or without the vLLM opt-in, and must not drag vllm's extra CUDA-toolkit deps"
    )


def test_requirements_gpu_file_no_longer_pins_torch_directly() -> None:
    """The vLLM-only file must not re-duplicate the CUDA-torch pin split into the new file."""
    assert REQUIREMENTS_GPU_VLLM.is_file(), f"{REQUIREMENTS_GPU_VLLM} missing"
    lines = [
        line.split("#", 1)[0].strip()
        for line in REQUIREMENTS_GPU_VLLM.read_text(encoding="utf-8").splitlines()
    ]
    pins = [line for line in lines if line]
    assert not any(pin.startswith(("torch==", "torchvision==")) for pin in pins), (
        f"requirements-gpu.txt still pins torch/torchvision directly: {pins!r}; "
        "that pin belongs solely in requirements-gpu-torch.txt (#15162) so the GPU-only "
        "install path does not depend on the vLLM file"
    )
    assert any(pin.startswith("vllm") for pin in pins)
