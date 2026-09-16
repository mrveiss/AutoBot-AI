"""The changelog branch name must carry no slash, and the sweep must know it (#16563).

`release/changelog-${VERSION}` was unpushable from the moment a branch named
`release` existed: git stores refs as paths, so `refs/heads/release` (a file) and
`refs/heads/release/changelog-v0.9.0` (a directory) cannot coexist. Every release
run from the 2026-09-12 rename onward failed at that push with
`directory file conflict`, which is why no changelog reached the release branch.

A flat name cannot hit that, so the first test pins the absence of a slash rather
than the particular name. The second test is the one that matters longer: the
release workflow and the branch sweep have to agree on the prefix, or renaming it
in one place teaches the sweep to treat released changelog branches as abandoned
work. That is a drift between two files that no single-file test can see.
"""

import re

from repo_tests._paths import repo_root

# #15925: one spelling of "the repository root" for every guard here. Re-deriving
# it from __file__ is what the coverage instrument cannot pattern-match, so a
# guard that binds it by hand is a guard that instrument cannot see.
RELEASE_WORKFLOW = repo_root() / ".github" / "workflows" / "release.yml"
BRANCH_GUARDS = repo_root() / "scripts" / "lib" / "branch-guards.sh"


def _changelog_branch_expression() -> str:
    """The right-hand side of the BRANCH= assignment in the changelog step."""
    text = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    match = re.search(r'^\s*BRANCH="([^"]+)"', text, re.M)
    assert match, "release.yml no longer assigns BRANCH= — update this guard with it"
    return match.group(1)


def _archival_prefixes() -> list[str]:
    text = BRANCH_GUARDS.read_text(encoding="utf-8")
    match = re.search(r'BRANCH_ARCHIVAL_PREFIXES="\$\{BRANCH_ARCHIVAL_PREFIXES:-([^}"]+)\}"', text)
    assert match, "branch-guards.sh no longer defines BRANCH_ARCHIVAL_PREFIXES"
    return match.group(1).split()


def test_changelog_branch_name_carries_no_slash():
    expression = _changelog_branch_expression()
    assert "/" not in expression, (
        f"changelog branch {expression!r} contains a slash. A ref cannot be both a file and a "
        "directory, so any prefix that is also a branch name makes the push fail with "
        "'directory file conflict' (#16563)."
    )


def test_the_sweep_recognises_the_changelog_branch_as_archival():
    """Rename the branch without telling the sweep and it reads as abandoned work."""
    literal_prefix = _changelog_branch_expression().split("${")[0]
    assert literal_prefix, "changelog branch name starts with a variable — nothing to match a prefix against"
    prefixes = _archival_prefixes()
    assert any(literal_prefix.startswith(p) or p.startswith(literal_prefix) for p in prefixes), (
        f"release.yml builds {literal_prefix!r}* but branch-guards.sh archival prefixes are "
        f"{prefixes} — the sweep would treat released changelog branches as abandoned (#16563)."
    )
