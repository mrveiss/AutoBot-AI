# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The public docs a new self-hoster follows stay correct as the code moves (#19178, #19179, #19184, #19185).

An end-user walk (README -> INSTALL -> user guide) hit dead links and anchors, requirement numbers
that disagreed with what install.sh enforces, install commands that fail verbatim (no sudo, no
env files, `cp .env.example .env` for Docker), and a product name users should never see. Each
check below reads the docs a user actually reaches and fails the moment one drifts again.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
from repo_tests._paths import repo_root

_ROOT = repo_root()


def _user_docs() -> list[Path]:
    """README, INSTALL, the docs index, and the user docs and user guide trees."""
    docs = [_ROOT / "README.md", _ROOT / "INSTALL.md", _ROOT / "docs" / "README.md"]
    for tree in ("docs/user", "docs/user-guide"):
        docs += sorted((_ROOT / tree).rglob("*.md"))
    assert len(docs) >= 10, f"the user-doc set shrank to {len(docs)} -- the checks below would cover too little"
    return docs


_FENCE = re.compile(r"^```.*?^```", re.M | re.S)
_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
# A reference definition, `[label]: dest`; footnotes (`[^1]: text`) are not links.
_REF_DEF = re.compile(r"^ {0,3}\[(?!\^)[^\]]+\]:[ \t]*<?([^\s>]+)>?", re.M)


def anchor_slug(heading: str) -> str:
    """GitHub's heading anchor: lowercase, punctuation dropped, spaces to hyphens."""
    text = re.sub(r"[`*_]", "", heading.strip().lower())
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def anchors(md: Path) -> set[str]:
    body = _FENCE.sub("", md.read_text(encoding="utf-8"))
    return {anchor_slug(m.group(1)) for m in re.finditer(r"^#{1,6}\s+(.+?)\s*#*\s*$", body, re.M)}


def link_targets(text: str) -> list[str]:
    """Every link destination outside code fences: inline `[t](dest)` and reference `[l]: dest`."""
    body = _FENCE.sub("", text)
    return _LINK.findall(body) + _REF_DEF.findall(body)


def broken_links(md: Path) -> list[str]:
    """Relative links in *md* whose file, or #anchor, does not exist."""
    bad = []
    for target in link_targets(md.read_text(encoding="utf-8")):
        if re.match(r"^[a-z][a-z0-9+.-]*:", target) or target.startswith("<"):
            continue  # absolute URL, mailto:, or an autolink
        path_part, _, anchor = target.partition("#")
        dest = md if not path_part else (md.parent / path_part).resolve()
        if not dest.exists():
            bad.append(f"{target} (no such file)")
        elif anchor and dest.suffix == ".md" and anchor.lower() not in anchors(dest):
            bad.append(f"{target} (no such heading)")
    return bad


def test_every_relative_link_and_anchor_in_the_user_docs_resolves() -> None:
    """#19185 AC3: a link checker over the user docs, run with the python suite in CI."""
    found = {str(md.relative_to(_ROOT)): broken_links(md) for md in _user_docs()}
    found = {k: v for k, v in found.items() if v}
    assert not found, f"dead links in the user docs: {found}"


def test_the_requirement_minimums_are_the_installers_own() -> None:
    """#19178 AC4: INSTALL.md's one requirements table states what install.sh refuses below."""
    install = (_ROOT / "install.sh").read_text(encoding="utf-8")
    mem = int(re.search(r"^readonly REQUIRED_MEM_MB=(\d+)", install, re.M).group(1))
    disk = int(re.search(r"^readonly REQUIRED_DISK_MB=(\d+)", install, re.M).group(1))
    table = (_ROOT / "INSTALL.md").read_text(encoding="utf-8")
    ram_row = re.search(r"^\| RAM \| ([\d.]+) GB", table, re.M)
    disk_row = re.search(r"^\| Disk \| ([\d.]+) GB", table, re.M)
    assert ram_row and disk_row, "INSTALL.md's requirements table no longer has RAM and Disk rows"
    assert (
        float(ram_row.group(1)) * 1024 == mem
    ), f"INSTALL.md says {ram_row.group(1)} GB RAM, install.sh needs {mem} MB"
    assert (
        float(disk_row.group(1)) * 1024 == disk
    ), f"INSTALL.md says {disk_row.group(1)} GB disk, install.sh needs {disk} MB"


def command_problems(text: str) -> list[str]:
    """Documented shell commands a user would copy that cannot work verbatim."""
    problems = []
    for block in re.findall(r"^```(?:bash|sh|shell|console)?\n(.*?)^```", text, re.M | re.S):
        joined = re.sub(r"\\\n\s*", " ", block)
        for line in joined.splitlines():
            line = line.strip()
            if re.search(r"install\.sh[\"']?\s*\|\s*bash\b", line):
                problems.append(f"piped to bash without sudo: {line}")
            if re.search(r"^docker[ -]compose\b", line) and "--env-file docker/.env.docker" not in line:
                problems.append(f"compose without docker/.env.docker: {line}")
            if re.search(r"^docker[ -]compose\b", line) and ".env.docker" in line and ".env.secrets" not in line:
                problems.append(f"compose without docker/.env.secrets: {line}")
            if re.search(r"\bcp \.env\.example \.env\b", line):
                problems.append(f".env.example is for native installs, not Docker: {line}")
    return problems


def test_every_documented_install_command_works_verbatim() -> None:
    """#19179 AC3: sudo where install.sh needs root; both env files on every compose command."""
    found = {str(md.relative_to(_ROOT)): command_problems(md.read_text(encoding="utf-8")) for md in _user_docs()}
    found = {k: v for k, v in found.items() if v}
    assert not found, found


def llc_mentions(text: str) -> list[str]:
    """User-visible 'LLC' -- the product is Company OS (owner, 2026-10-22). Code identifiers
    (llc_*, LLC_* names, paths) are excluded: only the bare word in prose counts."""
    return [m.group(0) for m in re.finditer(r"(?<![\w/.-])LLC(?![\w/.-])", _FENCE.sub("", text))]


_LOCALE_GLOBS = ("autobot-frontend/src/i18n/locales/*.json", "autobot-slm-frontend/src/locales/*.json")

# Public docs outside the user trees that name the product (#19184): the glossary and indexes a
# reader lands on, and the pages the wiki publishes from docs/.
_COMPANY_OS_DOCS = (
    "docs/GLOSSARY.md",
    "docs/INDEX.md",
    "docs/architecture/PLATFORM_MODEL.md",
    "docs/features/CATALOG.md",
    "docs/llc/_index.md",
)


def _locale_files() -> list[Path]:
    """Every UI locale. Each glob must match on its own: one wrong path (the SLM's was
    ``src/i18n/locales``, which does not exist) must not hide behind the other (#19184)."""
    files: list[Path] = []
    for pattern in _LOCALE_GLOBS:
        matched = sorted(_ROOT.glob(pattern))
        assert matched, f"{pattern} matches no locale file -- that UI's strings would go unchecked"
        files += matched
    return files


def _company_os_docs() -> list[Path]:
    docs = [_ROOT / rel for rel in _COMPANY_OS_DOCS]
    missing = [str(d.relative_to(_ROOT)) for d in docs if not d.is_file()]
    assert not missing, f"named docs no longer exist: {missing}"
    return docs


def test_no_user_doc_or_ui_string_says_llc() -> None:
    """#19184 AC2."""
    found = {
        str(f.relative_to(_ROOT)): llc_mentions(f.read_text(encoding="utf-8"))
        for f in _user_docs() + _company_os_docs() + _locale_files()
    }
    found = {k: v for k, v in found.items() if v}
    assert not found, f"'LLC' where users should read 'Company OS': {found}"


_BACKEND_ON_8001 = re.compile(r"(?:localhost|127\.0\.0\.1|0\.0\.0\.0):8001/(?:api|health)")
# The main backend's canonical health path is /api/system/health (docs/api/health.md); /api/health is
# a legacy alias. The SLM's own /slm/api/health is a different service and is fine.
_LEGACY_BACKEND_HEALTH = re.compile(r"(?<!/slm)/api/health\b")


def test_no_user_doc_health_checks_the_backend_on_8001() -> None:
    """#19183 AC2: the backend is reached through nginx (Docker ``http://localhost/api``, native
    ``https://<server>/api``); in Docker 8001 is RedisInsight, so a check there never reaches it."""
    found = {str(f.relative_to(_ROOT)): _BACKEND_ON_8001.findall(f.read_text(encoding="utf-8")) for f in _user_docs()}
    found = {k: v for k, v in found.items() if v}
    assert not found, f"backend health checked on RedisInsight's port: {found}"


def test_user_docs_check_the_backend_on_its_canonical_health_path() -> None:
    """#19183 review: the main backend is checked at /api/system/health, not the legacy alias."""
    found = {
        str(f.relative_to(_ROOT)): _LEGACY_BACKEND_HEALTH.findall(f.read_text(encoding="utf-8")) for f in _user_docs()
    }
    found = {k: v for k, v in found.items() if v}
    assert not found, f"the legacy /api/health alias where /api/system/health is canonical: {found}"


def test_contrast_a_locale_glob_that_matches_nothing_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """One wrong locale path must fail on its own, even when the other glob matches."""
    monkeypatch.setattr(
        sys.modules[__name__], "_LOCALE_GLOBS", (_LOCALE_GLOBS[0], "autobot-slm-frontend/src/i18n/locales/*.json")
    )
    with pytest.raises(AssertionError, match="matches no locale file"):
        _locale_files()


def test_contrast_reference_links_are_checked(tmp_path: Path) -> None:
    """A reference-style destination is a link like any other: a broken one fails, a good one passes."""
    (tmp_path / "INSTALL.md").write_text("# Setup\n", encoding="utf-8")
    good = tmp_path / "good.md"
    good.write_text("See [Install][setup].\n\n[setup]: ./INSTALL.md#setup\n[^1]: a footnote\n", encoding="utf-8")
    bad = tmp_path / "bad.md"
    bad.write_text("See [Install][setup].\n\n[setup]: ./MISSING.md\n", encoding="utf-8")
    assert link_targets(good.read_text(encoding="utf-8")) == ["./INSTALL.md#setup"]
    assert broken_links(good) == []
    assert broken_links(bad) == ["./MISSING.md (no such file)"]


def test_contrast_each_detector_fires() -> None:
    assert anchor_slug("Quick Start (3 steps)") == "quick-start-3-steps"
    assert anchor_slug("The `autobot` account's root access") == "the-autobot-accounts-root-access"
    assert command_problems("```bash\ncurl -fsSL https://x/install.sh | bash\n```\n")
    assert not command_problems("```bash\ncurl -fsSL https://x/install.sh | sudo bash\n```\n")
    assert command_problems("```bash\ndocker compose up -d\n```\n")
    assert not command_problems(
        "```bash\ndocker compose --env-file docker/.env.docker \\\n  --env-file docker/.env.secrets up -d\n```\n"
    )
    assert llc_mentions("Run AutoBot LLC today") == ["LLC"]
    assert llc_mentions("| [LLC Module PRD](../planning/PRD_AutoBot_LLC_Module.md) |") == ["LLC"]
    assert _BACKEND_ON_8001.findall("curl http://localhost:8001/health")
    assert _BACKEND_ON_8001.findall("curl http://127.0.0.1:8001/api/system/health")
    assert _BACKEND_ON_8001.findall("curl http://0.0.0.0:8001/health")
    assert not _BACKEND_ON_8001.findall("RedisInsight on 127.0.0.1:8001; curl http://localhost/api/system/health")
    assert _LEGACY_BACKEND_HEALTH.findall("curl http://localhost/api/health")
    assert not _LEGACY_BACKEND_HEALTH.findall("curl -sk https://127.0.0.1/slm/api/health; /api/system/health")
    assert llc_mentions("the llc_agents module and LLC_MODE flag, docs/llc/x.md") == []
