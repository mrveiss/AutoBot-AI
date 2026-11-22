# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An audit module claims no integrity property it does not provide (#17219).

"Tamper-resistant", "tamper-proof", "immutable" and "append-only" are claims an auditor tests.
In an audit module's docstring or comment they are allowed only where the sentence names the
mechanism that provides the property or says the property is NOT provided. A module that says
"immutable" about a table whose rows a foreign key updates is a credibility failure inside our
own source (#17219).
"""

import ast
import re

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_CLAIMS = re.compile(r"tamper[- ]?(?:resistant|proof)|immutable|append[- ]only", re.IGNORECASE)
#: The mechanism, or the denial, that makes a sentence containing a claim honest.
_NAMES_MECHANISM = re.compile(
    r"hash[- ]chain|audit_chain|chain_seq|row_mac|\bHMAC\b|tamper-evident|by convention|"
    r"\b(?:not|never|no|nor|without|isn't|doesn't|cannot)\b\W+(?:\w+\W+){0,3}?"
    r"(?:tamper[- ]?(?:resistant|proof)|immutable|append[- ]only)|"
    r"\b(?:called|call|calls|claimed|claims)\W+(?:it\W+)?(?:as\W+)?(?:tamper|immutable|append)",
    re.IGNORECASE,
)
_ROOTS = ("autobot-backend", "autobot-slm-backend", "autobot_shared")
_AUDIT_PATH = re.compile(r"(?:^|/)(?:services/audit/|[^/]*audit[^/]*\.py$)")


def _is_audit_module(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    if name.endswith("_test.py") or name.startswith("test_") or "/tests/" in rel or "/migrations/" in rel:
        return False
    return rel.endswith(".py") and bool(_AUDIT_PATH.search(rel))


def _population(root) -> list[str]:
    try:
        return [rel for rel in tracked_paths(root, *_ROOTS) if _is_audit_module(rel)]
    except EmptyEnumeration:
        return []


REACH = declare(
    "audit-integrity-wording",
    discover=_population,
    what="audit modules (path names audit)",
    roots=_ROOTS,
    floor=45,  # #19676: pinned while the declaration is new; drops once it has a base to compare to
)


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.;:])\s+|\n\s*\n", text) if s.strip()]


def dishonest_claims(source: str) -> list[str]:
    """Sentences of *source*'s docstrings and comments that claim an integrity property and name no mechanism."""
    scopes = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    texts = [ast.get_docstring(n) or "" for n in ast.walk(ast.parse(source)) if isinstance(n, scopes)]
    texts += [line.split("#", 1)[1] for line in source.splitlines() if "#" in line]
    return [s.strip() for t in texts for s in _sentences(t) if _CLAIMS.search(s) and not _NAMES_MECHANISM.search(s)]


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        ("bare claim in a docstring", '"""Immutable audit trail."""\n', 1),
        ("claim naming the chain", '"""Tamper-evident via the hash chain, not immutable."""\n', 0),
        ("a denial", '"""This used to be called tamper-resistant; it is not."""\n', 0),
        ("a documented-as claim", '"""This table is documented as immutable."""\n', 1),
        ("a bare claim after a negation elsewhere", '"""Rows are not deleted. The table is immutable."""\n', 1),
        ("claim in a comment", "x = 1  # append-only table\n", 1),
        ("no claim", '"""Audit rows are sealed on insert."""\n', 0),
    ],
)
def test_the_wording_matcher_tells_a_claim_from_a_denial(label: str, source: str, expected: int) -> None:
    assert len(dishonest_claims(source)) == expected, label


def test_no_audit_module_claims_an_integrity_property_it_lacks() -> None:
    root = repo_root()
    found = {
        rel: claims
        for rel in REACH.examined(root)
        if (claims := dishonest_claims((root / rel).read_text(encoding="utf-8")))
    }
    assert not found, (
        f"#17219: {found} claim tamper-resistance/immutability with no mechanism named. Name the mechanism "
        "(autobot_shared/audit_chain.py) or say what is NOT provided."
    )
