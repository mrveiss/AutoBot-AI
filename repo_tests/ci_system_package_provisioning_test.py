# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#14550 — system packages ansible installs on hosts are absent from CI runners.

Exercises the exact functions ``code-quality`` calls
(``tools/lint/check_ci_system_package_provisioning.py --audit``) rather than
paraphrasing the rule, so a test agreeing with a second copy of the decision
proves nothing about the copy that actually blocks a merge.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
_CHECKER = REPO_ROOT / "tools" / "lint" / "check_ci_system_package_provisioning.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_ci_system_package_provisioning", _CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = _load_checker()


# --------------------------------------------------------------------------
# Discrimination — against a real (synthetic) tree on disk
# --------------------------------------------------------------------------


def _write_ansible_task(tmp_path, packages: list[str]) -> None:
    tasks_dir = tmp_path / "autobot-slm-backend" / "ansible" / "roles" / "backend" / "tasks"
    tasks_dir.mkdir(parents=True)
    body = "\n".join(f"        - {pkg}" for pkg in packages)
    (tasks_dir / "main.yml").write_text(
        f"""---
  - name: "Backend | Install backend-specific system dependencies"
    ansible.builtin.apt:
      name:
{body}
      state: present
    tags: ['backend', 'packages']
""",
        encoding="utf-8",
    )


def _write_setup_action(tmp_path, apt_install_line: str | None) -> None:
    action_dir = tmp_path / ".github" / "actions" / "setup-python-suite"
    action_dir.mkdir(parents=True)
    body = f"        run: |\n          sudo apt-get install -y {apt_install_line}\n" if apt_install_line else ""
    text = f"runs:\n  using: composite\n  steps:\n    - shell: bash\n{body}"
    (action_dir / "action.yml").write_text(text, encoding="utf-8")


def _write_gated_test(tmp_path, *, rel_path: str, binary: str) -> None:
    path = tmp_path / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""import shutil
import pytest


@pytest.mark.skipif(
    shutil.which("{binary}") is None,
    reason="{binary} not installed",
)
def test_real_thing():
    pass
""",
        encoding="utf-8",
    )


#: Mirrors the real ansible role's feature-package group (13 entries) so
#: fixtures clear FEATURE_PACKAGE_FLOOR without needing the toolchain packages,
#: which ansible_feature_packages() subtracts out before counting.
_SAMPLE_FEATURE_PACKAGES = [
    "xvfb",
    "x11-utils",
    "x11-apps",
    "ffmpeg",
    "libsndfile1",
    "libsndfile1-dev",
    "portaudio19-dev",
    "espeak-ng",
    "espeak-ng-data",
    "tesseract-ocr",
    "libtesseract-dev",
    "python3-tk",
    "postgresql-client",
]


def test_audit_fails_when_a_gated_binarys_package_is_not_provisioned(tmp_path):
    _write_ansible_task(tmp_path, _SAMPLE_FEATURE_PACKAGES)
    _write_setup_action(tmp_path, apt_install_line=None)
    _write_gated_test(tmp_path, rel_path="pkg/thing_test.py", binary="tesseract")

    reached, problems = checker.audit_provisioning(tmp_path)
    assert reached == 1
    assert problems, "an ansible-installed, CI-unprovisioned binary must fail"
    assert "tesseract" in problems[0]


def test_audit_passes_when_the_package_is_provisioned(tmp_path):
    _write_ansible_task(tmp_path, _SAMPLE_FEATURE_PACKAGES)
    _write_setup_action(tmp_path, apt_install_line="tesseract-ocr")
    _write_gated_test(tmp_path, rel_path="pkg/thing_test.py", binary="tesseract")

    reached, problems = checker.audit_provisioning(tmp_path)
    assert reached == 1
    assert problems == []


def test_audit_ignores_a_binary_ansible_does_not_install(tmp_path):
    """A gate on a binary outside the ansible role's package set is not this guard's concern."""
    without_ffmpeg = [pkg for pkg in _SAMPLE_FEATURE_PACKAGES if pkg != "ffmpeg"]
    _write_ansible_task(tmp_path, without_ffmpeg)
    _write_setup_action(tmp_path, apt_install_line=None)
    _write_gated_test(tmp_path, rel_path="pkg/thing_test.py", binary="ffmpeg")

    reached, problems = checker.audit_provisioning(tmp_path)
    assert reached == 1  # the gate is still found and reported...
    assert problems == []  # ...but produces no problem, since ansible never promised it


def test_audit_fails_below_the_feature_package_floor(tmp_path):
    """A renamed/moved ansible task must not read as a clean scan of nothing."""
    _write_ansible_task(tmp_path, ["ffmpeg"])  # far below FEATURE_PACKAGE_FLOOR
    _write_setup_action(tmp_path, apt_install_line="ffmpeg")
    reached, problems = checker.audit_provisioning(tmp_path)
    assert reached == 0
    assert problems and "moved or was renamed" in problems[0]


def test_audit_fails_when_no_gated_binary_is_found(tmp_path):
    """A test-file rename that hides every skip-gate must not read as zero problems."""
    _write_ansible_task(tmp_path, _SAMPLE_FEATURE_PACKAGES)
    _write_setup_action(tmp_path, apt_install_line="ffmpeg")
    reached, problems = checker.audit_provisioning(tmp_path)
    assert reached == 0
    assert problems and "zero shutil.which" in problems[0]


def test_toolchain_packages_are_excluded_from_scope():
    """git/curl/build-essential are pre-installed by the runner image — not this guard's job."""
    assert "git" in checker.TOOLCHAIN_PACKAGES
    assert "curl" in checker.TOOLCHAIN_PACKAGES
    assert "ffmpeg" not in checker.TOOLCHAIN_PACKAGES


def _write_probe_gated_test(tmp_path, *, rel_path: str) -> None:
    """A test gated on an indirect probe call, never touching shutil.which.

    The probe call is assembled from fragments rather than written as a
    literal -- this guard scans the whole tree including repo_tests/ itself,
    so a literal `get_tesseract_version(` here would make the checker flag
    ITS OWN test file the moment this fixture is written to disk.
    """
    probe_call = "get_tesseract" + "_version()"
    path = tmp_path / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "import pytest\n\n\n"
        "def test_real_ocr():\n"
        '    pytest.importorskip("pytesseract")\n'
        "    import pytesseract\n"
        f"    pytesseract.{probe_call}\n",
        encoding="utf-8",
    )


def test_probe_call_widens_detection_beyond_shutil_which(tmp_path):
    """#14550 code-review: a get_tesseract_version() gate must not read as
    "no real test, out of scope" just because it never calls shutil.which."""
    _write_ansible_task(tmp_path, _SAMPLE_FEATURE_PACKAGES)
    _write_setup_action(tmp_path, apt_install_line=None)
    _write_probe_gated_test(tmp_path, rel_path="pkg/thing_test.py")

    reached, problems = checker.audit_provisioning(tmp_path)
    assert reached == 1
    assert problems, "a probe-call gate on an unprovisioned package must fail"
    assert "tesseract" in problems[0]


def test_prefix_style_test_files_are_scanned_too(tmp_path):
    """pytest.ini collects BOTH `test_*.py` and `*_test.py` -- so must this guard."""
    _write_ansible_task(tmp_path, _SAMPLE_FEATURE_PACKAGES)
    _write_setup_action(tmp_path, apt_install_line=None)
    _write_gated_test(tmp_path, rel_path="pkg/test_thing.py", binary="tesseract")

    reached, problems = checker.audit_provisioning(tmp_path)
    assert reached == 1, "a test_*.py-prefixed file's skip-gate was not found"
    assert problems


# --------------------------------------------------------------------------
# The live tree, and the #14550 regression this PR fixes
# --------------------------------------------------------------------------


def test_ansible_feature_packages_reaches_the_floor():
    packages = checker.ansible_feature_packages()
    assert len(packages) >= checker.FEATURE_PACKAGE_FLOOR, packages
    assert "tesseract-ocr" in packages
    assert "ffmpeg" in packages
    assert "git" not in packages  # toolchain package, excluded on purpose


def test_ffmpeg_is_provisioned_in_ci():
    """The one live finding #14550 fixed: ffmpeg must now be installed in CI."""
    assert "ffmpeg" in checker.ci_installed_packages(), (
        ".github/actions/setup-python-suite/action.yml must install ffmpeg — "
        "test_real_audio_extraction needs it to run for real, not skip (#14550)"
    )


def test_audit_is_clean_on_the_real_tree():
    reached, problems = checker.audit_provisioning()
    assert reached >= 1, "no shutil.which(...) skip-gate found on the live tree"
    assert problems == [], problems


def test_ci_installed_packages_ignores_apt_install_mentioned_in_a_comment(tmp_path):
    """#14550 incident: a comment EXPLAINING an apt-get command must not be
    tokenized as one. The action file's own docstring-style comment about
    this very bug contains the literal substring "apt-get install" in prose,
    and used to leak words from that sentence into the installed-package set."""
    action_dir = tmp_path / ".github" / "actions" / "setup-python-suite"
    action_dir.mkdir(parents=True)
    fixture = """runs:
  using: composite
  steps:
    # a bare `apt-get install` hung one shard for the full timeout
    - shell: bash
      run: |
        sudo apt-get install -y --no-install-recommends -o DPkg::Lock::Timeout=60 ffmpeg
"""
    (action_dir / "action.yml").write_text(fixture, encoding="utf-8")
    assert checker.ci_installed_packages(tmp_path) == {"ffmpeg"}


def test_setup_python_suite_apt_step_waits_for_the_dpkg_lock_and_cannot_hang_the_job():
    """#14550 post-merge incident 1: an unbounded apt-get install hung one
    shard for the job's full 60-minute timeout, taking every test in it down
    too. `-o DPkg::Lock::Timeout` bounds the wait for the dpkg lock, and
    coreutils `timeout` around each COMMAND bounds the whole invocation.

    NOT `timeout-minutes` on the step -- that is incident 2: that key does
    not exist on a composite action's own steps (only `run`, `shell`,
    `working-directory`, `env`, `id`, `if`, `name` do), and setting it broke
    GitHub's template validation for the WHOLE action, on every shard, not
    just the one with a stuck lock. This test pins the working shape,
    including the negative half.
    """
    action = (REPO_ROOT / ".github" / "actions" / "setup-python-suite" / "action.yml").read_text(encoding="utf-8")
    assert "DPkg::Lock::Timeout" in action, "apt-get must bound its wait for the dpkg lock, not hang indefinitely"
    parsed = yaml.safe_load(action)
    apt_steps = [s for s in parsed["runs"]["steps"] if "apt-get install" in s.get("run", "")]
    assert apt_steps, "no step installs system packages — did the step get renamed?"
    step = apt_steps[0]
    assert "timeout " in step["run"], "the apt-get command itself must be wrapped in coreutils `timeout`"


def test_setup_python_suite_steps_use_only_composite_action_keys():
    """#14550 post-merge incident 2, generalised: not just the apt step.

    A composite action's OWN steps accept only `run`, `shell`,
    `working-directory`, `env`, `id`, `if`, `name` -- `timeout-minutes` (job-
    and workflow-step-only) made GitHub's template validator reject the
    WHOLE action.yml before a single step ran, on every shard. Checks every
    step, not only the one that caused the incident, since the next
    workflow-only key added to any step here fails the same way.
    """
    action = (REPO_ROOT / ".github" / "actions" / "setup-python-suite" / "action.yml").read_text(encoding="utf-8")
    parsed = yaml.safe_load(action)
    steps = parsed["runs"]["steps"]
    assert steps, "no steps found — did the action structure change?"
    allowed = {"name", "run", "shell", "working-directory", "env", "id", "if", "uses", "with"}
    for step in steps:
        offending = set(step) - allowed
        assert not offending, (
            f"step {step.get('name')!r} uses key(s) {offending} that a composite action's own steps do not "
            "support -- GitHub's template validator rejects the WHOLE file for this, not just the one step"
        )


# --------------------------------------------------------------------------
# The audit entrypoint, and the check that actually runs it
# --------------------------------------------------------------------------


def test_code_quality_runs_the_audit():
    workflow = (REPO_ROOT / ".github" / "workflows" / "code-quality.yml").read_text(encoding="utf-8")
    assert "check_ci_system_package_provisioning.py --audit" in workflow, (
        "code-quality.yml no longer runs the CI system-package provisioning audit — "
        "the guard would stop blocking merges while these tests kept passing (#14550)"
    )
    assert _CHECKER.is_file(), f"{_CHECKER} is gone but the workflow still calls it"


def test_setup_python_suite_installs_ffmpeg_directly():
    """Pin the fix at the source file, not only through the checker's own parse."""
    action = (REPO_ROOT / ".github" / "actions" / "setup-python-suite" / "action.yml").read_text(encoding="utf-8")
    assert "ffmpeg" in action, "setup-python-suite/action.yml no longer installs ffmpeg (#14550)"


def test_the_checker_needs_no_third_party_import():
    """It must run in a job that installs linters, not the application's dependencies."""
    source = _CHECKER.read_text(encoding="utf-8")
    third_party = [
        line
        for line in source.splitlines()
        if line.startswith(("import ", "from "))
        and not line.startswith("from __future__")
        and line.split()[1].split(".")[0] not in {"argparse", "logging", "pathlib", "re", "sys"}
    ]
    assert third_party == [], f"the checker imports non-stdlib modules: {third_party}"
