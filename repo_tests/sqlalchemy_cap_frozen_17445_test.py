# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""SQLAlchemy's `<2.1` cap must survive an automated bump in all four manifests (#17445).

SQLAlchemy 2.1.0 kills 27 tests inside SQLAlchemy's own cache-key machinery --
`TypeError: 'InternalTraversal' object is not callable`, raised in
`sql/_cache_key_cy.py` with no project frame in the failing call. The cap is a
**deferral**, recorded on #17445: do not raise the bound without running the
suites against 2.1.x first.

**Four places hold it (#18148)**, each with its own dependabot block:

| manifest | dependabot directory | shape |
|---|---|---|
| `autobot-backend/requirements.txt` | `/autobot-backend` | `<2.1` upper bound |
| `autobot-slm-backend/requirements.txt` | `/autobot-slm-backend` | `<2.1` upper bound |
| `autobot-infrastructure/shared/docker/ai-stack/requirements-ai.txt` | the ai-stack directory | `<2.1` upper bound |
| `requirements-ci/storage.txt` | `/` | exact `==2.0.x` |

**A comment did not hold it.** #17706 proposed `sqlalchemy>=2.1.0,<2.2` and left
the explanatory paragraph in place directly above the line it contradicted. The
existing `update-types: ["version-update:semver-major"]` ignore did not stop it
either, because 2.0 -> 2.1 is a **minor** -- the same shape as openai (#14431) and
protobuf (#14727), where a grouped `all-dependencies` bump walked past
`update-types`. So each row asserts the pin itself AND a `versions` range in the
matching dependabot block that a grouped bump cannot route around.

Requirements are parsed with `packaging` (Requirement/SpecifierSet);
`dependabot.yml` with yaml.

**What this cannot assert:** that dependabot's next run does not propose it
anyway. That is observable only in the run. A test over config shape is evidence
about the config, not about the bot's behaviour, and must not be read as the
second thing.
"""

from __future__ import annotations

import re

import pytest

yaml = pytest.importorskip("yaml")
packaging_requirements = pytest.importorskip("packaging.requirements")

from repo_tests._paths import repo_root  # noqa: E402

_CONFIG = repo_root() / ".github" / "dependabot.yml"
_CEILING = "2.1"
_PROBES = ("2.1.0", "2.1.1", "2.1.9")  # any 2.1.x the pin admits is a failure

# (manifest, dependabot directory, shape)
_ROWS = [
    ("autobot-backend/requirements.txt", "/autobot-backend", "upper-bound"),
    ("autobot-slm-backend/requirements.txt", "/autobot-slm-backend", "upper-bound"),
    (
        "autobot-infrastructure/shared/docker/ai-stack/requirements-ai.txt",
        "/autobot-infrastructure/shared/docker/ai-stack",
        "upper-bound",
    ),
    ("requirements-ci/storage.txt", "/", "exact"),
]
_IDS = [row[0] for row in _ROWS]


def _sqlalchemy_requirement(text: str):
    """The single sqlalchemy Requirement in *text*, parsed by packaging."""
    found = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        req = packaging_requirements.Requirement(line)
        if req.name.lower() == "sqlalchemy":
            found.append(req)
    assert len(found) == 1, f"expected exactly one sqlalchemy requirement, found {len(found)}"
    return found[0]


def _admitted_21x(text: str) -> list[str]:
    """The 2.1.x probe versions the manifest's sqlalchemy requirement admits."""
    spec = _sqlalchemy_requirement(text).specifier
    return [v for v in _PROBES if spec.contains(v, prereleases=True)]


def _shape_ok(text: str, shape: str) -> bool:
    spec = _sqlalchemy_requirement(text).specifier
    if shape == "exact":
        return any(s.operator == "==" and s.version.startswith("2.0.") for s in spec)
    return any(s.operator == "<" and s.version == _CEILING for s in spec)


def _pip_block(document: dict, directory: str) -> dict:
    blocks = [u for u in document["updates"] if u.get("package-ecosystem") == "pip" and u.get("directory") == directory]
    assert len(blocks) == 1, f"expected exactly one pip block for {directory}, found {len(blocks)}"
    return blocks[0]


def _sqlalchemy_ignore(document: dict, directory: str) -> dict:
    entries = [i for i in _pip_block(document, directory).get("ignore", []) if i.get("dependency-name") == "sqlalchemy"]
    assert entries, (
        f"no dependabot ignore entry for sqlalchemy in the {directory} block. "
        "Without it a grouped all-dependencies bump re-proposes the cap raise every week (#17706)."
    )
    assert len(entries) == 1, f"{len(entries)} sqlalchemy ignore entries; one of them is dead config"
    return entries[0]


def _excludes_the_ceiling(versions: list[str]) -> bool:
    """True when *versions* bars everything at or above the ceiling."""
    for spec in versions:
        match = re.fullmatch(r"\s*>=\s*([0-9][0-9.]*)\s*", spec)
        if match and _le(match.group(1), _CEILING):
            return True
    return False


def _le(left: str, right: str) -> bool:
    """Numeric version comparison, zero-padded to equal length.

    Padding is the whole point: bare tuple comparison makes `(2, 1, 0) <= (2, 1)`
    False, because a prefix sorts first. That read `>=2.1.0` as NOT barring 2.1 --
    caught by this module's own contrast pair rather than in review.
    """

    def parts(v: str) -> list[int]:
        return [int(p) for p in v.split(".") if p.isdigit()]

    a, b = parts(left), parts(right)
    width = max(len(a), len(b))
    a += [0] * (width - len(a))
    b += [0] * (width - len(b))
    return a <= b


def _ignore_problem(document: dict, directory: str) -> str | None:
    """Why the dependabot block fails to bar 2.1, or None when it holds."""
    try:
        versions = _sqlalchemy_ignore(document, directory).get("versions") or []
    except AssertionError as exc:
        return str(exc)
    if not versions:
        return (
            "the sqlalchemy ignore has no `versions` range. `update-types: semver-major` alone "
            "does NOT stop a grouped all-dependencies bump, and 2.0 -> 2.1 is a MINOR anyway (#17706)."
        )
    if not _excludes_the_ceiling(versions):
        return f"the ignore range {versions} does not bar >= {_CEILING}, so a 2.1 bump can still be proposed"
    if any(re.fullmatch(r"\s*>=\s*0[.0]*\s*", v) or v.strip() in {"*", ">=0"} for v in versions):
        return f"the range {versions} bars everything, including 2.0.x security patches"
    return None


def _document() -> dict:
    return yaml.safe_load(_CONFIG.read_text(encoding="utf-8"))


@pytest.mark.parametrize(("manifest", "directory", "shape"), _ROWS, ids=_IDS)
def test_the_manifest_admits_no_21x(manifest: str, directory: str, shape: str) -> None:
    text = (repo_root() / manifest).read_text(encoding="utf-8")
    assert not _admitted_21x(text), (
        f"{manifest} admits SQLAlchemy {_admitted_21x(text)}. 2.1.x kills 27 tests (#17445); "
        "raising the bound is #17445's work, not a dependency bump's."
    )
    assert _shape_ok(text, shape), f"{manifest} no longer has the expected `{shape}` constraint shape"


@pytest.mark.parametrize(("manifest", "directory", "shape"), _ROWS, ids=_IDS)
def test_the_manifest_tells_the_reader_why(manifest: str, directory: str, shape: str) -> None:
    """A bare `<2.1` invites deletion by the next person who sees it as stale."""
    assert "#17445" in (repo_root() / manifest).read_text(
        encoding="utf-8"
    ), f"{manifest} does not cite the issue that records why the cap exists"


@pytest.mark.parametrize(("manifest", "directory", "shape"), _ROWS, ids=_IDS)
def test_dependabot_bars_the_minor_not_merely_the_major(manifest: str, directory: str, shape: str) -> None:
    problem = _ignore_problem(_document(), directory)
    assert problem is None, f"{directory}: {problem}"


# --- contrast pairs: a check that always passed would pass the tests above ---

_GOOD_IGNORE = {
    "updates": [
        {
            "package-ecosystem": "pip",
            "directory": "/x",
            "ignore": [{"dependency-name": "sqlalchemy", "versions": [">=2.1"]}],
        }
    ]
}
_MAJOR_ONLY = {
    "updates": [
        {
            "package-ecosystem": "pip",
            "directory": "/x",
            "ignore": [{"dependency-name": "sqlalchemy", "update-types": ["version-update:semver-major"]}],
        }
    ]
}
_NO_ENTRY = {"updates": [{"package-ecosystem": "pip", "directory": "/x", "ignore": []}]}


@pytest.mark.parametrize(
    ("text", "shape", "admits", "shape_ok"),
    [
        ("sqlalchemy>=2.0.54,<2.1\n", "upper-bound", False, True),  # real shape
        ("SQLAlchemy[asyncio]>=2.0.54,<2.1  # why\n", "upper-bound", False, True),
        ("sqlalchemy==2.0.54\n", "exact", False, True),  # real shape (storage.txt)
        ("sqlalchemy>=2.1.0,<2.2\n", "upper-bound", True, False),  # the #17706 bump
        ("sqlalchemy>=2.0.54\n", "upper-bound", True, False),  # cap deleted
        ("sqlalchemy==2.1.0\n", "exact", True, False),
    ],
)
def test_the_manifest_check_itself(text: str, shape: str, admits: bool, shape_ok: bool) -> None:
    assert bool(_admitted_21x(text)) is admits
    assert _shape_ok(text, shape) is shape_ok


@pytest.mark.parametrize(
    ("document", "holds"),
    [(_GOOD_IGNORE, True), (_MAJOR_ONLY, False), (_NO_ENTRY, False)],
    ids=["versions-range", "semver-major-only (#17706)", "no-entry"],
)
def test_the_ignore_check_itself(document: dict, holds: bool) -> None:
    assert (_ignore_problem(document, "/x") is None) is holds


@pytest.mark.parametrize(
    ("versions", "expected"),
    [
        ([">=2.1"], True),
        ([">=2.1.0"], True),
        ([">=2.0"], True),  # stricter than needed, still bars 2.1
        ([">=2.2"], False),  # lets 2.1 through -- the bug this guards
        ([">=3.0.0"], False),
        ([], False),
    ],
)
def test_the_range_check_itself(versions: list[str], expected: bool) -> None:
    assert _excludes_the_ceiling(versions) is expected
