# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Sub-Workflow Composition — workflows as reusable building blocks.

Issue #2143: Allow a workflow step to invoke another stored workflow by ID,
mapping parent variables into the child's input context and capturing child
outputs under a named key in the parent step_outputs registry.

Key classes
-----------
SubWorkflowStep
    Typed description of a sub-workflow invocation embedded inside a parent
    workflow step dict.

SubWorkflowExecutor
    Resolves input mappings, executes the child workflow through a provided
    WorkflowExecutor instance (recursive composition), captures outputs, and
    enforces a nesting depth limit to prevent infinite recursion.

Module-level helpers
--------------------
is_sub_workflow_step(step)
    Return True when *step* carries ``type="sub_workflow"`` and a non-empty
    ``workflow_id``.

extract_sub_workflow_step(step)
    Parse a raw step dict into a SubWorkflowStep dataclass.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Dict, List

from constants.status_enums import TaskStatus

from .variable_resolver import StepOutput, VariableResolver

if TYPE_CHECKING:
    # Avoid a circular import at runtime — WorkflowExecutor imports this module.
    from .workflow_executor import WorkflowExecutor
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Hard limit on how deeply sub-workflows may nest to prevent runaway recursion.
MAX_NESTING_DEPTH: int = 5

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class SubWorkflowStep:
    """
    Typed representation of a sub-workflow invocation step.

    Attributes:
        workflow_id:    ID of the child workflow to execute.
        input_mapping:  Dict mapping child input key → parent variable expression.
                        Expressions follow the ``${steps.<id>.<accessor>}`` syntax
                        resolved by VariableResolver before execution.
        output_key:     Key under which the child's outputs are stored in the
                        parent's ``step_outputs`` registry after execution.
        step_id:        Step identifier in the parent workflow (from ``step["id"]``).
    """

    workflow_id: str
    input_mapping: Dict[str, str] = field(default_factory=dict)
    output_key: str = "sub_workflow_output"
    step_id: str = ""


# ---------------------------------------------------------------------------
# WorkflowFetcher protocol (callable type alias)
# ---------------------------------------------------------------------------

#: Callable that retrieves a workflow definition by ID.
#: Returns a dict with at minimum ``{"steps": [...]}``; may include ``"edges"``.
#: Returns None when the workflow is not found.
WorkflowFetcher = Callable[[str], Dict[str, Any] | None]


# ---------------------------------------------------------------------------
# SubWorkflowExecutor
# ---------------------------------------------------------------------------


class SubWorkflowExecutor:
    """
    Executes a sub-workflow step within a parent workflow execution.

    Responsibilities
    ----------------
    1. Enforce a maximum nesting depth (``MAX_NESTING_DEPTH``) so recursive
       or accidentally cyclic compositions fail loudly rather than overflowing.
    2. Apply ``input_mapping`` — resolve parent variable expressions and build
       the child workflow's input context dict.
    3. Delegate execution to the parent ``WorkflowExecutor`` instance (which
       already holds all agent callbacks and supporting infrastructure).
    4. Wrap the child execution context in a ``StepOutput`` keyed under
       ``output_key`` so parent steps can reference child results via the
       standard ``${steps.<id>.output.*}`` syntax.

    Args:
        workflow_executor:  The parent ``WorkflowExecutor`` instance.  Reused
                            for child execution so circuit breaker, retry, and
                            checkpoint machinery applies uniformly.
        workflow_fetcher:   Callable ``(workflow_id: str) → workflow_dict | None``.
                            Injected to avoid coupling this module to any
                            particular storage backend.
    """

    def __init__(
        self,
        workflow_executor: "WorkflowExecutor",
        workflow_fetcher: WorkflowFetcher,
    ) -> None:
        self._executor = workflow_executor
        self._fetch_workflow = workflow_fetcher

    async def execute(
        self,
        sub_step: SubWorkflowStep,
        parent_context: Dict[str, Any],
        parent_step_outputs: Dict[str, StepOutput],
        current_depth: int = 0,
    ) -> Dict[str, Any]:
        """
        Execute a sub-workflow and return the step result dict.

        The result follows the same shape used by ``_execute_coordinated_step``:
        ``{"success": True/False, "step_id": ..., "sub_workflow_result": {...}}``.

        Args:
            sub_step:            Parsed sub-workflow step descriptor.
            parent_context:      Parent workflow's context dict (forwarded to child).
            parent_step_outputs: Completed step outputs from the parent execution,
                                 used to resolve ``${steps.…}`` references in
                                 ``input_mapping`` values.
            current_depth:       Current nesting depth (0 = top-level call).

        Returns:
            Step result dict with ``success`` bool and ``sub_workflow_result`` key.
        """
        if current_depth >= MAX_NESTING_DEPTH:
            logger.error(
                "Sub-workflow '%s' (step %s): maximum nesting depth %d reached — aborting",
                sub_step.workflow_id,
                sub_step.step_id,
                MAX_NESTING_DEPTH,
            )
            raise RecursionError(
                f"Sub-workflow '{sub_step.workflow_id}' exceeds maximum nesting depth "
                f"of {MAX_NESTING_DEPTH}. Check for circular workflow references."
            )

        logger.info(
            "Sub-workflow step %s: starting child workflow '%s' (depth=%d)",
            sub_step.step_id,
            sub_step.workflow_id,
            current_depth,
        )

        workflow_def = self._fetch_workflow(sub_step.workflow_id)
        if workflow_def is None:
            logger.error(
                "Sub-workflow step %s: workflow '%s' not found",
                sub_step.step_id,
                sub_step.workflow_id,
            )
            raise ValueError(
                f"Sub-workflow step '{sub_step.step_id}': " f"workflow '{sub_step.workflow_id}' not found."
            )

        child_steps: List[Dict[str, Any]] = workflow_def.get("steps", [])
        child_edges: List[Dict[str, Any]] = workflow_def.get("edges", [])

        child_context = self._build_child_context(sub_step, parent_context, parent_step_outputs)

        child_result = await self._executor.execute_coordinated_workflow(
            workflow_id=sub_step.workflow_id,
            steps=child_steps,
            context=child_context,
            edges=child_edges or None,
        )

        success = child_result.get("status") == TaskStatus.COMPLETED.value
        logger.info(
            "Sub-workflow step %s: child '%s' finished — status=%s",
            sub_step.step_id,
            sub_step.workflow_id,
            child_result.get("status"),
        )

        return {
            "success": success,
            "step_id": sub_step.step_id,
            "sub_workflow_result": child_result,
            "output_key": sub_step.output_key,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_child_context(
        self,
        sub_step: SubWorkflowStep,
        parent_context: Dict[str, Any],
        parent_step_outputs: Dict[str, StepOutput],
    ) -> Dict[str, Any]:
        """
        Build the context dict passed to the child workflow.

        Starts from a shallow copy of *parent_context*, then applies
        ``input_mapping`` to inject resolved parent variable values under
        the child's expected input keys.

        Args:
            sub_step:            The sub-workflow step descriptor.
            parent_context:      Parent execution context.
            parent_step_outputs: Parent step outputs for variable resolution.

        Returns:
            Child context dict with mapped inputs merged in.
        """
        child_context: Dict[str, Any] = dict(parent_context)
        child_context["_sub_workflow_inputs"] = {}

        if not sub_step.input_mapping:
            return child_context

        resolver = VariableResolver()
        resolved_inputs: Dict[str, Any] = {}

        for child_key, parent_expr in sub_step.input_mapping.items():
            resolved = resolver.resolve(parent_expr, parent_step_outputs)
            if resolved == parent_expr and "${steps." in parent_expr:
                logger.warning(
                    "Sub-workflow step %s: input_mapping key '%s' — "
                    "expression '%s' could not be resolved; passing raw expression",
                    sub_step.step_id,
                    child_key,
                    parent_expr,
                )
            resolved_inputs[child_key] = resolved
            logger.debug(
                "Sub-workflow step %s: mapped input '%s' = %r",
                sub_step.step_id,
                child_key,
                resolved,
            )

        child_context["_sub_workflow_inputs"] = resolved_inputs
        return child_context


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def is_sub_workflow_step(step: Dict[str, Any]) -> bool:
    """
    Return True when *step* is a sub-workflow invocation step.

    A step qualifies when it carries ``type="sub_workflow"`` and a
    non-empty ``workflow_id`` field.

    Issue #2143.
    """
    return step.get("type") == "sub_workflow" and bool(step.get("workflow_id"))


def extract_sub_workflow_step(step: Dict[str, Any]) -> SubWorkflowStep:
    """
    Parse a raw step dict into a ``SubWorkflowStep`` dataclass.

    Expected step dict shape::

        {
            "id": "invoke_child",
            "type": "sub_workflow",
            "workflow_id": "wf-data-pipeline",
            "input_mapping": {
                "dataset_path": "${steps.fetch.output.path}",
                "threshold": "0.8"
            },
            "output_key": "pipeline_result"
        }

    Raises:
        ValueError: when ``workflow_id`` is absent or empty.

    Issue #2143.
    """
    workflow_id: str = step.get("workflow_id", "")
    if not workflow_id:
        raise ValueError(f"Sub-workflow step '{step.get('id', '<unknown>')}' is missing 'workflow_id'.")

    return SubWorkflowStep(
        workflow_id=workflow_id,
        input_mapping=step.get("input_mapping", {}),
        output_key=step.get("output_key", "sub_workflow_output"),
        step_id=step.get("id", ""),
    )
