# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Template variables must reach step inputs, not just actions (#15682).

``create_workflow_from_template`` substituted ``action`` and ``description``
and then copied ``step.inputs`` verbatim, so every placeholder an input carried
arrived at the handler as the literal ``{var}``. Two of those inputs are LLM
prompts, which is how a template variable became a prompt defect.

These assertions read the instantiated workflow rather than the substitution
helper: a helper test would have passed throughout, because the helper was
never broken -- it was never called on ``inputs``.
"""

from typing import Any, Dict

from workflow_templates.manager import WorkflowTemplateManager

_VARIABLES = {
    "subreddits": "selfhosted,LocalLLaMA",
    "keywords": "local AI assistant,self-hosted automation",
    "autobot_url": "the project page",
}


def _steps_by_id(workflow: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {step["step_id"]: step for step in workflow["steps"]}


def _instantiate() -> Dict[str, Any]:
    workflow = WorkflowTemplateManager().create_workflow_from_template("reddit_monitor_reply", _VARIABLES)
    assert workflow is not None, "the reddit_monitor_reply template did not instantiate"
    return workflow


def test_inputs_are_substituted_not_copied_verbatim() -> None:
    """The defect exactly: inputs arrived holding the placeholder text."""
    inputs = _steps_by_id(_instantiate())["reddit_search"]["inputs"]

    assert inputs["subreddits"] == _VARIABLES["subreddits"]
    assert inputs["keywords"] == _VARIABLES["keywords"]


def test_a_prompt_input_reaches_the_handler_with_its_variable_filled() -> None:
    """The LLM half: a prompt shipping `{autobot_url}` is a prompt with a hole."""
    prompt = _steps_by_id(_instantiate())["draft_replies"]["inputs"]["prompt"]

    assert _VARIABLES["autobot_url"] in prompt
    assert "{autobot_url}" not in prompt


def test_non_string_inputs_keep_their_declared_types() -> None:
    """Substitution must not coerce; a limit of 25 is an int, not "25"."""
    inputs = _steps_by_id(_instantiate())["reddit_search"]["inputs"]

    assert inputs["limit"] == 25
    assert isinstance(inputs["limit"], int)
    assert inputs["min_score"] == 5


def test_substitution_reaches_inside_nested_containers() -> None:
    """``WorkflowTask.inputs`` is Dict[str, Any] and templates nest lists in it.

    A top-level pass over string values would satisfy every test above and
    still miss this, so the nesting is pinned directly rather than inferred
    from the templates that happen to exist today.
    """
    manager = WorkflowTemplateManager()
    nested = {
        "targets": ["{subreddits}", {"deep": "{keywords}"}],
        "meta": {"url": "{autobot_url}", "count": 3},
    }

    result = manager._substitute_in(nested, _VARIABLES)

    assert result["targets"][0] == _VARIABLES["subreddits"]
    assert result["targets"][1]["deep"] == _VARIABLES["keywords"]
    assert result["meta"]["url"] == _VARIABLES["autobot_url"]
    assert result["meta"]["count"] == 3


def test_an_unprovided_variable_is_left_visible_rather_than_blanked() -> None:
    """A missing variable must stay legible, not silently become empty text.

    Blanking would turn "mention AutoBot at {autobot_url}" into a sentence that
    reads as finished while having lost its content -- the #15630 failure mode.
    """
    workflow = WorkflowTemplateManager().create_workflow_from_template("reddit_monitor_reply", {})
    assert workflow is not None

    prompt = _steps_by_id(workflow)["draft_replies"]["inputs"]["prompt"]
    assert "{autobot_url}" in prompt
