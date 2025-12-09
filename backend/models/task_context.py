# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Task Execution Context Models

Issue #322: Created to eliminate data clump patterns in task handlers.
These dataclasses encapsulate groups of parameters that are frequently
passed together, improving code maintainability and type safety.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from src.worker_node import WorkerNode


@dataclass
class TaskExecutionContext:
    """
    Context object for task execution.

    Encapsulates the common parameters passed to task handlers,
    eliminating the data clump anti-pattern where worker, task_payload,
    user_role, and task_id were passed separately to multiple methods.

    Issue #322: Replaces 4-parameter signatures across 21+ task handler methods.

    Attributes:
        worker: The WorkerNode instance providing access to modules and security
        task_payload: The task data including all parameters
        user_role: The user role for permission checks and audit logging
        task_id: The unique task identifier for tracking and audit
        metadata: Optional additional metadata for the task execution
    """

    worker: "WorkerNode"
    task_payload: Dict[str, Any]
    user_role: str
    task_id: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def security_layer(self):
        """Convenience accessor for worker's security layer."""
        return self.worker.security_layer

    def audit_log(
        self,
        action: str,
        status: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Log an audit event using the context's security layer.

        Args:
            action: The action being logged (e.g., 'execute_shell_command')
            status: The status of the action (e.g., 'success', 'failure', 'blocked')
            details: Additional details to include in the audit log
        """
        log_details = {"task_id": self.task_id, **(details or {})}
        self.worker.security_layer.audit_log(
            action, self.user_role, status, log_details
        )

    def get_payload_value(self, key: str, default: Any = None) -> Any:
        """
        Safely get a value from the task payload.

        Args:
            key: The key to retrieve from task_payload
            default: Default value if key is not found

        Returns:
            The value from task_payload or the default
        """
        return self.task_payload.get(key, default)

    def require_payload_value(self, key: str) -> Any:
        """
        Get a required value from the task payload.

        Args:
            key: The key to retrieve from task_payload

        Returns:
            The value from task_payload

        Raises:
            KeyError: If the key is not present in task_payload
        """
        if key not in self.task_payload:
            raise KeyError(f"Required key '{key}' not found in task_payload")
        return self.task_payload[key]


@dataclass
class WorkflowStepContext:
    """
    Context object for workflow step execution.

    Issue #322: Replaces 4-parameter signatures in workflow step handlers.

    Attributes:
        workflow_id: The unique workflow identifier
        step: The workflow step being executed
        orchestrator: The orchestrator instance managing the workflow
        action: The action to perform in this step
        metadata: Optional additional metadata
    """

    workflow_id: str
    step: Any  # WorkflowStep type
    orchestrator: Any  # Orchestrator instance
    action: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class JudgmentContext:
    """
    Context object for judgment/arbitration operations.

    Issue #322: Replaces 4-parameter signatures in judge classes.

    Attributes:
        subject: The subject being judged
        criteria: The criteria for judgment
        alternatives: The alternatives being evaluated
        context: Additional context for the judgment
        metadata: Optional additional metadata
    """

    subject: str
    criteria: Dict[str, Any]
    alternatives: list
    context: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SecurityCheckContext:
    """
    Context object for security policy checks.

    Issue #322: Replaces 3-parameter signatures in security policy methods.

    Attributes:
        policy: The security policy being checked
        context: The context for the security check
        result: The result object to populate
        metadata: Optional additional metadata
    """

    policy: Dict[str, Any]
    context: Dict[str, Any]
    result: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FactContentContext:
    """
    Context object for knowledge fact storage operations.

    Issue #322: Replaces 3-parameter signatures in knowledge fact methods.

    Attributes:
        fact_id: The unique identifier for the fact
        content: The content of the fact
        metadata: Metadata associated with the fact
        embedding: Optional embedding vector for the fact
    """

    fact_id: str
    content: str
    metadata: Dict[str, Any]
    embedding: Optional[list] = None


@dataclass
class DataFlowContext:
    """
    Context object for data flow analysis operations.

    Issue #322: Replaces 3-parameter signatures in DFA analysis methods.

    Attributes:
        expr: The AST expression node being analyzed
        target_var: The target variable name
        target_line: The target line number
        metadata: Optional additional metadata
    """

    expr: Any  # ast.expr type
    target_var: str
    target_line: int
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AuditQueryContext:
    """
    Context object for audit log query operations.

    Issue #322: Replaces 4-parameter signatures in audit query methods.
    Used by _query_session, _query_user, _query_operation, _query_vm,
    _query_result, _query_user_operation, _query_time_range methods.

    Attributes:
        start_time: Start of the time range for the query
        end_time: End of the time range for the query
        limit: Maximum number of results to return
        offset: Number of results to skip (for pagination)
    """

    start_time: Any  # datetime
    end_time: Any  # datetime
    limit: int
    offset: int = 0


@dataclass
class ConnectionCredentials:
    """
    Context object for SSH/remote connection credentials.

    Issue #322: Replaces 5-parameter signatures in SSH connection methods.

    Attributes:
        host: Remote host address
        port: Connection port (default 22 for SSH)
        username: Authentication username
        key_path: Path to SSH key file
        passphrase: Optional passphrase for the key
    """

    host: str
    port: int = 22
    username: str = "autobot"
    key_path: str = "~/.ssh/autobot_key"
    passphrase: Optional[str] = None

    def get_pool_key(self) -> str:
        """Generate a unique key for connection pooling."""
        return f"{self.host}:{self.port}:{self.username}"


@dataclass
class SearchQueryContext:
    """
    Context object for search operations.

    Issue #322: Replaces 4-parameter signatures in search methods.

    Attributes:
        query: The search query string
        max_results: Maximum number of results to return
        enable_reranking: Whether to enable result reranking
        timeout: Optional timeout for the search operation
        score_threshold: Minimum score threshold for results
    """

    query: str
    max_results: int = 10
    enable_reranking: bool = True
    timeout: Optional[float] = None
    score_threshold: float = 0.0
