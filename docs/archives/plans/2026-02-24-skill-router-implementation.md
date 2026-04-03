# Skill Router Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a `SkillRouterSkill` meta-skill that, given a natural-language task description, finds and enables the best matching skill using a two-phase hybrid approach (keyword scoring → LLM re-ranking).

**Architecture:** Phase 1 tokenizes the task and scores each registered skill by token overlap across `name`, `tags`, `tools`, and `description` (weighted). Phase 2 sends the top-K candidates to AutoBot's `LLMInterface.chat_completion()` for re-ranking. The winner is enabled via `get_skill_registry().enable_skill()`.

**Tech Stack:** Python 3.12, `skills.base_skill.BaseSkill`, `skills.registry.get_skill_registry`, `llm_interface_pkg.LLMInterface`, `pytest`, `unittest.mock`

---

## Task 1: Keyword Scorer

**Files:**
- Create: `autobot-backend/skills/builtin/skill_router_test.py`
- Create: `autobot-backend/skills/builtin/skill_router.py`

### Step 1: Write the failing test

Create `autobot-backend/skills/builtin/skill_router_test.py`:

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for SkillRouterSkill (skill-router meta-skill)."""

import re
import pytest
from skills.base_skill import SkillManifest, SkillConfigField
from skills.builtin.skill_router import SkillRouterSkill, _tokenize, _score_skill


def _make_manifest(name, description, tags, tools):
    return SkillManifest(
        name=name,
        version="1.0.0",
        description=description,
        author="mrveiss",
        category="test",
        tags=tags,
        tools=tools,
    )


def test_tokenize_splits_on_non_word():
    assert _tokenize("analyze this PDF document") == {"analyze", "this", "pdf", "document"}


def test_tokenize_handles_kebab_and_underscore():
    assert "browser" in _tokenize("browser-automation")
    assert "automation" in _tokenize("browser-automation")
    assert "code" in _tokenize("code_review")


def test_score_skill_matches_tags():
    manifest = _make_manifest(
        name="document-analysis",
        description="Analyze documents",
        tags=["document", "pdf", "analysis"],
        tools=["analyze_doc"],
    )
    score = _score_skill({"pdf", "document"}, manifest)
    assert score > 0


def test_score_skill_tag_and_name_weighted_higher_than_description():
    manifest_good = _make_manifest(
        name="pdf-tool",
        description="General purpose tool",
        tags=["pdf"],
        tools=["process"],
    )
    manifest_weak = _make_manifest(
        name="general-tool",
        description="This tool handles pdf documents",
        tags=["general"],
        tools=["process"],
    )
    score_good = _score_skill({"pdf"}, manifest_good)
    score_weak = _score_skill({"pdf"}, manifest_weak)
    assert score_good > score_weak


def test_score_skill_zero_for_no_match():
    manifest = _make_manifest(
        name="calendar-integration",
        description="Manage calendar events",
        tags=["calendar", "events"],
        tools=["create_event"],
    )
    score = _score_skill({"browser", "scrape", "web"}, manifest)
    assert score == 0.0
```

### Step 2: Run to verify it fails

```bash
cd /home/kali/Desktop/AutoBot/autobot-backend
python -m pytest skills/builtin/skill_router_test.py -v 2>&1 | head -30
```

Expected: `ImportError` — `skill_router` does not exist yet.

### Step 3: Implement `_tokenize` and `_score_skill`

Create `autobot-backend/skills/builtin/skill_router.py`:

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Skill Router Meta-Skill

Two-phase skill discovery: keyword scoring (Phase 1) + LLM re-ranking (Phase 2).
Auto-enables the best matching skill for a given task description.
"""

import json
import logging
import re
from typing import Any, Dict, List, Set, Tuple

from skills.base_skill import BaseSkill, SkillConfigField, SkillManifest

logger = logging.getLogger(__name__)


def _tokenize(text: str) -> Set[str]:
    """Lowercase and split text on non-word characters."""
    return {t for t in re.split(r"[\W_]+", text.lower()) if t}


def _score_skill(task_tokens: Set[str], manifest: SkillManifest) -> float:
    """Score a skill manifest against task tokens.

    Weights: name (3x), tags (3x), tools (2x), description (1x).
    """
    name_tokens = _tokenize(manifest.name)
    tag_tokens: Set[str] = set()
    for tag in manifest.tags:
        tag_tokens.update(_tokenize(tag))
    tool_tokens: Set[str] = set()
    for tool in manifest.tools:
        tool_tokens.update(_tokenize(tool))
    desc_tokens = _tokenize(manifest.description)

    return (
        len(task_tokens & name_tokens) * 3.0
        + len(task_tokens & tag_tokens) * 3.0
        + len(task_tokens & tool_tokens) * 2.0
        + len(task_tokens & desc_tokens) * 1.0
    )
```

### Step 4: Run to verify scorer tests pass

```bash
cd /home/kali/Desktop/AutoBot/autobot-backend
python -m pytest skills/builtin/skill_router_test.py::test_tokenize_splits_on_non_word \
  skills/builtin/skill_router_test.py::test_tokenize_handles_kebab_and_underscore \
  skills/builtin/skill_router_test.py::test_score_skill_matches_tags \
  skills/builtin/skill_router_test.py::test_score_skill_tag_and_name_weighted_higher_than_description \
  skills/builtin/skill_router_test.py::test_score_skill_zero_for_no_match -v
```

Expected: 5 passed.

### Step 5: Commit

```bash
git add autobot-backend/skills/builtin/skill_router.py \
        autobot-backend/skills/builtin/skill_router_test.py
git commit -m "feat(skills): add skill-router keyword scorer and tests"
```

---

## Task 2: LLM Re-ranker

**Files:**
- Modify: `autobot-backend/skills/builtin/skill_router.py`
- Modify: `autobot-backend/skills/builtin/skill_router_test.py`

### Step 1: Add tests for `_llm_rerank`

Append to `skill_router_test.py`:

```python
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


def test_llm_rerank_parses_json_response():
    """_llm_rerank should parse skill name and reason from LLM JSON."""
    mock_response = MagicMock()
    mock_response.content = '{"skill": "document-analysis", "reason": "PDF task"}'
    mock_response.error = None

    candidates = [
        {"name": "document-analysis", "description": "Analyze docs", "tags": [], "tools": []},
        {"name": "browser-automation", "description": "Browse web", "tags": [], "tools": []},
    ]

    with patch(
        "skills.builtin.skill_router.LLMInterface"
    ) as MockLLM:
        instance = MockLLM.return_value
        instance.chat_completion = AsyncMock(return_value=mock_response)

        skill = SkillRouterSkill()
        name, reason = asyncio.get_event_loop().run_until_complete(
            skill._llm_rerank("analyze this pdf", candidates)
        )

    assert name == "document-analysis"
    assert reason == "PDF task"


def test_llm_rerank_handles_markdown_code_block():
    """_llm_rerank should extract JSON from ```json ... ``` blocks."""
    mock_response = MagicMock()
    mock_response.content = '```json\n{"skill": "code-review", "reason": "code task"}\n```'
    mock_response.error = None

    candidates = [
        {"name": "code-review", "description": "Review code", "tags": [], "tools": []},
    ]

    with patch("skills.builtin.skill_router.LLMInterface") as MockLLM:
        instance = MockLLM.return_value
        instance.chat_completion = AsyncMock(return_value=mock_response)

        skill = SkillRouterSkill()
        name, reason = asyncio.get_event_loop().run_until_complete(
            skill._llm_rerank("review my code", candidates)
        )

    assert name == "code-review"
```

### Step 2: Run to verify tests fail

```bash
cd /home/kali/Desktop/AutoBot/autobot-backend
python -m pytest skills/builtin/skill_router_test.py::test_llm_rerank_parses_json_response \
  skills/builtin/skill_router_test.py::test_llm_rerank_handles_markdown_code_block -v
```

Expected: `AttributeError` — `_llm_rerank` not yet defined.

### Step 3: Implement `_llm_rerank` and `SkillRouterSkill` class skeleton

Add to `skill_router.py` after the helper functions:

```python
try:
    from llm_interface_pkg import LLMInterface
    _LLM_AVAILABLE = True
except ImportError:
    LLMInterface = None  # type: ignore[assignment,misc]
    _LLM_AVAILABLE = False


class SkillRouterSkill(BaseSkill):
    """Meta-skill: finds and enables the best skill for a given task."""

    @staticmethod
    def get_manifest() -> SkillManifest:
        """Return skill-router manifest."""
        return SkillManifest(
            name="skill-router",
            version="1.0.0",
            description="Meta-skill that routes tasks to the most appropriate skill",
            author="mrveiss",
            category="meta",
            dependencies=[],
            config={
                "top_k": SkillConfigField(
                    type="int",
                    default=5,
                    description="Number of keyword candidates to send to LLM",
                ),
                "auto_enable": SkillConfigField(
                    type="bool",
                    default=True,
                    description="Enable the winning skill automatically",
                ),
            },
            tools=["find_skill"],
            triggers=[],
            tags=["meta", "routing", "discovery", "orchestration"],
        )

    async def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a skill router action."""
        if action == "find_skill":
            return await self._find_skill(params)
        return {"success": False, "error": f"Unknown action: {action}"}

    async def _llm_rerank(
        self, task: str, candidates: List[Dict[str, Any]]
    ) -> Tuple[str, str]:
        """Re-rank candidates via LLM. Returns (skill_name, reason).

        Raises ValueError if LLM unavailable or response unparseable.
        """
        if not _LLM_AVAILABLE or LLMInterface is None:
            raise ValueError("LLMInterface not available")

        summaries = [
            f"- {c['name']}: {c['description']} "
            f"(tags: {', '.join(c['tags'])}, tools: {', '.join(c['tools'])})"
            for c in candidates
        ]
        prompt = (
            f'Given this task: "{task}"\n\n'
            f"Choose the most appropriate skill from:\n"
            + "\n".join(summaries)
            + '\n\nRespond with JSON only: {"skill": "<name>", "reason": "<brief reason>"}'
        )
        messages = [{"role": "user", "content": prompt}]
        llm = LLMInterface()
        response = await llm.chat_completion(messages, llm_type="task")

        content = response.content.strip()
        # Strip markdown code blocks if present
        match = re.search(r"\{.*?\}", content, re.DOTALL)
        if not match:
            raise ValueError(f"No JSON found in LLM response: {content[:100]}")
        data = json.loads(match.group())
        return data["skill"], data.get("reason", "")

    async def _find_skill(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Placeholder — implemented in Task 3."""
        return {"success": False, "error": "not implemented"}
```

### Step 4: Run to verify re-ranker tests pass

```bash
cd /home/kali/Desktop/AutoBot/autobot-backend
python -m pytest skills/builtin/skill_router_test.py::test_llm_rerank_parses_json_response \
  skills/builtin/skill_router_test.py::test_llm_rerank_handles_markdown_code_block -v
```

Expected: 2 passed.

### Step 5: Commit

```bash
git add autobot-backend/skills/builtin/skill_router.py \
        autobot-backend/skills/builtin/skill_router_test.py
git commit -m "feat(skills): add skill-router LLM re-ranker"
```

---

## Task 3: `find_skill` Action + Full Integration

**Files:**
- Modify: `autobot-backend/skills/builtin/skill_router.py`
- Modify: `autobot-backend/skills/builtin/skill_router_test.py`

### Step 1: Add integration tests for `execute("find_skill", ...)`

Append to `skill_router_test.py`:

```python
def _make_registry_skill(name, description, tags, tools):
    """Build a minimal mock skill with a manifest."""
    mock_skill = MagicMock()
    mock_skill.get_manifest.return_value = _make_manifest(name, description, tags, tools)
    return mock_skill


def test_find_skill_enables_best_match_via_llm():
    """find_skill should enable the LLM-chosen winner and return it."""
    mock_llm_response = MagicMock()
    mock_llm_response.content = '{"skill": "document-analysis", "reason": "PDF task"}'
    mock_llm_response.error = None

    registry_skills = {
        "document-analysis": _make_registry_skill(
            "document-analysis", "Analyze documents", ["document", "pdf"], ["analyze_doc"]
        ),
        "browser-automation": _make_registry_skill(
            "browser-automation", "Automate browser", ["browser", "web"], ["browse"]
        ),
    }

    mock_registry = MagicMock()
    mock_registry._skills = registry_skills
    mock_registry.enable_skill.return_value = {"success": True}

    with patch("skills.builtin.skill_router.get_skill_registry", return_value=mock_registry), \
         patch("skills.builtin.skill_router.LLMInterface") as MockLLM:
        instance = MockLLM.return_value
        instance.chat_completion = AsyncMock(return_value=mock_llm_response)

        skill = SkillRouterSkill()
        skill.apply_config({"top_k": 5, "auto_enable": True})
        result = asyncio.get_event_loop().run_until_complete(
            skill.execute("find_skill", {"task": "analyze this pdf document"})
        )

    assert result["success"] is True
    assert result["enabled_skill"] == "document-analysis"
    assert result["method"] == "llm"
    assert "reason" in result
    assert len(result["candidates"]) > 0
    mock_registry.enable_skill.assert_called_once_with("document-analysis")


def test_find_skill_falls_back_to_keyword_on_llm_error():
    """If LLM fails, use the top keyword-scored skill."""
    registry_skills = {
        "document-analysis": _make_registry_skill(
            "document-analysis", "Analyze documents", ["document", "pdf"], ["analyze_doc"]
        ),
        "browser-automation": _make_registry_skill(
            "browser-automation", "Automate browser", ["browser"], ["browse"]
        ),
    }

    mock_registry = MagicMock()
    mock_registry._skills = registry_skills
    mock_registry.enable_skill.return_value = {"success": True}

    with patch("skills.builtin.skill_router.get_skill_registry", return_value=mock_registry), \
         patch("skills.builtin.skill_router.LLMInterface") as MockLLM:
        instance = MockLLM.return_value
        instance.chat_completion = AsyncMock(side_effect=Exception("LLM timeout"))

        skill = SkillRouterSkill()
        skill.apply_config({"top_k": 5, "auto_enable": True})
        result = asyncio.get_event_loop().run_until_complete(
            skill.execute("find_skill", {"task": "analyze this pdf document"})
        )

    assert result["success"] is True
    assert result["enabled_skill"] == "document-analysis"
    assert result["method"] == "keyword_fallback"


def test_find_skill_dry_run_does_not_enable():
    """dry_run=True should return result without calling enable_skill."""
    mock_llm_response = MagicMock()
    mock_llm_response.content = '{"skill": "document-analysis", "reason": "test"}'
    mock_llm_response.error = None

    registry_skills = {
        "document-analysis": _make_registry_skill(
            "document-analysis", "Analyze documents", ["document", "pdf"], ["analyze_doc"]
        ),
    }

    mock_registry = MagicMock()
    mock_registry._skills = registry_skills

    with patch("skills.builtin.skill_router.get_skill_registry", return_value=mock_registry), \
         patch("skills.builtin.skill_router.LLMInterface") as MockLLM:
        instance = MockLLM.return_value
        instance.chat_completion = AsyncMock(return_value=mock_llm_response)

        skill = SkillRouterSkill()
        skill.apply_config({"top_k": 5, "auto_enable": True})
        result = asyncio.get_event_loop().run_until_complete(
            skill.execute("find_skill", {"task": "analyze pdf", "dry_run": True})
        )

    assert result["success"] is True
    mock_registry.enable_skill.assert_not_called()


def test_find_skill_requires_task_param():
    """find_skill with no task returns error."""
    skill = SkillRouterSkill()
    result = asyncio.get_event_loop().run_until_complete(
        skill.execute("find_skill", {})
    )
    assert result["success"] is False
    assert "task" in result["error"].lower()


def test_find_skill_no_skills_registered():
    """find_skill returns error when registry is empty."""
    mock_registry = MagicMock()
    mock_registry._skills = {}

    with patch("skills.builtin.skill_router.get_skill_registry", return_value=mock_registry):
        skill = SkillRouterSkill()
        result = asyncio.get_event_loop().run_until_complete(
            skill.execute("find_skill", {"task": "do something"})
        )

    assert result["success"] is False
    assert "no skills" in result["error"].lower()
```

### Step 2: Run to verify tests fail

```bash
cd /home/kali/Desktop/AutoBot/autobot-backend
python -m pytest skills/builtin/skill_router_test.py::test_find_skill_enables_best_match_via_llm \
  skills/builtin/skill_router_test.py::test_find_skill_falls_back_to_keyword_on_llm_error \
  skills/builtin/skill_router_test.py::test_find_skill_dry_run_does_not_enable \
  skills/builtin/skill_router_test.py::test_find_skill_requires_task_param \
  skills/builtin/skill_router_test.py::test_find_skill_no_skills_registered -v
```

Expected: failures (placeholder `_find_skill` returns not-implemented).

### Step 3: Implement `_find_skill`

Replace the placeholder `_find_skill` in `skill_router.py`:

```python
async def _find_skill(self, params: Dict[str, Any]) -> Dict[str, Any]:
    """Find and enable the best skill for the given task. Issue #<new>."""
    task: str = params.get("task", "").strip()
    dry_run: bool = params.get("dry_run", False)

    if not task:
        return {"success": False, "error": "task parameter is required"}

    from skills.registry import get_skill_registry

    registry = get_skill_registry()
    all_skills = registry._skills

    if not all_skills:
        return {"success": False, "error": "no skills registered"}

    # Phase 1: keyword scoring
    top_k: int = self._config.get("top_k", 5)
    task_tokens = _tokenize(task)
    scored = []
    for name, skill_instance in all_skills.items():
        manifest = skill_instance.get_manifest()
        score = _score_skill(task_tokens, manifest)
        scored.append({
            "name": manifest.name,
            "description": manifest.description,
            "tags": manifest.tags,
            "tools": manifest.tools,
            "score": score,
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    candidates = [c for c in scored[:top_k] if c["score"] > 0] or scored[:1]

    # Phase 2: LLM re-ranking
    winner = candidates[0]["name"]
    reason = "top keyword match"
    method = "keyword_fallback"

    try:
        llm_winner, llm_reason = await self._llm_rerank(task, candidates)
        # Validate LLM returned a real candidate name
        candidate_names = {c["name"] for c in candidates}
        if llm_winner in candidate_names:
            winner = llm_winner
            reason = llm_reason
            method = "llm"
        else:
            logger.warning(
                "LLM returned unknown skill '%s', using keyword winner '%s'",
                llm_winner,
                winner,
            )
    except Exception as exc:
        logger.warning("LLM re-ranking failed, using keyword fallback: %s", exc)

    # Enable winner
    auto_enable: bool = self._config.get("auto_enable", True)
    if auto_enable and not dry_run:
        enable_result = registry.enable_skill(winner)
        if not enable_result.get("success"):
            return {
                "success": False,
                "error": f"Failed to enable skill '{winner}': {enable_result.get('error')}",
            }

    return {
        "success": True,
        "enabled_skill": winner,
        "reason": reason,
        "method": method,
        "candidates": [{"name": c["name"], "score": c["score"]} for c in candidates],
        "dry_run": dry_run,
    }
```

Also add the missing import at the top of the file (add to the imports section):

```python
from skills.registry import get_skill_registry
```

### Step 4: Run all tests

```bash
cd /home/kali/Desktop/AutoBot/autobot-backend
python -m pytest skills/builtin/skill_router_test.py -v
```

Expected: all tests pass (green).

### Step 5: Commit

```bash
git add autobot-backend/skills/builtin/skill_router.py \
        autobot-backend/skills/builtin/skill_router_test.py
git commit -m "feat(skills): implement find_skill action with LLM re-ranking and fallback"
```

---

## Task 4: Verify Auto-Discovery

The registry's `discover_builtin_skills()` uses `pkgutil.iter_modules` + reflection to find all `BaseSkill` subclasses in `skills.builtin`. No manual registration needed — just verify.

### Step 1: Smoke test discovery

```bash
cd /home/kali/Desktop/AutoBot/autobot-backend
python -c "
from skills.registry import SkillRegistry
r = SkillRegistry()
r.discover_builtin_skills()
skill = r.get('skill-router')
print('Found:', skill)
print('Manifest:', skill.get_manifest().name if skill else 'NOT FOUND')
"
```

Expected output:
```
Found: <skills.builtin.skill_router.SkillRouterSkill object at 0x...>
Manifest: skill-router
```

If `NOT FOUND`: check that `SkillRouterSkill` is not accidentally named with a leading underscore and that the module has no import errors.

### Step 2: Run full skill test suite to check no regressions

```bash
cd /home/kali/Desktop/AutoBot/autobot-backend
python -m pytest skills/ -v --tb=short 2>&1 | tail -20
```

Expected: all existing tests still pass + new skill_router tests pass.

### Step 3: Commit (if any fixes needed from discovery check)

```bash
git add autobot-backend/skills/builtin/skill_router.py
git commit -m "fix(skills): ensure skill-router auto-discovers correctly"
```

---

## Done

After Task 4 passes, the `skill-router` skill:
- Auto-discovered on backend startup
- Exposes `find_skill` tool
- Phase 1: keyword scores all registered skills
- Phase 2: LLM re-ranks top-K via `LLMInterface.chat_completion()`
- Falls back to keyword winner if LLM fails
- Calls `registry.enable_skill(winner)` and returns `{success, enabled_skill, reason, method, candidates}`
