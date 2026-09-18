# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No ChromaDB launch site binds a wildcard interface (#15317).

Two of the three files originally reviewed here had `--host 0.0.0.0` -- every
interface, in front of four unpatchable advisories, one a pre-auth RCE. The
host firewall was the only remaining control. A first version of this guard
regex-scanned a hand-kept tuple of three files for that literal, which left
two real gaps (PR #16882 review):

* it never resolved `chromadb_bind_host` itself -- the two live templates
  read `{{ chromadb_bind_host }}` (unrendered Jinja), so a future edit to its
  real default in `group_vars/all.yml` could widen the bind and every check
  here would keep passing;
* `install-bare-metal.sh`'s own launch site was outside the hand-kept tuple,
  so the docstring's "every file" claim was false as written.

This version resolves the variable's actual value (default + any override)
and discovers launch sites by sweeping tracked `.service`/`.service.j2`/
`.sh` files rather than naming them, so both gaps are structural rather than
a longer list to maintain.

No named cluster-mode allowlist: `docs/architecture/NETWORK_TOPOLOGY.md`'s
only documented multi-node path is setting `chromadb_bind_host` to a specific
fleet IP, which is never a wildcard, and #15317's own AC is explicit --
"never an 'allow from anywhere' rule". So the check below only special-cases
the wildcard *shape* (`0.0.0.0` / `::` / empty), not "anything other than
127.0.0.1"; a specific address passes with no allowlist entry needed.
"""

from __future__ import annotations

import re
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_REPO_ROOT = repo_root()

# The canonical bind-address default. Checked directly, separately from the
# override sweep below, so its own absence (a rename, a moved file) is a
# distinct, clearly-named failure rather than one more zero-length list.
_GROUP_VARS_ALL = "autobot-slm-backend/ansible/inventory/group_vars/all.yml"

# The two live templates that must read the SAME variable -- named directly
# (not sweep-discovered) because this test asserts a relationship between
# exactly these two files, not "some files somewhere".
_LIVE_TEMPLATES = (
    "autobot-slm-backend/ansible/roles/ai-stack/templates/autobot-chromadb.service.j2",
    "autobot-slm-backend/ansible/roles/redis/templates/autobot-chromadb.service.j2",
)

# Extensions a ChromaDB `chroma run` ExecStart has ever appeared in: two
# ansible .j2 templates, one decorative reference .service, and the
# bare-metal installer's inline heredoc .sh unit.
_LAUNCH_SITE_PATTERNS = ("*.service", "*.service.j2", "*.sh")

# A `chroma run` invocation followed by `--host <value>` within a bounded
# window, tolerating the `chroma run \` + newline-indented `--host ...`
# continuation style install-bare-metal.sh and the redis template use, as
# well as the single-line form the ai-stack template uses. 120 chars covers
# both comfortably while staying far short of an unrelated "chroma run" or
# "--host" mention elsewhere in a file (measured: the guard's own module
# docstring above and every prose "chroma runs on/from/unauthenticated" hit
# in the tree sit hundreds of characters from the nearest "--host").
_CHROMA_LAUNCH_SITE_WINDOW = re.compile(r"chroma\s+run\b[\s\S]{0,120}?--host\s+\S+")

# A bind literal typed directly into a rendered/heredoc ExecStart. 127.0.0.1
# is the chosen safe default and is not itself a violation; a real
# regression looks like 0.0.0.0, the IPv6 wildcard, or an empty value.
_HARDCODED_WIDE_BIND = re.compile(r"""--host\s+(?:0\.0\.0\.0|::|""|'')""")

# chromadb_bind_host's assignment at the start of a line -- deliberately a
# text-level scan, not a YAML/Jinja parse: cheap, matches this guard's
# existing style, and sufficient for a top-level scalar assignment, which is
# the only form this variable has ever taken in this tree.
_BIND_VAR_PATTERN = re.compile(r"^chromadb_bind_host:\s*(.*)$", re.MULTILINE)

_WILDCARD_BIND_VALUES = {"0.0.0.0", "::", ""}

# Every file a `chromadb_bind_host` override could legitimately live in:
# other group_vars files, host_vars (none exist today -- the pattern still
# sweeps for one), and every role's own defaults.
_OVERRIDE_SEARCH_PATTERNS = (
    "autobot-slm-backend/ansible/inventory/group_vars/*.yml",
    "autobot-slm-backend/ansible/inventory/host_vars/*.yml",
    "autobot-slm-backend/ansible/roles/*/defaults/main.yml",
)


def _extract_bind_host_value(text: str) -> str | None:
    """The value assigned to `chromadb_bind_host` in *text*, quotes stripped."""
    match = _BIND_VAR_PATTERN.search(text)
    if not match:
        return None
    raw = match.group(1).split("#", 1)[0].strip()
    return raw.strip("'\"")


def _is_wildcard_bind(value: str) -> bool:
    """True for 0.0.0.0 / :: / empty -- never for a specific address.

    A specific fleet IP (loopback or otherwise) is the documented multi-node
    override and must pass; only the wildcard shape is special-cased.
    """
    return value.strip().strip("'\"") in _WILDCARD_BIND_VALUES


def _discover_chroma_launch_sites(root: Path) -> list[str]:
    """Every tracked launch-site-shaped file that actually invokes
    `chroma run ... --host` -- sweep, not a hand-kept list (#15317 review)."""
    try:
        candidates = tracked_paths(root, *_LAUNCH_SITE_PATTERNS)
    except EmptyEnumeration:
        return []
    return [
        rel
        for rel in candidates
        if _CHROMA_LAUNCH_SITE_WINDOW.search((root / rel).read_text(encoding="utf-8", errors="ignore"))
    ]


def _discover_override_candidate_files(root: Path) -> list[str]:
    """Every group_vars/host_vars/role-defaults file that could carry a
    `chromadb_bind_host` override, whether or not it actually does."""
    found: list[str] = []
    for pattern in _OVERRIDE_SEARCH_PATTERNS:
        try:
            found.extend(tracked_paths(root, pattern))
        except EmptyEnumeration:
            continue
    return found


def _bind_host_overrides(root: Path, candidates: list[str]) -> list[tuple[str, str]]:
    """(path, value) for each candidate that assigns chromadb_bind_host,
    excluding the canonical default (group_vars/all.yml, checked on its own by
    test_chromadb_bind_host_default_resolves_to_a_non_wildcard)."""
    overrides = []
    for rel in candidates:
        if rel == _GROUP_VARS_ALL:
            continue
        text = (root / rel).read_text(encoding="utf-8", errors="ignore")
        value = _extract_bind_host_value(text)
        if value is not None:
            overrides.append((rel, value))
    return overrides


#: 4 known launch sites today: the two live ansible templates, the infra
#: decorative reference copy, and install-bare-metal.sh's heredoc unit.
CHROMA_LAUNCH_SITES = declare(
    "chromadb-bind-launch-sites",
    discover=_discover_chroma_launch_sites,
    floor=4,
    growth=2,
    what="files invoking `chroma run ... --host` -- ChromaDB bind launch sites (#15317)",
)

#: 37 candidates as of #15317's guard rewrite: 8 group_vars files + 29
#: role defaults/main.yml files + 0 host_vars (the directory does not exist
#: yet). Re-measure with `git ls-files` before lowering.
BIND_HOST_OVERRIDE_CANDIDATES = declare(
    "chromadb-bind-host-override-candidates",
    discover=_discover_override_candidate_files,
    floor=30,
    growth=15,
    what="group_vars/host_vars/role-defaults files scanned for a chromadb_bind_host override (#15317)",
)


def test_the_sweep_reaches_the_known_chroma_launch_sites() -> None:
    """Vacuity floor: a sweep that quietly narrows -- wrong root, wrong
    extensions, a pattern typo -- must not pass as a clean tree."""
    CHROMA_LAUNCH_SITES.examined(_REPO_ROOT)


def test_no_chroma_launch_site_hardcodes_a_wide_bind() -> None:
    offenders = [
        rel
        for rel in CHROMA_LAUNCH_SITES.examined(_REPO_ROOT)
        if _HARDCODED_WIDE_BIND.search((_REPO_ROOT / rel).read_text(encoding="utf-8"))
    ]
    assert not offenders, (
        f"{offenders} bind ChromaDB to a wildcard literally -- in front of four unpatchable "
        "advisories (one pre-auth RCE), the host firewall becomes the only remaining "
        "control. Bind through chromadb_bind_host (group_vars/all.yml), not a literal (#15317)."
    )


def test_the_ai_stack_and_redis_templates_share_one_bind_variable() -> None:
    """The two live templates must read the SAME variable, or a value set in one
    place silently fails to narrow the unit the other role renders."""
    for rel_path in _LIVE_TEMPLATES:
        text = (_REPO_ROOT / rel_path).read_text(encoding="utf-8")
        assert "{{ chromadb_bind_host }}" in text, f"{rel_path} does not read chromadb_bind_host"


def test_chromadb_bind_host_default_resolves_to_a_non_wildcard() -> None:
    """The gap the PR #16882 review named: the old guard never looked at what
    chromadb_bind_host actually resolves to, only at whether the templates
    named it. A future edit widening group_vars/all.yml:426 must fail here."""
    text = (_REPO_ROOT / _GROUP_VARS_ALL).read_text(encoding="utf-8")
    value = _extract_bind_host_value(text)
    assert value is not None, f"chromadb_bind_host not found in {_GROUP_VARS_ALL} -- this guard would be vacuous"
    assert not _is_wildcard_bind(value), (
        f"chromadb_bind_host resolves to {value!r} in {_GROUP_VARS_ALL} -- a wildcard bind reopens "
        "the every-interface exposure #15317 closed, in front of four unpatchable ChromaDB "
        "advisories, one a pre-auth RCE."
    )


def test_the_override_scan_reaches_a_real_population() -> None:
    """Vacuity floor for the override sweep, distinct from the launch-site
    floor above -- a broken glob here would make the next test check zero
    files and still read as a clean pass."""
    BIND_HOST_OVERRIDE_CANDIDATES.examined(_REPO_ROOT)


def test_no_chromadb_bind_host_override_widens_to_a_wildcard() -> None:
    """Any group_vars/host_vars/role-default that overrides chromadb_bind_host
    must still resolve to a real address. #15317's own AC is explicit that a
    multi-node install needs a scoped firewall rule, "never an allow from
    anywhere rule" -- so a specific fleet IP passes (the documented multi-node
    override) and 0.0.0.0/::/empty do not, wherever they are set."""
    candidates = BIND_HOST_OVERRIDE_CANDIDATES.examined(_REPO_ROOT)
    offenders = [
        (rel, value) for rel, value in _bind_host_overrides(_REPO_ROOT, list(candidates)) if _is_wildcard_bind(value)
    ]
    assert not offenders, f"{offenders} override chromadb_bind_host to a wildcard bind (#15317)"


def test_is_wildcard_bind_matches_only_the_documented_wildcard_forms() -> None:
    """0.0.0.0 / :: / empty fail; a specific address -- loopback or a fleet
    IP, the documented multi-node override -- passes. No named cluster-mode
    allowlist: only the wildcard shape is special-cased (#15317 review)."""
    for wildcard in ("0.0.0.0", "::", "", '""', "''"):
        assert _is_wildcard_bind(wildcard), f"{wildcard!r} should be treated as a wildcard bind"
    for real in ("127.0.0.1", "10.0.4.23", "192.168.1.50"):
        assert not _is_wildcard_bind(real), f"{real!r} must not be flagged as a wildcard"


def test_the_wide_bind_sweep_catches_a_synthetic_wildcard_launch_site(tmp_path: Path) -> None:
    """Negative control: a fabricated wide-bind unit must be caught by the same
    discovery-marker + literal-scan pair the real guard runs above, proving
    neither step is silently vacuous just because today's tree is clean."""
    fake_unit = tmp_path / "fake-chromadb.service"
    fake_unit.write_text(
        "ExecStart=/venv/bin/chroma run \\\n    --host 0.0.0.0 \\\n    --port 8100\n",
        encoding="utf-8",
    )
    text = fake_unit.read_text(encoding="utf-8")
    assert _CHROMA_LAUNCH_SITE_WINDOW.search(text), "sweep marker failed to recognize a synthetic chroma launch site"
    assert _HARDCODED_WIDE_BIND.search(text), "literal-bind detector failed to catch a synthetic 0.0.0.0"


def test_the_variable_check_catches_a_synthetic_wildcard_override(tmp_path: Path) -> None:
    """Negative control for the resolved-value path: a fabricated override
    file must be caught by the same extract + wildcard-check pair the real
    guard runs above."""
    fake_vars = tmp_path / "fake_group_vars.yml"
    fake_vars.write_text('chromadb_bind_host: "0.0.0.0"\n', encoding="utf-8")
    value = _extract_bind_host_value(fake_vars.read_text(encoding="utf-8"))
    assert value == "0.0.0.0"
    assert _is_wildcard_bind(value), "wildcard check failed to catch a synthetic 0.0.0.0 override"
