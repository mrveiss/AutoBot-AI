# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""install.sh tells the user what it needs and what it installs (#18583, #18586).

An external clean-install test stopped at the systemd pre-flight on a container
host and was told only how to fix WSL2 (#18583). A user running `./install.sh`
from a clone at a chosen commit got the remote `main` with no word said (#18586).

These run the real functions under `set -euo pipefail`. Message text is an
output of the function, so asserting on it is asserting on behaviour: each test
fails if the branch it names stops producing its sentence.

**What they do not cover.** They do not run the pre-flight on a real container
or WSL host, and they do not clone anything — `code_deployment` is checked only
for calling the reporter and logging the installed commit.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from repo_tests._paths import repo_root

from autobot_shared.paths import scrubbed_git_env

_INSTALL = repo_root() / "install.sh"
_BASH = shutil.which("bash") or "bash"


def _text() -> str:
    return _INSTALL.read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    """The named shell function, verbatim, from install.sh."""
    match = re.search(rf"^{re.escape(name)}\(\) \{{.*?^\}}", _text(), re.S | re.M)
    assert match, f"{name}() not found in install.sh — this file would test nothing"
    return match.group(0)


def _bash(script: str, *, cwd: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([_BASH, "-c", script], capture_output=True, text=True, timeout=60, cwd=cwd)


def _hint(proc_version: str) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        version = Path(tmp) / "version"
        version.write_text(proc_version, encoding="utf-8")
        script = f"""
set -euo pipefail
PROC_VERSION_FILE={version}
{_function_source("systemd_missing_hint")}
systemd_missing_hint
"""
        result = _bash(script)
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_the_systemd_hint_names_the_requirement_everywhere() -> None:
    for kernel in ("Linux version 6.12.0-amd64 (debian)", "Linux version 6.6.87.2-microsoft-standard-WSL2"):
        assert "systemd must be running as PID 1" in _hint(kernel), kernel


def test_a_non_wsl_host_is_pointed_at_the_docker_path_not_wsl() -> None:
    """The defect: a container host was told to edit /etc/wsl.conf."""
    hint = _hint("Linux version 6.12.0-amd64 (debian)")
    assert "Docker path in INSTALL.md" in hint
    assert "wsl.conf" not in hint


def test_wsl_still_gets_its_fix() -> None:
    hint = _hint("Linux version 6.6.87.2-microsoft-standard-WSL2")
    assert "[boot] systemd=true" in hint


def test_preflight_uses_the_hint() -> None:
    body = _function_source("preflight_checks")
    assert 'fatal "$(systemd_missing_hint)"' in body


def _report(script_dir: str, code_source: str = "/opt/autobot/code_source") -> subprocess.CompletedProcess:
    script = f"""
set -euo pipefail
warn() {{ echo "[WARN] $*"; }}
SCRIPT_DIR={script_dir!r}
CODE_SOURCE={code_source!r}
DEFAULT_REPO=https://example.invalid/repo.git
GIT_BRANCH=main
{_function_source("report_local_checkout")}
report_local_checkout
echo RETURNED
"""
    return _bash(script)


def _git_repo(path: Path) -> str:
    def git(*args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(path), *args], check=True, capture_output=True, text=True, env=scrubbed_git_env()
        ).stdout.strip()

    git("init", "-q")
    (path / "f").write_text("x", encoding="utf-8")
    git("add", "f")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "c")
    return git("rev-parse", "--short", "HEAD")


def test_a_run_from_a_checkout_says_the_checkout_is_not_installed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        sha = _git_repo(Path(tmp))
        result = _report(tmp)
    assert result.returncode == 0, result.stderr
    assert f"@ {sha}" in result.stdout and "not that checkout" in result.stdout, result.stdout
    assert "RETURNED" in result.stdout


def test_curl_pipe_and_non_git_dirs_stay_silent() -> None:
    """`curl | bash` has no SCRIPT_DIR; a plain directory is not a checkout."""
    with tempfile.TemporaryDirectory() as tmp:
        for script_dir in ("", tmp):
            result = _report(script_dir)
            assert result.returncode == 0, result.stderr
            assert result.stdout.strip() == "RETURNED", (script_dir, result.stdout)


def test_a_reinstall_from_the_installed_source_stays_silent() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _git_repo(Path(tmp))
        result = _report(tmp, code_source=tmp)
    assert result.stdout.strip() == "RETURNED", result.stdout


def _script_dir_block() -> str:
    match = re.search(r"^SCRIPT_DIR=\"\"\n.*?^readonly SCRIPT_DIR$", _text(), re.S | re.M)
    assert match, "the SCRIPT_DIR block was not found in install.sh"
    return match.group(0)


def test_script_dir_is_the_file_location_and_empty_when_piped() -> None:
    block = _script_dir_block() + '\necho "DIR=${SCRIPT_DIR}"\n'
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "install.sh"
        script.write_text("set -euo pipefail\n" + block, encoding="utf-8")
        as_file = subprocess.run([_BASH, str(script)], capture_output=True, text=True, timeout=30)
        piped = subprocess.run(
            [_BASH], input=script.read_text(encoding="utf-8"), capture_output=True, text=True, timeout=30
        )
        resolved = str(Path(tmp).resolve())
    assert f"DIR={resolved}" in as_file.stdout, as_file.stdout + as_file.stderr
    assert piped.stdout.strip() == "DIR=", piped.stdout + piped.stderr


def test_code_deployment_reports_before_cloning_and_logs_the_commit() -> None:
    body = _function_source("code_deployment")
    assert body.index("report_local_checkout") < body.index("git clone"), "the notice must precede the clone"
    assert 'git -C "${CODE_SOURCE}" rev-parse HEAD' in body


# --- INSTALL.md stays in step with install.sh (#18582) ---

_DOC = repo_root() / "INSTALL.md"


def _parse_args_options() -> list[str]:
    arms = re.findall(r"^\s+(-[^)\s]+)\)", _function_source("parse_args"), re.M)
    options = [opt.split("=")[0] for arm in arms for opt in arm.split("|")]
    assert len(options) >= 10, f"parse_args arms not read — this guard would check nothing: {options}"
    return options


def test_install_md_documents_every_installer_option() -> None:
    doc = _DOC.read_text(encoding="utf-8")
    missing = [opt for opt in _parse_args_options() if f"`{opt}" not in doc]
    assert not missing, f"install.sh accepts options INSTALL.md does not document: {missing}"


def test_install_md_phase_count_matches_the_installer() -> None:
    total = int(re.search(r"^TOTAL_PHASES=(\d+)$", _text(), re.M).group(1))
    phases = re.findall(r'^\s+phase "', _text(), re.M)
    assert len(phases) == total, f"install.sh declares {total} phases and runs {len(phases)}"
    doc = _DOC.read_text(encoding="utf-8")
    rows = re.findall(rf"^\| (\d+)/{total} ", doc, re.M)
    assert rows == [
        str(n) for n in range(1, total + 1)
    ], f"INSTALL.md phase table is not 1/{total}..{total}/{total}: {rows}"


def test_install_md_lists_systemd_as_a_requirement() -> None:
    assert "systemd running as PID 1" in _DOC.read_text(encoding="utf-8")


def test_the_slm_url_has_one_form_per_path() -> None:
    """`/slm` without the slash is served the main app (full stack) or a 404 (SLM-only)."""
    for doc in (_DOC, repo_root() / "README.md"):
        text = doc.read_text(encoding="utf-8")
        bare = re.findall(r"(?:localhost|<server-ip>)/slm(?![/\w])", text)
        assert not bare, f"{doc.name} has SLM URLs without the trailing slash: {bare}"
        assert not re.search(r"https://<server-ip>(?![/\w])", text), f"{doc.name} gives the SLM URL without /slm/"
