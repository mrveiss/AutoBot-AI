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
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from worker_node import WorkerNode


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


# Issue #375: Enhanced search context dataclasses for long parameter list refactoring


@dataclass
class EnhancedSearchQuery:
    """
    Query parameters for enhanced search operations.

    Issue #375: Groups query-related parameters from enhanced_search_v2.

    Attributes:
        query: The search query string
        limit: Maximum results to return
        offset: Pagination offset
        tags: Optional list of tags to filter by
        tags_match_any: If True, match ANY tag; False matches ALL
        exclude_terms: Terms to exclude from results
        require_terms: Terms that must be present
    """

    query: str
    limit: int = 10
    offset: int = 0
    tags: Optional[List[str]] = None
    tags_match_any: bool = False
    exclude_terms: Optional[List[str]] = None
    require_terms: Optional[List[str]] = None


@dataclass
class EnhancedSearchFilters:
    """
    Filter parameters for enhanced search operations.

    Issue #375: Groups filter-related parameters from enhanced_search_v2.

    Attributes:
        category: Optional category filter
        created_after: Filter by creation date (ISO format)
        created_before: Filter by creation date (ISO format)
        exclude_sources: Sources to exclude
        verified_only: Only return verified results
    """

    category: Optional[str] = None
    created_after: Optional[str] = None
    created_before: Optional[str] = None
    exclude_sources: Optional[List[str]] = None
    verified_only: bool = False


@dataclass
class EnhancedSearchOptions:
    """
    Search option parameters for enhanced search operations.

    Issue #375: Groups search option parameters from enhanced_search_v2.

    Attributes:
        mode: Search mode ("semantic", "keyword", "hybrid")
        enable_reranking: Enable cross-encoder reranking
        min_score: Minimum similarity score threshold (0.0-1.0)
        enable_query_expansion: Expand query with synonyms
        enable_relevance_scoring: Apply relevance boosting
        enable_clustering: Cluster results by topic
        track_analytics: Track search analytics
    """

    mode: str = "hybrid"
    enable_reranking: bool = False
    min_score: float = 0.0
    enable_query_expansion: bool = False
    enable_relevance_scoring: bool = False
    enable_clustering: bool = False
    track_analytics: bool = True


@dataclass
class EnhancedSearchContext:
    """
    Complete context for enhanced search operations.

    Issue #375: Combines all search parameters into a single context object,
    reducing the 20-parameter signature of enhanced_search_v2 to 4 parameters.

    Attributes:
        query_params: Query-related parameters
        filters: Filter-related parameters
        options: Search option parameters
        session_id: Session ID for analytics tracking
    """

    query_params: EnhancedSearchQuery
    filters: EnhancedSearchFilters = field(default_factory=EnhancedSearchFilters)
    options: EnhancedSearchOptions = field(default_factory=EnhancedSearchOptions)
    session_id: Optional[str] = None

    @classmethod
    def from_params(
        cls,
        query: str,
        limit: int = 10,
        offset: int = 0,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        tags_match_any: bool = False,
        mode: str = "hybrid",
        enable_reranking: bool = False,
        min_score: float = 0.0,
        enable_query_expansion: bool = False,
        enable_relevance_scoring: bool = False,
        enable_clustering: bool = False,
        track_analytics: bool = True,
        created_after: Optional[str] = None,
        created_before: Optional[str] = None,
        exclude_terms: Optional[List[str]] = None,
        require_terms: Optional[List[str]] = None,
        exclude_sources: Optional[List[str]] = None,
        verified_only: bool = False,
        session_id: Optional[str] = None,
    ) -> "EnhancedSearchContext":
        """
        Create an EnhancedSearchContext from individual parameters.

        This factory method maintains backward compatibility by accepting
        the original 20 parameters and grouping them into the context object.
        """
        return cls(
            query_params=EnhancedSearchQuery(
                query=query,
                limit=limit,
                offset=offset,
                tags=tags,
                tags_match_any=tags_match_any,
                exclude_terms=exclude_terms,
                require_terms=require_terms,
            ),
            filters=EnhancedSearchFilters(
                category=category,
                created_after=created_after,
                created_before=created_before,
                exclude_sources=exclude_sources,
                verified_only=verified_only,
            ),
            options=EnhancedSearchOptions(
                mode=mode,
                enable_reranking=enable_reranking,
                min_score=min_score,
                enable_query_expansion=enable_query_expansion,
                enable_relevance_scoring=enable_relevance_scoring,
                enable_clustering=enable_clustering,
                track_analytics=track_analytics,
            ),
            session_id=session_id,
        )


@dataclass
class SearchResponseContext:
    """
    Context object for building enhanced search responses.

    Issue #375: Replaces 15-parameter signature in _build_enhanced_search_response.
    Groups response-building parameters into logical categories.

    Attributes:
        results: All search results
        unclustered: Unclustered results
        clusters: Clustered results (if enabled)
        query_processed: Processed query string
        mode: Search mode used
        tags: Applied tags filter
        min_score: Minimum score threshold applied
        enable_reranking: Whether reranking was applied
        enable_query_expansion: Whether query expansion was applied
        enable_relevance_scoring: Whether relevance scoring was applied
        enable_clustering: Whether clustering was applied
        queries_count: Number of query variations searched
        duration_ms: Search duration in milliseconds
        offset: Pagination offset
        limit: Pagination limit
    """

    results: List[Dict[str, Any]]
    unclustered: List[Dict[str, Any]]
    clusters: Optional[List[Dict[str, Any]]]
    query_processed: str
    mode: str
    tags: Optional[List[str]]
    min_score: float
    enable_reranking: bool
    enable_query_expansion: bool
    enable_relevance_scoring: bool
    enable_clustering: bool
    queries_count: int
    duration_ms: int
    offset: int
    limit: int


@dataclass
class SearchAnalyticsContext:
    """
    Context object for search analytics tracking.

    Issue #375: Replaces 10-parameter signature in _track_search_analytics.

    Attributes:
        query: Original query string
        result_count: Number of results found
        duration_ms: Search duration in milliseconds
        session_id: Session ID for tracking
        mode: Search mode used
        tags: Tags applied
        category: Category filter applied
        query_expansion: Whether query expansion was enabled
        relevance_scoring: Whether relevance scoring was enabled
        track_analytics: Whether to track analytics
    """

    query: str
    result_count: int
    duration_ms: int
    session_id: Optional[str]
    mode: str
    tags: Optional[List[str]]
    category: Optional[str]
    query_expansion: bool
    relevance_scoring: bool
    track_analytics: bool = True
