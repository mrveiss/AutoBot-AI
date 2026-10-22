# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Every release publishes a tag-pinned, checksummed install.sh -- signed once the key exists (#18666).

The documented one-liner ran an unpinned `main` install.sh as root with no integrity check. The
release job now builds a copy whose DEFAULT_BRANCH is the release tag and its SHA256, and signs it
with the key image-sign.yml uses. cosign.pub is still a placeholder (#19126), so signing is gated on
a real key: a placeholder ships the installer checksum-only with a warning, never a fake signature.

The workflow steps' own `run:` scripts are executed here (with a stub `cosign`), not just grepped.
"""

from __future__ import annotations

import base64
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from repo_tests._paths import repo_root

from autobot_shared.isolated_git import git, isolated_git_env, make_repo
from autobot_shared.paths import scrubbed_git_env

_ROOT = repo_root()
_RELEASE = _ROOT / ".github" / "workflows" / "release.yml"
_IMAGE_SIGN = _ROOT / ".github" / "workflows" / "image-sign.yml"
_BASH = shutil.which("bash")


def _steps(path: Path, job: str) -> list[dict]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["jobs"][job]["steps"]


def _step(fragment: str) -> dict:
    found = [s for s in _steps(_RELEASE, "release") if fragment in str(s.get("name", ""))]
    assert len(found) == 1, f"expected one step named like {fragment!r}, found {len(found)}"
    return found[0]


def _clean_env() -> dict:
    """The canonical scrub (#15246): no inherited GIT_DIR can point a git write at the real repo."""
    return scrubbed_git_env()


def _run(script: str, cwd: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    if _BASH is None:
        pytest.skip("bash unavailable")
    (cwd / "tmp").mkdir(exist_ok=True)
    full_env = {**_clean_env(), "GITHUB_OUTPUT": str(cwd / "out.txt"), "TMPDIR": str(cwd / "tmp"), **(env or {})}
    return subprocess.run([_BASH, "-c", script], cwd=cwd, env=full_env, capture_output=True, text=True, timeout=60)


# --- the key gate -------------------------------------------------------------------------------


_REAL_PUB = "-----BEGIN PUBLIC KEY-----\nMFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE\n-----END PUBLIC KEY-----\n"


def _gate(tmp_path: Path, pub: str | None, secret: str) -> tuple[subprocess.CompletedProcess, str]:
    """Run the key gate's own script; *pub* None leaves cosign.pub missing."""
    if pub is not None:
        (tmp_path / "cosign.pub").write_text(pub, encoding="utf-8")
    out = _run(_step("Check the signing key is real")["run"], tmp_path, {"COSIGN_PRIVATE_KEY": secret})
    written = tmp_path / "out.txt"
    return out, written.read_text(encoding="utf-8").strip() if written.exists() else ""


@pytest.mark.parametrize(
    ("case", "pub", "secret", "ok", "real", "says"),
    [
        ("missing", None, "", False, "", "missing or empty"),
        ("empty", "", "k", False, "", "missing or empty"),
        ("placeholder", "PLACEHOLDER", "", True, "real=false", "UNSIGNED"),
        ("placeholder with a secret", "PLACEHOLDER", "k", True, "real=false", "commit the matching public key"),
        ("real without a secret", _REAL_PUB, "", False, "", "COSIGN_PRIVATE_KEY secret is empty"),
        ("real with a secret", _REAL_PUB, "k", True, "real=true", ""),
    ],
)
def test_the_key_gate_classifies_every_configuration(tmp_path, case, pub, secret, ok, real, says) -> None:
    """CodeRabbit on #19154: classify explicitly, and refuse an unusable configuration before the tag."""
    if pub == "PLACEHOLDER":
        pub = (_ROOT / "cosign.pub").read_text(encoding="utf-8")
    out, written = _gate(tmp_path, pub, secret)
    assert (out.returncode == 0) is ok, (case, out.stdout, out.stderr)
    assert written == real, case
    assert says in out.stdout, (case, out.stdout)


def test_the_key_gate_runs_before_the_tag_is_created() -> None:
    """A signing failure after the tag push strands a tagged release with no assets."""
    names = [s.get("name") for s in _steps(_RELEASE, "release")]
    assert names.index("Check the signing key is real (#18666)") < names.index("Commit changelog files and tag")


def test_signing_steps_are_gated_on_the_real_key() -> None:
    gate = "steps.check.outputs.release_needed == 'true' && steps.signkey.outputs.real == 'true'"
    assert _step("Sign the pinned installer").get("if") == gate
    assert [s for s in _steps(_RELEASE, "release") if s.get("name") == "Install cosign"][0].get("if") == gate


# --- building the pinned installer --------------------------------------------------------------


def test_the_pin_matches_install_sh_exactly() -> None:
    """The sed pattern and install.sh's DEFAULT_BRANCH line must agree, or the pin silently does nothing."""
    build = _step("Build the release's pinned installer")["run"]
    install = (_ROOT / "install.sh").read_text(encoding="utf-8")
    assert re.search(
        r'^readonly DEFAULT_BRANCH="main" PINNED_COMMIT=""', install, re.M
    ), "install.sh's pinned line changed"
    assert 'readonly DEFAULT_BRANCH=\\"main\\" PINNED_COMMIT=\\"\\"' in build, "the release no longer pins the line"
    assert "grep -q" in build and "exit 1" in build, "a pin that did not apply must fail the release"
    assert "sha256sum install.sh > install.sh.sha256" in build


def _tagged_checkout(path: Path, tag: str = "v1.2.3") -> str:
    """A throwaway repo holding install.sh, tagged as the release job tags it; returns the commit."""
    make_repo(path)
    shutil.copy(_ROOT / "install.sh", path / "install.sh")
    git(path, "add", "install.sh")
    git(path, "commit", "-q", "-m", "release")
    git(path, "tag", "-a", tag, "-m", f"Release {tag}")
    return git(path, "rev-parse", "HEAD").stdout.strip()


def test_the_build_pins_the_tag_and_its_commit_and_writes_a_checksum(tmp_path: Path) -> None:
    commit = _tagged_checkout(tmp_path)
    out = _run(_step("Build the release's pinned installer")["run"], tmp_path, {"VERSION": "v1.2.3"})
    assert out.returncode == 0, out.stderr
    pinned = (tmp_path / "dist" / "install.sh").read_text(encoding="utf-8")
    assert re.search(rf'^readonly DEFAULT_BRANCH="v1\.2\.3" PINNED_COMMIT="{commit}"', pinned, re.M)
    check = subprocess.run(["sha256sum", "-c", "install.sh.sha256"], cwd=tmp_path / "dist", capture_output=True)
    assert check.returncode == 0


@pytest.mark.parametrize("version", ["1.2.3", "v1.2", "v1.2.3;rm -rf /", "main"])
def test_the_build_refuses_a_version_that_is_not_a_release_tag(tmp_path: Path, version: str) -> None:
    shutil.copy(_ROOT / "install.sh", tmp_path / "install.sh")
    out = _run(_step("Build the release's pinned installer")["run"], tmp_path, {"VERSION": version})
    assert out.returncode != 0 and not (tmp_path / "dist" / "install.sh").exists()


# --- signing (stub cosign) ----------------------------------------------------------------------


def _stub_cosign(bin_dir: Path) -> None:
    bin_dir.mkdir()
    stub = bin_dir / "cosign"
    stub.write_text(
        '#!/bin/sh\necho "$@" >> "$COSIGN_LOG"\n'
        'case "$1" in sign-blob) while [ "$1" != --output-signature ]; do shift; done; echo sig > "$2";; esac\n',
        encoding="utf-8",
    )
    stub.chmod(0o755)


def test_signing_signs_self_verifies_removes_the_key_and_publishes_the_fingerprint(tmp_path: Path) -> None:
    _tagged_checkout(tmp_path)
    assert _run(_step("Build the release's pinned installer")["run"], tmp_path, {"VERSION": "v1.2.3"}).returncode == 0
    (tmp_path / "cosign.pub").write_text(
        "-----BEGIN PUBLIC KEY-----\nkey\n-----END PUBLIC KEY-----\n", encoding="utf-8"
    )
    (tmp_path / "RELEASE_NOTES.md").write_text("notes\n", encoding="utf-8")
    _stub_cosign(tmp_path / "bin")
    env = {
        "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}",
        "COSIGN_LOG": str(tmp_path / "cosign.log"),
        "COSIGN_PRIVATE_KEY": base64.b64encode(b"private").decode(),
        "COSIGN_PASSWORD": "",
    }
    out = _run(_step("Sign the pinned installer")["run"], tmp_path, env)
    assert out.returncode == 0, out.stderr
    calls = (tmp_path / "cosign.log").read_text(encoding="utf-8").splitlines()
    assert calls[0].startswith("sign-blob --yes --key ") and calls[1].startswith("verify-blob --key cosign.pub")
    assert (tmp_path / "dist" / "install.sh.sig").exists()
    assert not list((tmp_path / "tmp").iterdir()), "the private key file was left behind"
    assert "Installer signing key (`cosign.pub`) SHA256:" in (tmp_path / "RELEASE_NOTES.md").read_text()


def private_key_in_scripts(steps: list[dict]) -> list[str]:
    """Steps whose `run:` text names the private-key secret (it must arrive through env:)."""
    return [str(s.get("name")) for s in steps if "secrets.COSIGN_PRIVATE_KEY" in str(s.get("run", ""))]


def test_no_workflow_interpolates_the_private_key_into_a_script() -> None:
    """27's review: the key goes in via env:, never `${{ secrets.COSIGN_PRIVATE_KEY }}` inside run:."""
    for path in (_RELEASE, _IMAGE_SIGN):
        for job in yaml.safe_load(path.read_text(encoding="utf-8"))["jobs"].values():
            assert not private_key_in_scripts(job.get("steps", [])), path.name


def test_the_signature_asset_is_listed_only_when_the_key_is_real() -> None:
    """27's review: an always-listed .sig only worked because unmatched files were ignored."""
    release = _step("Create GitHub Release")["with"]
    lines = [line.strip() for line in release["files"].splitlines() if line.strip()]
    assert lines == [
        "dist/install.sh",
        "dist/install.sh.sha256",
        "${{ steps.signkey.outputs.real == 'true' && 'dist/install.sh.sig' || '' }}",
    ], lines
    assert release.get("fail_on_unmatched_files") is True, "a missing asset must fail the release"


def _pin_problems(texts: dict[str, str]) -> list[str]:
    """Each workflow must carry exactly one cosign-installer pin, and all pins must be the same."""
    pins = {name: set(re.findall(r"sigstore/cosign-installer@([0-9a-f]{40})", text)) for name, text in texts.items()}
    problems = [
        f"{name}: {len(found)} cosign-installer pins, expected 1" for name, found in pins.items() if len(found) != 1
    ]
    if len(set().union(*pins.values())) > 1:
        problems.append(f"pins differ: {pins}")
    return problems


def test_cosign_installer_is_the_same_pinned_version_everywhere() -> None:
    """One action version, declared once in effect: release.yml matches image-sign.yml."""
    assert _pin_problems({p.name: p.read_text(encoding="utf-8") for p in (_RELEASE, _IMAGE_SIGN)}) == []


def test_contrast_a_missing_or_differing_pin_is_reported() -> None:
    pin = "uses: sigstore/cosign-installer@" + "a" * 40
    assert _pin_problems({"a.yml": pin, "b.yml": pin}) == []
    assert _pin_problems({"a.yml": pin, "b.yml": "no pin here"}) == ["b.yml: 0 cosign-installer pins, expected 1"]
    assert _pin_problems({"a.yml": pin, "b.yml": pin.replace("a" * 40, "b" * 40)})[0].startswith("pins differ")


# --- install.sh: a pinned tag reinstalls without `git pull` on a detached HEAD -------------------


def _pull_guard() -> str:
    text = (_ROOT / "install.sh").read_text(encoding="utf-8")
    m = re.search(r"sh -c '(git -C \"\$1\" symbolic-ref -q HEAD[^']*)'", text)
    assert m, "install.sh no longer guards the reinstall pull"
    return m.group(1)


def test_a_tag_reinstall_skips_the_pull_and_a_branch_reinstall_pulls(tmp_path: Path) -> None:
    if shutil.which("git") is None:
        pytest.skip("git unavailable")
    repo = make_repo(tmp_path / "repo")
    for args in (("commit", "-q", "--allow-empty", "-m", "c"), ("tag", "v1.2.3"), ("checkout", "-q", "v1.2.3")):
        git(repo, *args)
    guard = _pull_guard()
    detached = subprocess.run(
        ["sh", "-c", guard, "_", str(repo), "v1.2.3"], capture_output=True, env=isolated_git_env()
    )
    assert detached.returncode == 0, "a detached tag checkout still tried to pull"
    git(repo, "checkout", "-q", "-b", "work")
    on_branch = subprocess.run(["sh", "-c", guard, "_", str(repo), "work"], capture_output=True, env=isolated_git_env())
    assert on_branch.returncode != 0, "on a branch the guard must pull (here: no remote, so it fails)"


def _commit_check() -> str:
    text = (_ROOT / "install.sh").read_text(encoding="utf-8")
    m = re.search(r'(\[\[ -z "\$\{PINNED_COMMIT\}" .*?\]\] \|\| fatal "[^"]*")', text)
    assert m, "install.sh no longer checks the checked-out commit against PINNED_COMMIT"
    return m.group(1)


@pytest.mark.parametrize(
    ("pinned", "branch", "head", "refused"),
    [
        ("a" * 40, "v1.2.3", "a" * 40, False),  # the tag still names the release commit
        ("a" * 40, "v1.2.3", "b" * 40, True),  # the tag moved: refuse
        ("", "main", "b" * 40, False),  # an unpinned (main) installer checks nothing
        ("a" * 40, "my-branch", "b" * 40, False),  # an explicit --branch is the operator's choice
    ],
)
def test_a_moved_tag_is_refused_after_checkout(pinned: str, branch: str, head: str, refused: bool) -> None:
    if _BASH is None:
        pytest.skip("bash unavailable")
    script = (
        f'PINNED_COMMIT="{pinned}" DEFAULT_BRANCH="v1.2.3" GIT_BRANCH="{branch}" installed_sha="{head}"\n'
        'fatal() { echo "REFUSED: $*"; exit 1; }\n' + _commit_check() + "\necho OK\n"
    )
    out = subprocess.run([_BASH, "-c", script], capture_output=True, text=True, timeout=30)
    assert (out.returncode != 0) is refused, out.stdout + out.stderr
    assert ("REFUSED" in out.stdout) is refused


def test_install_md_documents_verifying_the_release_before_running() -> None:
    doc = (_ROOT / "INSTALL.md").read_text(encoding="utf-8")
    for needed in (
        "/releases/download/${TAG}",
        "sha256sum -c install.sh.sha256",
        "cosign verify-blob --key cosign.pub --signature install.sh.sig install.sh",
        "a channel a release cannot rewrite",
        "comparison aid only",
    ):
        assert needed in doc, f"INSTALL.md no longer shows: {needed}"
    assert re.search(
        r"sha256sum -c install\.sh\.sha256 \\\n\s+&& cosign verify-blob [^\n]+ \\\n\s+&& sudo bash install\.sh", doc
    ), "install.sh must run only if the checksum and the signature both verify (an && chain)"
    assert re.search(
        r"curl -fsSL \"https://github\.com/mrveiss/AutoBot-AI/releases/download/\$\{TAG\}/install\.sh\" \| sudo bash",
        doc,
    ), "the pinned one-liner is missing"
    assert (
        "sha256sum -c install.sh.sha256 && sudo bash install.sh" in doc
    ), "no checksum-only path while the key is unset"
    assert "proves the file arrived intact, not who made it" in doc, "checksum-only is not authenticity (#19126)"
    assert "air-gapped installs are out of scope" in doc, "the offline path is neither documented nor ruled out"


def expressions_in_scripts(steps: list[dict]) -> dict[str, list[str]]:
    """{step name: the `${{ }}` expressions written into its `run:` text}."""
    return {
        str(s.get("name")): re.findall(r"\$\{\{[^}]*\}\}", s.get("run", "")) for s in steps if "${{" in s.get("run", "")
    }


def test_no_release_step_interpolates_an_expression_into_its_script() -> None:
    """27's review: step outputs reach `run:` through env:, never as `${{ }}` in the script text."""
    left = expressions_in_scripts(_steps(_RELEASE, "release"))
    assert not left, left


def test_contrast_both_detectors_flag_the_script_form_and_pass_the_env_form() -> None:
    """CodeRabbit on #19154: each detector is shown firing on `${{ }}` in run: and not on env:."""
    inline = [
        {
            "name": "inline",
            "run": 'printf %s "${{ secrets.COSIGN_PRIVATE_KEY }}" > k\necho "${{ steps.check.outputs.version }}"',
        }
    ]
    via_env = [
        {
            "name": "via env",
            "env": {
                "COSIGN_PRIVATE_KEY": "${{ secrets.COSIGN_PRIVATE_KEY }}",
                "VERSION": "${{ steps.check.outputs.version }}",
            },
            "run": 'printf %s "${COSIGN_PRIVATE_KEY}" > k\necho "${VERSION}"',
        }
    ]
    assert private_key_in_scripts(inline) == ["inline"] and private_key_in_scripts(via_env) == []
    assert expressions_in_scripts(inline) == {
        "inline": ["${{ secrets.COSIGN_PRIVATE_KEY }}", "${{ steps.check.outputs.version }}"]
    }
    assert expressions_in_scripts(via_env) == {}
