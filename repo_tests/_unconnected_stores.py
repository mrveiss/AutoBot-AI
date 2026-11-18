# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Queues and stores that are written and never read (#20512).

Two shapes, both of which the #20234 instance (``file_cleanup_queue``: rows scheduled for
deletion, nothing ever claims them) exemplifies:

* **SQL tables**: ``CREATE TABLE <name>`` in a tracked ``.sql`` or production ``.py`` file whose
  name no production code reads or writes. A consumer is a ``FROM``/``JOIN``/``INTO``/``UPDATE``
  clause naming the table in production code that is not DDL: not a ``.sql`` file, not under
  ``migrations/`` or ``schemas/``. A trigger inside the schema that inserts rows is DDL, which is
  how ``file_cleanup_queue`` is filled yet unread.
* **Redis lists and streams**: a key pushed with ``lpush``/``rpush``/``xadd`` for which no
  ``lrange``/``lpop``/``rpop``/``blpop``/``brpop``/``lmove``/``lindex``/``xread``/
  ``xreadgroup``/``xrange``/``xrevrange`` call names the same key anywhere in production code.
  A key is the string literal passed, the literal prefix of an f-string (before the first
  ``{``), or the value of a ``NAME = "..."`` constant the argument names.

WHAT THIS CANNOT SEE
--------------------
* **A key built at runtime** (a local variable, a function result, concatenation): it resolves to
  nothing and is not reported. ``unresolved_keys`` counts them so the blind share is a number.
* **Redis types other than list/stream**: sets, sorted sets, hashes and plain keys are not
  queues in this sense and are out of scope; so is pub/sub (a publish with no subscriber is not
  stored).
* **A consumer by key prefix scan** (``scan_iter("history:*")`` then read): the key is read, but
  not by a call naming it, so it is reported. It belongs in the baseline or gains a named read.
* **ORM-mapped tables** (``__tablename__ =`` or ``Table("name"``) are counted as read: the model's
  users are the module detector's business. Tables created by Ansible/SQL outside the
  tracked ``.sql``/``.py`` set.
* **A consumer that is dead**: a read inside a function nothing calls counts as a read.
* Two producers sharing one key name are one key; a consumer of either connects both.
"""

from __future__ import annotations

import re

from repo_tests._unconnected_common import Tree, is_production

_TABLE_RE = re.compile(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[\"`]?(\w+)[\"`]?\s*\(", re.IGNORECASE)
_ORM_RE = re.compile(r"(?:__tablename__\s*=|\bTable\(\s*)\s*[\"'](\w+)[\"']")
#: Tables a framework reads on its own; no application code names them.
_FRAMEWORK_TABLES = frozenset({"alembic_version"})
_DDL_DIRS = ("migrations", "schemas")
#: Trees whose queues and tables are judged. Readers are looked for in every production file.
STORE_ROOTS = ("autobot-backend", "autobot-slm-backend", "autobot_shared", "autobot-infrastructure")
_STORE_PREFIXES = tuple(f"{r}/" for r in STORE_ROOTS)
#: A file that can hold a query at all; the clause scan is the costly one, so it runs only on these.
_SQL_WORDS = ("SELECT", "INSERT", "UPDATE", "DELETE", "select ", "insert into")

_PUSH = r"lpush|rpush|xadd"
_READ = r"lrange|lpop|rpop|blpop|brpop|lmove|blmove|brpoplpush|lindex|xread|xreadgroup|xrange|xrevrange"
_CALL = r"\.(?:{ops})\(\s*(?P<arg>f?[\"'][^\"'\n]*[\"']|[\w.]+)"
_PUSH_RE = re.compile(_CALL.format(ops=_PUSH))
_READ_RE = re.compile(_CALL.format(ops=_READ))
_CONST_RE = re.compile(r"^[ \t]*(\w+)\s*(?::[^=\n]+)?=\s*f?[\"']([^\"'\n]+)[\"']", re.MULTILINE)
_QUEUE_OPS = (".lpush(", ".rpush(", ".xadd(")
_SQL_SUFFIXES = (".py", ".sh", ".j2")


def _is_ddl_file(rel: str) -> bool:
    return rel.endswith(".sql") or any(d in rel.split("/")[:-1] for d in _DDL_DIRS)


def tables(tree: Tree) -> dict[str, str]:
    """``{table name: defining file}`` for every ``CREATE TABLE`` in a tracked ``.sql`` or production ``.py`` file."""
    found: dict[str, str] = {}
    for rel in tree.select(".sql", ".py", production=False):
        if not rel.startswith(_STORE_PREFIXES) or (rel.endswith(".py") and not is_production(rel)):
            continue
        text = tree.text(rel)
        if "CREATE" in text or "create table" in text:
            for name in _TABLE_RE.findall(text):
                found.setdefault(name.lower(), rel)
    return found


def unread_tables(tree: Tree) -> list[str]:
    """Defined table names that no production non-DDL file reads, writes or maps to an ORM model."""
    defined = tables(tree)
    if not defined:
        return []
    clause = re.compile(
        r"\b(?:FROM|JOIN|INTO|UPDATE)\s+[\"`]?(%s)\b" % "|".join(map(re.escape, sorted(defined))), re.IGNORECASE
    )
    used: set[str] = set()
    for rel in tree.select(*_SQL_SUFFIXES):
        text = tree.text(rel)
        if _is_ddl_file(rel):
            continue
        if "__tablename__" in text or "Table(" in text:
            used.update(m.lower() for m in _ORM_RE.findall(text))
        if any(word in text for word in _SQL_WORDS):
            used.update(m.lower() for m in clause.findall(text))
    return sorted(name for name in defined if name not in used and name not in _FRAMEWORK_TABLES)


def _key(arg: str, constants: dict[str, str]) -> str | None:
    if arg[0] in "\"'" or arg[:2] in ('f"', "f'"):
        return arg.lstrip("f")[1:-1].split("{")[0] or None
    return (constants.get(arg.rsplit(".", 1)[-1]) or "").split("{")[0] or None


def _file_constants(tree: Tree, rel: str, cache: dict[str, dict[str, str]]) -> dict[str, str]:
    """The ``NAME = "..."`` constants of one file, read once and only when one of its calls needs them."""
    if rel not in cache:
        cache[rel] = dict(_CONST_RE.findall(tree.text(rel)))
    return cache[rel]


def queue_keys(tree: Tree) -> tuple[dict[str, str], set[str], int]:
    """``({pushed key: first producing file}, read keys, producer calls whose key is not resolvable)``.

    A constant is resolved from the file that makes the call. A key held in another module's
    constant (or any variable) is unresolvable, and counted in the third value.
    """
    cache: dict[str, dict[str, str]] = {}
    pushed: dict[str, str] = {}
    read: set[str] = set()
    unresolved = 0
    for rel in tree.select(".py"):
        text = tree.text(rel)
        judged = rel.startswith(_STORE_PREFIXES) and any(op in text for op in _QUEUE_OPS)
        pushes = _PUSH_RE.finditer(text) if judged else ()
        for kind, matches in ((True, pushes), (False, _READ_RE.finditer(text))):
            for m in matches:
                arg = m.group("arg")
                quoted = arg[0] in "\"'" or arg[:2] in ('f"', "f'")
                key = _key(arg, {} if quoted else _file_constants(tree, rel, cache))
                if key is None:
                    unresolved += kind
                elif kind:
                    pushed.setdefault(key, rel)
                else:
                    read.add(key)
    return pushed, read, unresolved


def unread_queues(tree: Tree) -> list[str]:
    """Keys pushed in production code whose key no read call names, as ``"<file>:<key>"``."""
    pushed, read, _ = queue_keys(tree)
    return sorted(f"{rel}:{key}" for key, rel in pushed.items() if key not in read)


def store_files(tree: Tree) -> list[str]:
    """The files this detector judges: those pushing to a queue and those defining a table."""
    pushing = [rel for rel in tree.select(".py", under=STORE_ROOTS) if any(op in tree.text(rel) for op in _QUEUE_OPS)]
    return sorted({*pushing, *tables(tree).values()})
