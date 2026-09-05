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
BACKEND_DEFAULTS = (
    REPO_ROOT / "autobot-slm-backend" / "ansible" / "roles" / "backend" / "defaults" / "main.yml"
)
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


def _requirement_pins(text: str) -> list[str]:
    """The actual pip-installable lines of a requirements file -- never raw text.

    #15162 review: pip itself strips everything from ``#`` onward and skips
    blank lines; a check that instead substring-matches the whole file cannot
    tell a package pin from a comment *describing* one, and this file's header
    comment explains the vLLM/torch split in prose, mentioning both by name.
    Parsing it the way pip does is the only way "vllm is absent" and "vllm is
    documented" stay distinguishable.
    """
    pins = []
    for line in text.splitlines():
        pin = line.split("#", 1)[0].strip()
        if pin:
            pins.append(pin)
    return pins


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
    pins = _requirement_pins(REQUIREMENTS_GPU_TORCH.read_text(encoding="utf-8"))
    assert any(pin.startswith("torch==") for pin in pins), pins
    assert any(pin.startswith("torchvision==") for pin in pins), pins
    assert not any(pin.lower().startswith("vllm") for pin in pins), (
        f"requirements-gpu-torch.txt has an actual vllm requirement line ({pins!r}); "
        "it must stay vLLM-free -- it installs on every GPU host, with or without the "
        "vLLM opt-in, and must not drag vllm's extra CUDA-toolkit deps"
    )


@pytest.mark.parametrize(
    ("contents", "expect_vllm_pin"),
    [
        pytest.param(
            "\n".join(
                [
                    "# vLLM needs CUDA torch; this file provides it independent of vLLM (#15162).",
                    "# See requirements-gpu.txt for the actual vllm install.",
                    "torch==2.13.0",
                    "torchvision==0.28.0  # CUDA build",
                    "",
                ]
            ),
            False,
            id="vllm-only-in-prose",
        ),
        pytest.param(
            "\n".join(["torch==2.13.0", "vllm>=0.27.1", ""]),
            True,
            id="vllm-as-a-real-requirement-line",
        ),
    ],
)
def test_requirement_pin_parse_distinguishes_prose_from_a_real_pin(
    contents: str, expect_vllm_pin: bool
) -> None:
    """#15162 review: pins the exact regression a whole-text substring check invited.

    A comment naming ``vllm`` (documenting the decoupling this file exists for)
    must never fail the vLLM-free check; an actual ``vllm`` requirement line
    always must. Both halves are asserted so neither direction can go quietly
    wrong: a parse that is too eager passes the first case for the wrong reason,
    one that is too lax passes the second for the wrong reason.
    """
    pins = _requirement_pins(contents)
    has_vllm_pin = any(pin.lower().startswith("vllm") for pin in pins)
    assert has_vllm_pin is expect_vllm_pin, (
        f"parsed pins {pins!r} from {contents!r}; expected a vllm pin={expect_vllm_pin}"
    )
    # The trailing-comment shape used throughout this repo's requirements files
    # (`torch==2.13.0  # CUDA build`) must still parse to a bare pin.
    assert not any("#" in pin for pin in pins), f"a comment leaked into a parsed pin: {pins!r}"


def test_requirements_gpu_file_no_longer_pins_torch_directly() -> None:
    """The vLLM-only file must not re-duplicate the CUDA-torch pin split into the new file."""
    assert REQUIREMENTS_GPU_VLLM.is_file(), f"{REQUIREMENTS_GPU_VLLM} missing"
    pins = _requirement_pins(REQUIREMENTS_GPU_VLLM.read_text(encoding="utf-8"))
    assert not any(pin.startswith(("torch==", "torchvision==")) for pin in pins), (
        f"requirements-gpu.txt still pins torch/torchvision directly: {pins!r}; "
        "that pin belongs solely in requirements-gpu-torch.txt (#15162) so the GPU-only "
        "install path does not depend on the vLLM file"
    )
    assert any(pin.startswith("vllm") for pin in pins)


def test_code_source_dir_is_a_role_default_not_a_repeated_inline_literal() -> None:
    """#15162 review: the new CUDA-torch task must not grow the hardcoded-value baseline.

    A GPU host's requirements path used to repeat a `code_source_dir | default(...)`
    fallback inline on every task that needed it (nine occurrences after this fix
    added a tenth); each repeats the same hardcoded `/opt/autobot` literal that
    pipeline-scripts/hardcoded_values_baseline.txt tracks per-file, per-value
    COUNT -- so a tenth occurrence is a new finding, not something the baseline
    already excuses. The fix defines the value once, as a role default, and every
    task references the bare variable.
    """
    tasks_text = ANSIBLE_TASKS.read_text(encoding="utf-8")
    assert "code_source_dir | default(" not in tasks_text, (
        "tasks/main.yml still repeats the inline default('/opt/autobot/code_source') "
        "literal; it must be defined once in defaults/main.yml and referenced bare"
    )

    assert BACKEND_DEFAULTS.is_file(), f"{BACKEND_DEFAULTS} missing"
    defaults = yaml.safe_load(BACKEND_DEFAULTS.read_text(encoding="utf-8"))
    assert isinstance(defaults, dict)
    declared = defaults.get("code_source_dir")
    assert declared, "roles/backend/defaults/main.yml must define code_source_dir"

    # #15632 moved this default off the literal: a role default beats a
    # task-level `default(...)` filter, so a hardcoded value here silently
    # shadowed every derived fallback in the role and would diverge the moment
    # `autobot.base_dir` moved. This test's point is that the value is declared
    # ONCE rather than repeated inline -- which spelling it uses is #15632's
    # call, and pinning the old literal would re-forbid the fix.
    assert "/opt/autobot" not in declared, (
        f"code_source_dir restates the install root instead of deriving it from "
        f"autobot.base_dir (#15632); got {declared!r}"
    )
    assert "autobot.base_dir" in declared, (
        f"code_source_dir must derive from the inventory SSOT (#15632); got {declared!r}"
    )
