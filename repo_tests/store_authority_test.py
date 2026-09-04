# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every persisted concept names the store that is authoritative for it (#15663).

The same datum lives in Redis, Postgres and ChromaDB, each write path picked a
store on its own, and nothing said which one wins when they disagree. #12733 is
what that costs: ``facts/by_category`` went 43 -> 0 while 22 ChromaDB vectors
survived, because Redis was the only durable home a fact had and no rule said it
shouldn't be.

``autobot_shared/store_authority.py`` is the rule. These tests are the half that
stops it eroding, and the last one is the important one: it fails when a module
starts writing the same concept into a *second* store without declaring which
copy is authoritative -- which is how every existing dual-store module arrived.

Why "writes two stores" is the trigger
--------------------------------------
A module that writes one store cannot disagree with itself, so it needs no
declaration. A module that durably writes two has, by construction, a second
copy of something, and the only question worth asking is which one wins. That
question is exactly what the table answers, so the detector and the table share
a definition rather than approximating one another.

Both call shapes count. ``knowledge/facts.py`` -- the module #12733 is about --
never calls a Redis method directly: every one of its writes is
``asyncio.to_thread(self.redis_client.hset, ...)``, a bare attribute reference
handed to a thread. A first version of this detector read only ``ast.Call`` and
reported 24 dual-store modules, silently omitting the one the issue was filed
for.
"""

from __future__ import annotations

import ast
import subprocess  # nosec B404  # fixed argv, no shell, no caller input
from pathlib import Path

from autobot_shared.paths import scrubbed_git_env
from autobot_shared.store_authority import STORE_AUTHORITY, Store, system_of_record

REPO_ROOT = Path(__file__).resolve().parents[1]

#: The table itself, which is the one module allowed to name every store.
_CANONICAL = Path("autobot_shared/store_authority.py")

#: Modules that durably write two stores and have not yet said which one wins.
#: Shrink-only: an entry leaves when the concept is declared, and nothing may be
#: added -- a new dual-store module is the regression this file exists to catch.
_BASELINE = Path(__file__).parent / "store_authority_baseline.txt"

#: The baseline holds this many entries and may only shrink. Pinned as a COUNT,
#: not only as a set, because the set comparison cannot catch a two-sided
#: addition: a change that adds an undeclared dual-store module AND its own
#: baseline line passes every other assertion here. That is not hypothetical —
#: `python_file_size_ratchet_test.py` grew this exact ceiling test after a
#: change slipped 509 entries in that way. Lower it when an entry leaves; never
#: raise it to admit a new one.
MAX_BASELINE_ENTRIES = 8


# Methods that put bytes somewhere outliving the process, per store. Paired with
# a receiver test because the names are generic: `add` is ChromaDB's writer, a
# SQLAlchemy session's writer, and half the sets in the standard library.
_WRITES: dict[Store, tuple[frozenset[str], tuple[str, ...]]] = {
    Store.REDIS: (
        frozenset({"hset", "hmset", "set", "setex", "sadd", "rpush", "lpush", "zadd", "xadd", "json_set"}),
        ("redis", "pipe"),
    ),
    Store.CHROMADB: (
        frozenset({"add", "upsert", "add_documents", "insert_nodes"}),
        ("vector_store", "collection", "chroma"),
    ),
    Store.POSTGRES: (frozenset({"add", "add_all", "merge", "bulk_save_objects"}), ("session",)),
    Store.DISK: (frozenset({"write_text", "write_bytes"}), ("path", "file")),
}

# Reach floor, not a census: it measures how far the walk gets, never how much it
# finds. Declaring a concept must never trip it -- only a detector that has
# quietly stopped reading the tree it claims to read.
#
# It counts files that PARSED, not files that git listed. Those are different
# numbers and the difference is the whole point: if ``ast.parse`` began failing
# across the tree, ``stores_written`` would return an empty set from its
# SyntaxError branch for every file, ``dual_store_modules()`` would return {},
# and every assertion below would pass on a tree the detector had stopped
# reading. A floor over ``git ls-files`` would not notice; this one does.
_MIN_MODULES_PARSED = 2000  # 5100+ parse today, well above the current tree


def _receiver(node: ast.expr) -> str:
    """Lower-cased dotted text of the object an attribute hangs off."""
    parts: list[str] = []
    cursor = node
    while isinstance(cursor, ast.Attribute):
        parts.append(cursor.attr)
        cursor = cursor.value
    if isinstance(cursor, ast.Name):
        parts.append(cursor.id)
    elif isinstance(cursor, ast.Call):
        parts.append(_receiver(cursor.func) or "call")
    return ".".join(reversed(parts)).lower()


def _attribute_writes(node: ast.AST) -> tuple[str, str] | None:
    """``(method, receiver)`` for the two shapes a durable write takes."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        return node.func.attr, _receiver(node.func.value)
    if isinstance(node, ast.Attribute):
        return node.attr, _receiver(node.value)
    return None


def stores_written(source: str) -> set[Store]:
    """Every store *source* durably writes to."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    found: set[Store] = set()
    for node in ast.walk(tree):
        shape = _attribute_writes(node)
        if shape is None:
            continue
        method, receiver = shape
        for store, (methods, receivers) in _WRITES.items():
            if method in methods and any(hint in receiver for hint in receivers):
                found.add(store)
    return found


def _tracked_python_files() -> list[Path]:
    result = subprocess.run(  # nosec B603 B607
        ["git", "ls-files", "*.py"], cwd=REPO_ROOT, capture_output=True, text=True, check=False, env=scrubbed_git_env()
    )
    return [REPO_ROOT / line for line in result.stdout.splitlines() if line]


def _is_test(relative: str) -> bool:
    """A test module, by this repo's conventions -- not by "test" appearing anywhere.

    A substring check over the filename exempts production modules that merely
    contain the word: ``env_registry_testing.py``, ``testing_pattern_analyzer.py``
    and fifteen others in this tree. Any of them could write two durable stores
    and never appear in :func:`dual_store_modules`, which is the regression this
    file exists to catch.
    """
    path = Path(relative)
    name = path.name
    return (
        name.startswith("test_")
        or name.endswith("_test.py")
        or name == "conftest.py"
        or "tests" in path.parts
        or path.parts[0] == "repo_tests"
    )


def dual_store_modules() -> dict[str, set[Store]]:
    """``repo-relative path -> the stores it writes`` for every module writing two."""
    found: dict[str, set[Store]] = {}
    for path in _tracked_python_files():
        relative = path.relative_to(REPO_ROOT).as_posix()
        if _is_test(relative) or relative == _CANONICAL.as_posix():
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        stores = stores_written(source)
        if len(stores) >= 2:
            found[relative] = stores
    return found


def _declared_write_sites() -> set[str]:
    return {site for concept in STORE_AUTHORITY.values() for site in concept.write_sites}


def baseline_entries() -> set[str]:
    """Paths only. An inline ``#`` comment carries the tracking issue.

    The file's header promises an issue beside each entry, so the parser has to
    allow one: taking the whole line would bake ``# #15670`` into the path and
    every entry would read as BOTH an undeclared finding and a stale record.
    """
    lines = _BASELINE.read_text(encoding="utf-8").splitlines()
    entries = set()
    for line in lines:
        text = line.split("#", 1)[0].strip() if not line.lstrip().startswith("#") else ""
        if text:
            entries.add(text)
    return entries


def test_the_walk_reaches_the_tree():
    """A detector that stopped parsing files would report a clean tree."""
    parsed = 0
    for path in _tracked_python_files():
        try:
            ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, SyntaxError, ValueError):
            continue
        parsed += 1
    assert parsed >= _MIN_MODULES_PARSED, f"only {parsed} modules parsed; the detector has stopped reading the tree"


def test_the_detector_matches_the_shapes_it_claims_to():
    """Pin ``stores_written`` on known input, in both directions.

    Every other assertion here runs the detector against the live tree, so a
    hint that stopped matching -- ``redis_client`` renamed, a switch to a
    pipeline helper -- would shrink the finding set silently and leave
    ``test_no_undeclared_dual_store_module_exists`` passing on a detector that
    had gone blind. These cases fail instead.
    """
    call_shape = "async def f(self):\n    self.redis_client.hset(k, mapping=m)\n    self.vector_store.add([d])\n"
    assert stores_written(call_shape) == {Store.REDIS, Store.CHROMADB}

    # The shape knowledge/facts.py actually uses: the method is a reference
    # handed to a thread, never a call. Reading only ast.Call misses it.
    thread_shape = (
        "async def f(self):\n"
        "    await asyncio.to_thread(self.redis_client.hset, k, mapping=m)\n"
        "    await asyncio.to_thread(self.vector_store.add, [d])\n"
    )
    assert stores_written(thread_shape) == {Store.REDIS, Store.CHROMADB}

    assert stores_written("def f(session, item):\n    session.add(item)\n") == {Store.POSTGRES}
    assert stores_written("def f(cache_path, text):\n    cache_path.write_text(text)\n") == {Store.DISK}

    # The receiver hint is deliberately narrow, and this is the cost of that:
    # a disk write through a name carrying neither "path" nor "file" is missed.
    # Pinned rather than fixed -- widening it to every ``write_text`` would drag
    # in report writers, log rotation and cache dumps, none of which are a
    # second copy of a persisted concept. A module that writes user state to a
    # variable named ``p`` is a naming problem this guard is the wrong tool for.
    assert stores_written("def f(p, text):\n    p.write_text(text)\n") == set()

    # Negatives: reads are not writes, and a same-named method on an unrelated
    # object is not a store write -- both would inflate the finding set.
    assert stores_written("def f(self):\n    self.redis_client.hgetall(k)\n") == set()
    assert stores_written("def f(seen, item):\n    seen.add(item)\n") == set()
    assert stores_written("def f(x):\n    this is not python\n") == set()


def test_every_declared_write_site_exists():
    """A renamed module must move its declaration, not orphan it."""
    missing = sorted(site for site in _declared_write_sites() if not (REPO_ROOT / site).is_file())
    assert not missing, f"store_authority.py names write sites that do not exist: {missing}"


def test_a_projection_is_never_the_system_of_record():
    """The authority cannot also be one of its own copies."""
    contradictions = [
        concept.name for concept in STORE_AUTHORITY.values() if concept.system_of_record in concept.projections
    ]
    assert not contradictions, f"concepts listing their own system of record as a projection: {contradictions}"


def test_every_concept_says_how_its_copies_are_rebuilt():
    """Rule 2 -- a copy that cannot be reconstructed is a second original."""
    silent = [concept.name for concept in STORE_AUTHORITY.values() if not concept.rebuilt_by.strip()]
    assert not silent, f"concepts with projections but no stated rebuild: {silent}"


def test_a_redis_system_of_record_is_justified():
    """Rule 1's escape hatch, and the condition on it (#15663 criterion 5).

    A genuinely ephemeral datum whose only home is Redis is fine -- it just has
    to say so. An unstated one is indistinguishable from #12733.
    """
    unjustified = [
        concept.name
        for concept in STORE_AUTHORITY.values()
        if concept.system_of_record is Store.REDIS and not concept.note.strip()
    ]
    assert not unjustified, (
        "Redis is declared the system of record with no justification -- state why the datum is "
        f"ephemeral, or give it a durable home (#15663): {unjustified}"
    )


def test_the_table_is_reachable_from_a_write_site():
    """``system_of_record`` is the lookup that makes the table discoverable."""
    assert system_of_record("knowledge_facts").system_of_record is Store.POSTGRES
    try:
        system_of_record("a_concept_nobody_declared")
    except KeyError as exc:
        assert "no declared system of record" in str(exc)
    else:  # pragma: no cover - the raise is the contract
        raise AssertionError("an undeclared concept must not resolve")


def test_knowledge_facts_are_not_redis_with_rdb():
    """#12733's cause, pinned. Redis may hold a fact; it may not own one."""
    facts = STORE_AUTHORITY["knowledge_facts"]
    assert facts.system_of_record is Store.POSTGRES
    assert Store.REDIS in facts.projections
    assert Store.CHROMADB in facts.projections


def test_vectorized_status_is_derived_not_stored():
    """Rule 3, on the case that motivated it (#15663 criterion 3, #12733).

    ``vectorization_status`` / ``vectorized_at`` are a claim about ChromaDB's
    contents written beside the fact in Redis. Both readers of "is this fact
    vectorized" must ask the vector store instead: the status endpoint, so the
    browser stops reporting vectorized facts as unvectorized, and -- the one that
    actually kept the damage alive -- the reconciler, which skipped any fact
    stamped ``completed`` and so could never repair a vector that had gone
    missing underneath one.

    Writing the stamp is still fine; it records an attempt. Deciding from it is
    not, which is why this reads the two deciding functions rather than the file.
    """
    reconciler = (REPO_ROOT / "autobot-backend/background_vectorization.py").read_text(encoding="utf-8")
    deciders = {
        node.name: node
        for node in ast.walk(ast.parse(reconciler))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in {"_get_vectorization_status", "_filter_pending_facts"}
    }
    assert set(deciders) == {
        "_get_vectorization_status",
        "_filter_pending_facts",
    }, "the reconciler's skip decision moved; point this test at the function that makes it now"

    # Naming the Redis field is what reading it requires, so the field name as a
    # string literal in the body is the signal. Docstrings are excluded by
    # construction -- they are the module's own account of why the flag is gone.
    def _names_the_flag(node: ast.AST) -> bool:
        body = node.body[1:] if ast.get_docstring(node) else node.body
        return any(
            isinstance(child, ast.Constant) and child.value == "vectorization_status"
            for statement in body
            for child in ast.walk(statement)
        )

    offenders = sorted(name for name, node in deciders.items() if _names_the_flag(node))
    assert not offenders, (
        "the reconciler decides what to re-embed from a stored flag instead of asking ChromaDB "
        f"(#15663 rule 3): {offenders}"
    )
    called = {
        child.func.id
        for child in ast.walk(deciders["_get_vectorization_status"])
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
    }
    assert "vectorized_ids" in called, "the reconciler must ask the vector store for membership"

    status_api = (REPO_ROOT / "autobot-backend/api/knowledge_vectorization.py").read_text(encoding="utf-8")
    assert (
        "from knowledge.vector_membership import vectorized_ids" in status_api
    ), "the status endpoint and the reconciler must answer 'is it vectorized' the same way"


def test_the_baseline_only_shrinks():
    """A cleared entry must leave the file, so it cannot mask a later regression."""
    stale = sorted(baseline_entries() - set(dual_store_modules()))
    assert not stale, (
        "these modules no longer write two stores; drop them from "
        f"{_BASELINE.name} so it keeps describing the tree: {stale}"
    )


def test_no_undeclared_dual_store_module_exists():
    """The regression that matters: a second copy with nothing saying which wins.

    Every module here writes the same concept into two durable stores. Each
    arrived reasonably -- someone needed the datum in a second place and wrote it
    there -- and nothing told them a rule existed. This does.

    Fixing one is not a matter of deleting a write: name the concept in
    ``autobot_shared/store_authority.py``, say which store is authoritative and
    how the other copy is rebuilt from it, then list the module as a write site.
    """
    offenders = sorted(set(dual_store_modules()) - _declared_write_sites() - baseline_entries())
    assert not offenders, (
        "module durably writes two stores with no declared system of record -- declare the "
        f"concept in {_CANONICAL} (#15663): {offenders}"
    )


def test_the_baseline_count_may_not_grow():
    """Catches the two-sided addition `test_the_baseline_only_shrinks` cannot.

    That test compares live detector output against the baseline and checks each
    entry is still dual-store. Both hold when a change adds a new undeclared
    module and its baseline line together — the module is genuinely dual-store,
    so it is not stale, and it is in the baseline, so it is not a finding. Only
    the count notices.
    """
    count = len(baseline_entries())
    assert count <= MAX_BASELINE_ENTRIES, (
        f"the store-authority baseline grew to {count} entries, over the recorded "
        f"ceiling of {MAX_BASELINE_ENTRIES}. Declare the concept in "
        "autobot_shared/store_authority.py instead — lower this ceiling when an "
        "entry leaves, never raise it to let a new one in."
    )
