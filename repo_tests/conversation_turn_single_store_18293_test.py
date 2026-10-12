# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A conversation turn has one durable home: chat_sessions (#18293).

Every turn used to be written twice -- to chat_sessions and, by independent code,
to ``data/conversation_transcripts/{id}.json`` -- and the two diverged (#13214).
The transcript store is now ``legacy_conversation_transcripts`` in
``autobot_shared/store_authority.py``: read-only, no write sites. Three checks:

1. **One home for the location, resolved once.** The path is an SSOT setting
   (``config.path.legacy_transcripts_dir``, ``AUTOBOT_LEGACY_TRANSCRIPTS_DIR``):
   a path literal naming the directory appears only in ``ssot_config.py``, and the
   setting is read only by ``store_authority.legacy_conversation_transcripts_dir()``.
   Joining a name onto a data root of one's own is how the data-storage view and
   session-delete cleanup came to look under the project root's ``data/``, where
   the writer never wrote; reading the working directory is how a script started
   elsewhere came to read an empty one.
2. **Nothing writes under it.** No function that names the location (the
   constant, the resolver, a ``transcript_dir`` or the literal) also
   makes a file-creating call: ``open`` in a write/append mode, ``write_text``,
   ``write_bytes``, ``json.dump``, ``mkdir``/``makedirs``, ``rename``, ``touch``,
   ``shutil.copy*``/``move``.
3. **The LLM-context cache is written only by a declared site.** A module that
   builds a ``chat:conversation:*`` key and writes Redis is in
   ``chat_sessions.write_sites``.

What this cannot see, stated so an empty result is read correctly: a write in a
helper that receives the path as an argument from a function in another module
(check 2 is per function); a Redis write keyed by a prefix spelled some other
way (check 3 matches ``CHAT_CONVERSATION_PREFIX`` and the ``chat:conversation:``
literal); deletions -- removing a user's own legacy file when they delete the
session is not a write. Only non-test Python under the roots below is read.
"""

from __future__ import annotations

import ast
import functools
import re
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from autobot_shared.store_authority import STORE_AUTHORITY
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_ROOTS = ("autobot-backend", "autobot_shared", "autobot-infrastructure")
_HOME = "autobot_shared/ssot_config.py"
_RESOLVER = "autobot_shared/store_authority.py"
_SETTING = "legacy_transcripts_dir"
_LITERAL = re.compile(r"(^|[/\\])conversation_transcripts($|[/\\])")
_LOCATION_NAMES = frozenset(
    {"legacy_conversation_transcripts_dir", _SETTING, "legacy_transcript_file", "transcript_dir"}
)
_WRITE_CALLS = frozenset(
    {"write_text", "write_bytes", "dump", "mkdir", "makedirs", "rename", "touch", "copy", "copy2", "copyfile", "move"}
)
_CACHE_PREFIX_NAMES = frozenset({"CHAT_CONVERSATION_PREFIX"})
_REDIS_WRITES = frozenset({"set", "setex", "hset", "hmset", "rpush", "lpush", "json_set"})


def _is_source_python(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return rel.endswith(".py") and not (name.endswith("_test.py") or name.startswith("test_") or "/tests/" in rel)


def _source_population(root: Path) -> list[str]:
    try:
        tracked = tracked_paths(root, *_ROOTS)
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if _is_source_python(rel)]


def _all_python(root: Path) -> int:
    """Every tracked ``.py`` under the roots, tests included -- the reference population."""
    try:
        return sum(1 for rel in tracked_paths(root, *_ROOTS) if rel.endswith(".py"))
    except EmptyEnumeration:
        return 0


#: Measured 2026-10-11: 2,917 non-test files of 5,112 tracked ``.py`` under the
#: roots -- 57.1%. 0.50 leaves the band a shift of source into tests could take
#: before the sweep is meaningfully narrower; a fraction scales where a count
#: would go stale with the tree.
REACH = declare(
    "conversation-turn-single-store",
    discover=_source_population,
    reference=_all_python,
    min_fraction=0.50,
    what="non-test python source",
    roots=_ROOTS,
)


def _docstring_ids(tree: ast.AST) -> set[int]:
    owners = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    return {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, owners) and node.body and isinstance(node.body[0], ast.Expr)
    }


def path_literals(source: str) -> list[int]:
    """Lines of string constants naming the location as a path component (docstrings excluded)."""
    tree = ast.parse(source)
    skip = _docstring_ids(tree)
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in skip
        and _LITERAL.search(node.value)
    ]


def setting_reads(source: str) -> list[int]:
    """Lines reading the SSOT location setting -- ``<anything>.legacy_transcripts_dir``."""
    return [n.lineno for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Attribute) and n.attr == _SETTING]


def _called_name(call: ast.Call) -> str:
    func = call.func
    return func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ""


def _opens_for_writing(call: ast.Call) -> bool:
    if _called_name(call) != "open":
        return False
    modes = [kw.value for kw in call.keywords if kw.arg == "mode"] + call.args[1:2]
    return any(isinstance(m, ast.Constant) and isinstance(m.value, str) and set(m.value) & set("wax+") for m in modes)


def _names_location(node: ast.AST) -> bool:
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and sub.id in _LOCATION_NAMES:
            return True
        if isinstance(sub, ast.Attribute) and sub.attr in _LOCATION_NAMES:
            return True
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str) and _LITERAL.search(sub.value):
            return True
    return False


def _is_write(node: ast.AST) -> bool:
    """A file-creating method referenced (called or handed to ``to_thread``), or a bare call/open."""
    if isinstance(node, ast.Attribute):
        return node.attr in _WRITE_CALLS
    if isinstance(node, ast.Call):
        return (isinstance(node.func, ast.Name) and node.func.id in _WRITE_CALLS) or _opens_for_writing(node)
    return False


def transcript_writes(source: str) -> list[str]:
    """``function:line`` of every file-creating call in a function that names the location."""
    found = []
    for fn in ast.walk(ast.parse(source)):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) or not _names_location(fn):
            continue
        found.extend(f"{fn.name}:{node.lineno}" for node in ast.walk(fn) if _is_write(node))
    return found


def writes_llm_context_cache(source: str) -> bool:
    """True when *source* builds a ``chat:conversation:*`` key AND writes Redis."""
    tree = ast.parse(source)
    names_prefix = any(
        (isinstance(n, ast.Attribute) and n.attr in _CACHE_PREFIX_NAMES)
        or (isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.startswith("chat:conversation:"))
        for n in ast.walk(tree)
    )
    return names_prefix and any(
        isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr in _REDIS_WRITES
        and "redis" in ast.unparse(n.func.value).lower()
        for n in ast.walk(tree)
    )


@functools.lru_cache(maxsize=1)
def _population() -> dict[str, str]:
    root = repo_root()
    return {rel: (root / rel).read_text(encoding="utf-8") for rel in REACH.examined(root)}


_RETIRED_WRITER = """
class Mixin:
    async def _append_to_transcript(self, session_id, user, assistant):
        transcript_dir = Path(self.transcript_dir)
        await asyncio.to_thread(transcript_dir.mkdir, parents=True, exist_ok=True)
        async with aiofiles.open(transcript_dir / f"{session_id}.json", "w", encoding="utf-8") as f:
            await f.write(payload)
"""
_LEGACY_READER = """
async def read(session_id, transcript_dir=None):
    transcript_dir = transcript_dir or legacy_conversation_transcripts_dir()
    async with aiofiles.open(Path(transcript_dir) / f"{session_id}.json", "r", encoding="utf-8") as f:
        return await f.read()
"""


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        ("the retired transcript writer", _RETIRED_WRITER, ["_append_to_transcript:5", "_append_to_transcript:6"]),
        ("the read-only legacy reader", _LEGACY_READER, []),
        ("a write that never names the location", "def f(p):\n    p.write_text('x')\n", []),
        (
            "a literal path with json.dump",
            "def f(d):\n    json.dump(d, open('data/conversation_transcripts/x', 'a'))\n",
            ["f:2", "f:2"],
        ),
        ("a deletion", "def f(s):\n    os.remove(legacy_conversation_transcripts_dir() / s)\n", []),
    ],
)
def test_the_detector_tells_a_write_from_a_read(label: str, source: str, expected: list[str]) -> None:
    assert sorted(transcript_writes(source)) == sorted(expected), label


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("X = 'data/conversation_transcripts'\n", [1]),
        ("X = Path('data') / 'conversation_transcripts'\n", [1]),
        ('"""Reads data/conversation_transcripts."""\n', []),
        ("X = 'legacy_conversation_transcripts'\n", []),
    ],
)
def test_the_literal_matcher_sees_paths_not_prose(source: str, expected: list[int]) -> None:
    assert path_literals(source) == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("d = config.path.resolve(config.path.legacy_transcripts_dir)\n", [1]),
        ("d = Path.cwd() / 'data' / x\n", []),
        ("d = legacy_conversation_transcripts_dir()\n", []),
    ],
)
def test_the_setting_matcher_sees_a_read(source: str, expected: list[int]) -> None:
    assert setting_reads(source) == expected


def test_the_cache_matcher_needs_the_key_and_a_redis_write() -> None:
    writer = "k = f'{REDIS_KEY.CHAT_CONVERSATION_PREFIX}{s}'\nawait self.redis_client.set(k, v)\n"
    assert writes_llm_context_cache(writer)
    assert not writes_llm_context_cache("k = REDIS_KEY.CHAT_CONVERSATION_PREFIX\nawait redis.delete(k)\n")
    assert not writes_llm_context_cache("await self.redis_client.set('chat:session:x', v)\n")


def test_the_scan_is_not_vacuous() -> None:
    population = _population()
    assert "autobot-backend/chat_workflow/conversation.py" in population
    assert "autobot-backend/chat_history/legacy_transcripts.py" in population


def test_the_location_has_one_home() -> None:
    candidates = {rel: src for rel, src in _population().items() if "conversation_transcripts" in src}
    homes = {rel: lines for rel, src in candidates.items() if (lines := path_literals(src))}
    assert set(homes) == {_HOME}, (
        f"#18293: the legacy transcript location is spelled as a path outside {_HOME}: {homes}. "
        "Call legacy_conversation_transcripts_dir() instead."
    )


def test_the_location_is_resolved_in_one_place() -> None:
    candidates = {rel: src for rel, src in _population().items() if _SETTING in src}
    readers = {rel: lines for rel, src in candidates.items() if (lines := setting_reads(src))}
    assert set(readers) == {_RESOLVER}, (
        f"#18293: {readers} read the legacy transcript setting directly. Call "
        "legacy_conversation_transcripts_dir(): the one resolution of where the retired writer wrote."
    )


def test_nothing_writes_under_the_legacy_transcript_location() -> None:
    candidates = {rel: src for rel, src in _population().items() if any(n in src for n in _LOCATION_NAMES)}
    offenders = {rel: hits for rel, src in candidates.items() if (hits := transcript_writes(src))}
    assert not offenders, (
        f"#18293: {offenders} write under the retired transcript store. A turn's one durable home is "
        "chat_sessions (ChatHistoryManager); moving legacy files is a #17038 proposal, never code."
    )


def test_the_llm_context_cache_is_written_only_by_a_declared_site() -> None:
    declared = set(STORE_AUTHORITY["chat_sessions"].write_sites)
    writers = {
        rel
        for rel, src in _population().items()
        if ("CHAT_CONVERSATION_PREFIX" in src or "chat:conversation:" in src) and writes_llm_context_cache(src)
    }
    assert "autobot-backend/chat_workflow/conversation.py" in writers
    assert writers <= declared, f"#18293: undeclared chat:conversation:* writers: {sorted(writers - declared)}"


def test_the_legacy_store_is_declared_read_only() -> None:
    legacy = STORE_AUTHORITY["legacy_conversation_transcripts"]
    assert legacy.write_sites == ()
    assert "#17038" in legacy.note


_ENV_KEY = "AUTOBOT_LEGACY_TRANSCRIPTS_DIR"
_ANSIBLE_ENV = "autobot-slm-backend/ansible/roles/backend/templates/backend.env.j2"
_ANSIBLE_UNIT = "autobot-slm-backend/ansible/roles/backend/templates/autobot-backend.service.j2"
_COMPOSE = "docker-compose.yml"
_DOCKERFILE = "docker/backend/Dockerfile"


def _setting(text: str, key: str) -> str | None:
    """The value a template assigns to *key* (``KEY=v`` or ``- KEY=${KEY:-v}``), else None."""
    match = re.search(rf"^\s*(?:-\s*)?{re.escape(key)}=(.+?)\s*$", text, re.MULTILINE)
    if not match:
        return None
    value = match.group(1)
    default = re.fullmatch(rf"\$\{{{re.escape(key)}:-(.+)\}}", value)
    return default.group(1) if default else value


def test_the_template_reader_sees_a_pin_and_its_absence() -> None:
    assert _setting("A=1\nAUTOBOT_LEGACY_TRANSCRIPTS_DIR={{ d }}/x\n", _ENV_KEY) == "{{ d }}/x"
    assert (
        _setting("      - AUTOBOT_LEGACY_TRANSCRIPTS_DIR=${AUTOBOT_LEGACY_TRANSCRIPTS_DIR:-/app/x}\n", _ENV_KEY)
        == "/app/x"
    )
    assert _setting("AUTOBOT_DATA_DIR=/var/lib/autobot\n", _ENV_KEY) is None


def _read(rel: str) -> str:
    return (repo_root() / rel).read_text(encoding="utf-8")


def test_the_ansible_env_pins_the_location_under_the_service_working_directory() -> None:
    """Pinned, not inferred from base_dir: the old writer wrote under the unit's WorkingDirectory."""
    workdir = _setting(_read(_ANSIBLE_UNIT), "WorkingDirectory")
    assert workdir, f"{_ANSIBLE_UNIT} no longer sets WorkingDirectory"
    assert _setting(_read(_ANSIBLE_ENV), _ENV_KEY) == f"{workdir}/data/conversation_transcripts"


def test_the_compose_backend_pins_the_location_under_the_image_workdir() -> None:
    workdirs = re.findall(r"^WORKDIR\s+(\S+)", _read(_DOCKERFILE), re.MULTILINE)
    assert workdirs, f"{_DOCKERFILE} sets no WORKDIR"
    assert _setting(_read(_COMPOSE), _ENV_KEY) == f"{workdirs[-1]}/data/conversation_transcripts"


def _calls(source: str, name: str) -> bool:
    return any(isinstance(n, ast.Call) and _called_name(n) == name for n in ast.walk(ast.parse(source)))


def test_only_an_approved_proposal_removes_a_legacy_transcript() -> None:
    """A session delete never removes one: ownership of a legacy file cannot be proven (#18293)."""
    assert _calls("await remove_legacy_transcript(sid)\n", "remove_legacy_transcript")
    assert not _calls("from x import remove_legacy_transcript\n", "remove_legacy_transcript")
    callers = {
        rel
        for rel, src in _population().items()
        if "remove_legacy_transcript" in src and _calls(src, "remove_legacy_transcript")
    }
    assert callers == {"autobot-backend/services/legacy_transcript_disposal_action.py"}, callers


_CONTENT_READER = "read_legacy_transcript_pairs"
_REPAIR_TOOL = "autobot-backend/chat_history/session_reply_backfill.py"
_LEGACY_MODULE = "autobot-backend/chat_history/legacy_transcripts.py"


def _imports_module(source: str, dotted: str) -> bool:
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.module == dotted:
            return True
        if isinstance(node, ast.Import) and any(alias.name == dotted for alias in node.names):
            return True
    return False


def _opening_functions(source: str) -> set[str]:
    """Functions in *source* that open a file -- the legacy module may have exactly one."""
    return {
        fn.name
        for fn in ast.walk(ast.parse(source))
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(isinstance(n, ast.Call) and _called_name(n) == "open" for n in ast.walk(fn))
    }


def test_the_reader_matchers_see_a_read_and_an_import() -> None:
    assert _calls("pairs = await read_legacy_transcript_pairs(sid)\n", _CONTENT_READER)
    assert _imports_module(
        "from chat_history.session_reply_backfill import repair_session\n", "chat_history.session_reply_backfill"
    )
    assert not _imports_module("import chat_history\n", "chat_history.session_reply_backfill")
    assert _opening_functions("async def r(p):\n    async with aiofiles.open(p) as f:\n        pass\n") == {"r"}


def test_no_request_path_reads_a_legacy_transcript() -> None:
    """Ownership of a legacy file cannot be proven, so only human-run/approved tooling reads one (#18293)."""
    population = _population()
    readers = {rel for rel, src in population.items() if _CONTENT_READER in src and _calls(src, _CONTENT_READER)}
    assert readers == {_REPAIR_TOOL}, f"#18293: legacy transcript content read outside the repair tool: {readers}"
    importers = {
        rel
        for rel, src in population.items()
        if "session_reply_backfill" in src and _imports_module(src, "chat_history.session_reply_backfill")
    }
    assert not importers, f"#18293: the human-run repair tool is imported by production code: {importers}"
    assert _opening_functions(population[_LEGACY_MODULE]) == {_CONTENT_READER}
