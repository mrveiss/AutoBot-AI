# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Every release publishes a tag-pinned, checksummed, cosign-signed install.sh (#18666).

The documented one-liner ran an unpinned `main` install.sh as root with no integrity check,
although the repo ships cosign.pub. The release job now builds a copy whose DEFAULT_BRANCH is
the release tag, signs it with the key image-sign.yml uses, self-verifies, and attaches the
script, its SHA256 and its signature to the GitHub release.
"""

from __future__ import annotations

import re

import yaml
from repo_tests._paths import repo_root

_ROOT = repo_root()
_RELEASE = _ROOT / ".github" / "workflows" / "release.yml"


def _steps() -> list[dict]:
    return yaml.safe_load(_RELEASE.read_text(encoding="utf-8"))["jobs"]["release"]["steps"]


def _step(fragment: str) -> dict:
    found = [s for s in _steps() if fragment in str(s.get("name", ""))]
    assert len(found) == 1, f"expected one step named like {fragment!r}, found {len(found)}"
    return found[0]


def test_the_pin_matches_install_sh_exactly() -> None:
    """The sed pattern and install.sh's DEFAULT_BRANCH line must agree, or the pin silently does nothing."""
    build = _step("Build the release's pinned installer")["run"]
    install = (_ROOT / "install.sh").read_text(encoding="utf-8")
    assert re.search(r'^readonly DEFAULT_BRANCH="main"$', install, re.M), "install.sh's pinned line changed"
    assert 'readonly DEFAULT_BRANCH=\\"main\\"$' in build, "the release no longer pins DEFAULT_BRANCH"
    assert "grep -qx" in build and "exit 1" in build, "a pin that did not apply must fail the release"
    assert "sha256sum install.sh > install.sh.sha256" in build


def test_the_installer_is_signed_with_the_repo_key_and_self_verified() -> None:
    sign = _step("Sign the pinned installer")["run"]
    assert "cosign sign-blob --yes --key /tmp/cosign.key --output-signature dist/install.sh.sig dist/install.sh" in sign
    assert "rm -f /tmp/cosign.key" in sign
    assert "cosign verify-blob --key cosign.pub --signature dist/install.sh.sig dist/install.sh" in sign
    assert "sha256sum -c install.sh.sha256" in sign


def test_the_three_assets_are_attached_to_the_release() -> None:
    files = _step("Create GitHub Release")["with"]["files"].split()
    assert files == ["dist/install.sh", "dist/install.sh.sha256", "dist/install.sh.sig"], files


def test_signing_steps_run_only_when_a_release_is_made() -> None:
    for name in ("Build the release's pinned installer", "Sign the pinned installer"):
        assert _step(name).get("if") == "steps.check.outputs.release_needed == 'true'", name


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
    paths = (_RELEASE, _ROOT / ".github" / "workflows" / "image-sign.yml")
    assert _pin_problems({p.name: p.read_text(encoding="utf-8") for p in paths}) == []


def test_contrast_a_missing_or_differing_pin_is_reported() -> None:
    pin = "uses: sigstore/cosign-installer@" + "a" * 40
    assert _pin_problems({"a.yml": pin, "b.yml": pin}) == []
    assert _pin_problems({"a.yml": pin, "b.yml": "no pin here"}) == ["b.yml: 0 cosign-installer pins, expected 1"]
    assert _pin_problems({"a.yml": pin, "b.yml": pin.replace("a" * 40, "b" * 40)})[0].startswith("pins differ")


def test_install_md_documents_verifying_the_release_before_running() -> None:
    doc = (_ROOT / "INSTALL.md").read_text(encoding="utf-8")
    for needed in (
        "/releases/download/${TAG}",
        "sha256sum -c install.sh.sha256",
        "cosign verify-blob --key cosign.pub --signature install.sh.sig install.sh",
    ):
        assert needed in doc, f"INSTALL.md no longer shows: {needed}"
    assert re.search(
        r"sha256sum -c install\.sh\.sha256 \\\n\s+&& cosign verify-blob [^\n]+ \\\n\s+&& sudo bash install\.sh", doc
    ), "install.sh must run only if the checksum and the signature both verify (an && chain)"
    assert re.search(
        r"curl -fsSL \"https://github\.com/mrveiss/AutoBot-AI/releases/download/\$\{TAG\}/install\.sh\" \| sudo bash",
        doc,
    ), "the pinned one-liner is missing"
    assert "air-gapped installs are out of scope" in doc, "the offline path is neither documented nor ruled out"
