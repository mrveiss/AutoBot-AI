# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An agent that writes must say what it writes (#15950).

Enforcement that depends on every future author remembering to call it is not
enforcement. `BaseAgent.declared_scopes` defaults to `[]` so that adding claims
could not break agents nobody had revisited -- which is the right default and
also the exact hole this closes: a new writing agent inherits "declares nothing"
silently, and nothing about it looks wrong.

WHAT THIS DETECTOR ACTUALLY ANSWERS, which is narrower than its name:
agent classes *defined under `autobot-backend/agents/`* whose own class body
contains a call whose name begins with a write-ish verb. It does not follow
calls into helper modules, does not see writes performed by a collaborator
object, and does not know that `save_draft` writes while `save_time` does not.
It is a tripwire for the common case, not a proof of absence -- so the tests
below assert what it CAN see, and one of them asserts it can still see anything
at all.
"""

from __future__ import annotations

import ast
import pathlib
import re

AGENTS_DIR = pathlib.Path(__file__).resolve().parents[2] / "agents"

#: A call whose name starts one of these is treated as a write. Deliberately
#: verb-prefixed rather than a name list: a list would have to be extended for
#: every new persistence helper, and the extension is the step that gets missed.
_WRITE_VERB = re.compile(r"^(add_|store_|save_|write_|upsert|persist_|index_)")

#: The root of the agent hierarchy. Every other base is discovered from it, so a
#: class inheriting through `StandardizedAgent` or `BaseModalityAgent` is found
#: without naming those here -- naming them is how the next intermediate base
#: becomes an invisible blind spot.
_ROOT_BASE = "BaseAgent"


def _class_index() -> dict[str, tuple[str, set[str], ast.ClassDef]]:
    index: dict[str, tuple[str, set[str], ast.ClassDef]] = {}
    for path in sorted(AGENTS_DIR.glob("*.py")):
        if path.name.endswith("_test.py"):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover - a broken file is another test's problem
            continue
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                bases = {b.id for b in node.bases if isinstance(b, ast.Name)}
                index[node.name] = (path.name, bases, node)
    return index


def _agent_classes(index) -> set[str]:
    """Everything reachable from `BaseAgent` by inheritance, transitively."""
    found, changed = {_ROOT_BASE}, True
    while changed:
        changed = False
        for name, (_f, bases, _n) in index.items():
            if name not in found and bases & found:
                found.add(name)
                changed = True
    return found - {_ROOT_BASE}


def _first_write(node: ast.ClassDef) -> str | None:
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        func = sub.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if _WRITE_VERB.match(name or ""):
            return name
        if name == "open" and any(
            isinstance(a, ast.Constant) and isinstance(a.value, str) and "w" in a.value for a in sub.args[1:]
        ):
            return "open(mode='w')"
    return None


def _declares(node: ast.ClassDef) -> bool:
    return any(
        isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and m.name == "declared_scopes" for m in node.body
    )


def _write_capable_agents():
    index = _class_index()
    out = []
    for name in sorted(_agent_classes(index)):
        filename, _bases, node = index[name]
        write = _first_write(node)
        if write:
            out.append((f"{filename}:{name}", write, _declares(node)))
    return out


#: The one write-capable agent that cannot declare yet, and precisely why.
#: `npu_code_search_agent.py` sits at exactly its grandfathered size ceiling
#: (1455 lines), so ANY addition to it fails the file-size ratchet -- including
#: the ~10 lines a `declared_scopes` override needs. Getting it under the ceiling
#: means extracting from a 1455-line file, which is its own change with its own
#: review. Tracked in #16173; this entry goes away when that lands.
#:
#: An entry here is a STATED gap, which is a finding. Removing the guard, or
#: quietly widening the detector until this class stopped matching, would be the
#: unstated kind.
_CEILING_BLOCKED = {
    "npu_code_search_agent.py:NPUCodeSearchAgent": "file at its size ceiling; see #16173",
}


def test_every_write_capable_agent_declares_its_scopes():
    """The rule with teeth, minus one entry that says out loud why it is exempt."""
    undeclared = [
        (where, verb)
        for where, verb, declares in _write_capable_agents()
        if not declares and where not in _CEILING_BLOCKED
    ]

    assert not undeclared, (
        f"{[u[0] for u in undeclared]} write but declare no scopes. Override `declared_scopes` "
        "to return the `<kind>:<path>` values the run will touch, so a second agent working the "
        "same scope is refused instead of overwriting. Verbs seen: "
        f"{[u[1] for u in undeclared]}"
    )


def test_the_detector_can_still_see_a_writing_agent():
    """Otherwise the test above passes by finding nothing, which is not the same as finding none.

    If a refactor moves every persistence call behind a collaborator, this
    detector goes quiet and the guard above turns green forever while enforcing
    nothing. The guard must fail loudly when it stops being able to look, rather
    than reporting a clean tree it never inspected (#15962).
    """
    assert _write_capable_agents(), (
        "no write-capable agent found at all -- the detector has gone blind rather than the "
        "codebase having gone read-only. Check `_WRITE_VERB` and `_agent_classes` before "
        "trusting any green result from this module."
    )


def test_the_detector_fires_on_a_writing_class_that_does_not_declare(tmp_path):
    """Prove the guard can FAIL. A tripwire nobody has seen trip is an assumption."""
    module = tmp_path / "pretend_agent.py"
    module.write_text(
        "class PretendAgent(BaseAgent):\n"
        "    async def process_request(self, request):\n"
        "        await self.store_result(request)\n",
        encoding="utf-8",
    )
    tree = ast.parse(module.read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))

    assert _first_write(cls) == "store_result"
    assert not _declares(cls)


def test_the_detector_does_not_fire_on_a_read_only_agent(tmp_path):
    """And that it can PASS -- a detector that flags everything gets switched off."""
    module = tmp_path / "reader_agent.py"
    module.write_text(
        "class ReaderAgent(BaseAgent):\n"
        "    async def process_request(self, request):\n"
        "        return await self.search_knowledge(request.payload)\n",
        encoding="utf-8",
    )
    tree = ast.parse(module.read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))

    assert _first_write(cls) is None


def test_transitive_bases_are_followed_not_hardcoded():
    """A class inheriting through an intermediate base must still be seen.

    `BaseModalityAgent` sits between `StandardizedAgent` and seven agents. An
    earlier version of this detector named its bases literally and missed all
    seven -- the blind spot was invisible because the guard was green.
    """
    index = _class_index()
    agents = _agent_classes(index)

    assert "BaseModalityAgent" in agents, "the intermediate base itself must be recognised"
    modality_children = [n for n, (_f, b, _x) in index.items() if "BaseModalityAgent" in b]
    assert modality_children, "expected agents inheriting through BaseModalityAgent"
    assert set(modality_children) <= agents, "a class two levels from BaseAgent was not reached"


def test_the_ceiling_exemption_does_not_outlive_its_reason():
    """An exemption naming a class that now declares exempts nothing and misleads.

    Same failure the file-size audit refuses: an entry naming a compliant file
    "exempts nothing while looking authoritative". When #16173 lands and the
    agent declares, this fails until the entry is deleted.
    """
    declaring = {where for where, _verb, declares in _write_capable_agents() if declares}
    stale = sorted(_CEILING_BLOCKED.keys() & declaring)

    assert not stale, f"{stale} now declare scopes -- delete their _CEILING_BLOCKED entries"


def test_the_ceiling_exemption_still_names_something_real():
    """And that it does not name a class the detector no longer sees at all."""
    known = {where for where, _verb, _declares in _write_capable_agents()}
    phantom = sorted(_CEILING_BLOCKED.keys() - known)

    assert not phantom, (
        f"{phantom} are exempted but no longer detected as write-capable. Either they were "
        "removed -- delete the entry -- or the detector stopped seeing them, which is worse."
    )
