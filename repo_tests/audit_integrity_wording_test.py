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
import io
import re
import tokenize

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from autobot_shared.testfile_names import is_test_filename
from tools.lint import _parse_cache as parse_cache
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_CLAIMS = re.compile(r"tamper[- ]?(?:resistant|proof)|immutable|append[- ]only", re.IGNORECASE)
#: The mechanism that makes a whole sentence honest.
_NAMES_MECHANISM = re.compile(
    r"hash[- ]chain|audit_chain|chain_seq|row_mac|\bHMAC\b|tamper-evident|by convention|"
    r"\b(?:called|call|calls|claimed|claims)\W+(?:it\W+)?(?:as\W+)?(?:tamper|immutable|append)",
    re.IGNORECASE,
)
#: A denial applies to the one claim it directly precedes, not to the rest of the sentence.
_NEGATOR = r"\b(?:not|never|no|nor|without|isn't|doesn't|cannot)\b\W+"
#: Only words that qualify the claim sit between the negation and the claim ("not strictly immutable"); a verb
#: ("do not alter immutable rows") makes the claim a premise, not a denial.
_QUALIFIERS = r"(?:(?:be|been|is|are|was|were|a|an|the|truly|really|fully|strictly|actually|yet|provide|provides|offer|offers|guarantee|guarantees)\W+){0,3}$"
_DENIES = re.compile(_NEGATOR + _QUALIFIERS, re.IGNORECASE)
_CLAUSE_BREAK = re.compile(r"[,;]|\b(?:but|and|or|yet|however|while|although)\b", re.IGNORECASE)
_ROOTS = ("autobot-backend", "autobot-slm-backend", "autobot_shared")
_AUDIT_PATH = re.compile(r"(?:^|/)(?:services/audit/|[^/]*audit[^/]*\.py$)")


def _is_audit_module(rel: str) -> bool:
    if is_test_filename(rel) or "/tests/" in rel or "/migrations/" in rel:
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
    floor=46,  # #19676: pinned while the declaration is new; drops once it has a base to compare to
)


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.;:])\s+|\n\s*\n", text) if s.strip()]


def _comments(source: str) -> list[str]:
    """Comment text only: a ``#`` inside a string literal is runtime data, not a comment.

    Consecutive full-line comments are one text, so a sentence wrapped over lines stays whole.
    """
    blocks: list[tuple[int, str]] = []
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type != tokenize.COMMENT:
            continue
        row, text = tok.start[0], tok.string.lstrip("#")
        if not tok.line[: tok.start[1]].strip() and blocks and blocks[-1][0] == row - 1:
            blocks[-1] = (row, blocks[-1][1] + "\n" + text)
        else:
            blocks.append((row, text))
    return [text for _, text in blocks]


def _is_dishonest(sentence: str) -> bool:
    """A claim is honest when the sentence names a mechanism or a denial directly precedes that claim."""
    if _NAMES_MECHANISM.search(sentence):
        return False
    start = 0
    for claim in _CLAIMS.finditer(sentence):
        before = _CLAUSE_BREAK.split(sentence[start : claim.start()])[-1]
        if not _DENIES.search(before):
            return True
        start = claim.end()
    return False


def dishonest_claims(source: str) -> list[str]:
    """Sentences of *source*'s docstrings and comments that claim an integrity property and name no mechanism."""
    scopes = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    texts = [ast.get_docstring(n) or "" for n in ast.walk(parse_cache.parse(source)) if isinstance(n, scopes)]
    texts += _comments(source)
    return [s.strip() for t in texts for s in _sentences(t) if _CLAIMS.search(s) and _is_dishonest(s)]


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        ("bare claim in a docstring", '"""Immutable audit trail."""\n', 1),
        ("claim naming the chain", '"""Tamper-evident via the hash chain, not immutable."""\n', 0),
        ("a denial", '"""This used to be called tamper-resistant; it is not."""\n', 0),
        ("a documented-as claim", '"""This table is documented as immutable."""\n', 1),
        ("a bare claim after a negation elsewhere", '"""Rows are not deleted. The table is immutable."""\n', 1),
        ("claim in a comment", "x = 1  # append-only table\n", 1),
        ("claim in a string literal that holds a hash", 'message = "# immutable"\n', 0),
        ("a claim wrapped over comment lines", "# Append-only via the\n# hash chain.\nx = 1\n", 0),
        ("unrelated comment blocks stay apart", "# Append-only\nx = 1\n# via the hash chain.\n", 1),
        ("a denial for one claim, a bare second claim", '"""This table is not append-only but is immutable."""\n', 1),
        ("a denial covering both claims", '"""This table is not append-only nor immutable."""\n', 0),
        ("a prohibition asserts the property", '"""Do not alter immutable audit rows."""\n', 1),
        ("a qualified denial", '"""These rows are not strictly immutable."""\n', 0),
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


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("autobot-backend/services/audit/store.py", True),
        ("autobot_shared/audit_chain.py", True),
        ("autobot-backend/services/audit_logger.py", True),
        ("autobot-backend/services/audit/store_test.py", False),
        ("autobot-backend/services/audit/test_store.py", False),
        ("autobot-backend/tests/audit_x.py", False),
        ("autobot-backend/migrations/versions/20261122_122_audit_chain.py", False),
        ("autobot-backend/services/billing.py", False),
        ("autobot-backend/services/audit/notes.md", False),
    ],
)
def test_the_audit_module_selector_accepts_audit_sources_and_rejects_the_rest(path: str, expected: bool) -> None:
    assert _is_audit_module(path) is expected
