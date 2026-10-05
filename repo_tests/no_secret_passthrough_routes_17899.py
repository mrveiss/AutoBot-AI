# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Routes the response-model secret guard CANNOT rule on (#17899).

Every entry is a route whose `response_model` declares no fields and permits
extras, so the guard's matcher has nothing to match. **This is not a waiver
list and not a violation list.** It is the set the guard has told us it cannot
see, written down so that "found no secret" and "could not look" stop being
the same green.

Why a record at all, rather than a plain failure: 174 routes carry this shape
today, so failing on all of them would make the guard unrunnable and it would
be switched off within the day. The record freezes what existed when the third
verdict landed; ``no_secret_passthrough_model_17899_test.py`` fails on a route
that is NOT in here, so a NEW pass-through response model cannot land unseen.

IT ONLY SHRINKS. An entry leaves when the route's model declares its fields —
at which point the guard can finally rule on it, and the existing violation
test does. Never add an entry to quiet a new route; declare the fields.

Keyed by ``(file, "METHOD /path", model)`` and NOT by line number: a line
number moves whenever anything above the decorator is edited, which would turn
every unrelated change into a re-freeze and train the reader to stop looking.

The four ``autobot-backend/api/llm.py`` entries in
``no_secret_in_response_model_baseline_17865.py`` describe the same route from
the other side: those came from the index merging two same-named classes
(#17935), not from anybody observing the response. This record is the honest
statement about that route.
"""

from __future__ import annotations

PASSTHROUGH_ROUTES: frozenset[tuple[str, str, str]] = frozenset(
    {
        ("autobot-backend/api/a2a.py", "GET /agent-card", "A2AAgentCardResponse"),
        ("autobot-backend/api/a2a.py", "GET /capabilities", "A2ACapabilitiesResponse"),
        ("autobot-backend/api/a2a.py", "POST /capabilities/verify", "A2ACapabilitiesResponse"),
        (
            "autobot-backend/api/advanced_control.py",
            "GET /streaming/capabilities",
            "AdvancedControlStreamingCapabilitiesResponse",
        ),
        (
            "autobot-backend/api/advanced_control.py",
            "GET /takeover/status",
            "AdvancedControlTakeoverSystemStatusResponse",
        ),
        ("autobot-backend/api/analytics.py", "GET /communication/patterns", "AnalyticsCommunicationPatternsResponse"),
        (
            "autobot-backend/api/analytics.py",
            "GET /dashboard/overview/status/{task_id}",
            "AnalyticsDashboardStatusResponse",
        ),
        ("autobot-backend/api/analytics.py", "GET /realtime/metrics", "AnalyticsRealtimeMetricsResponse"),
        ("autobot-backend/api/analytics.py", "GET /root-cause/{task_id}", "AnalyticsRootCauseResponse"),
        ("autobot-backend/api/analytics.py", "GET /status", "AnalyticsStatusResponse"),
        ("autobot-backend/api/analytics.py", "GET /system/health-detailed", "AnalyticsDetailedHealthResponse"),
        ("autobot-backend/api/analytics.py", "GET /trends/historical", "AnalyticsHistoricalTrendsResponse"),
        ("autobot-backend/api/analytics_agents.py", "GET /comparison", "AgentComparisonResponse"),
        ("autobot-backend/api/analytics_agents.py", "GET /trends", "AgentPerformanceTrendsResponse"),
        ("autobot-backend/api/analytics_behavior.py", "GET /engagement", "BehaviorEngagementResponse"),
        ("autobot-backend/api/analytics_behavior.py", "GET /features", "BehaviorFeatureMetricsResponse"),
        ("autobot-backend/api/analytics_behavior.py", "GET /features/comparison", "BehaviorFeatureComparisonResponse"),
        ("autobot-backend/api/analytics_behavior.py", "GET /stats/daily", "BehaviorDailyStatsResponse"),
        ("autobot-backend/api/analytics_behavior.py", "GET /stats/heatmap", "BehaviorHeatmapResponse"),
        ("autobot-backend/api/analytics_behavior.py", "GET /stats/peak", "BehaviorPeakUsageResponse"),
        ("autobot-backend/api/analytics_behavior.py", "GET /summary", "BehaviorSummaryResponse"),
        ("autobot-backend/api/analytics_bug_prediction.py", "GET /heatmap", "BugPredictionHeatmapResponse"),
        ("autobot-backend/api/analytics_bug_prediction.py", "GET /status/{task_id}", "BugPredictionStatusResponse"),
        ("autobot-backend/api/analytics_bug_prediction.py", "GET /summary", "BugPredictionSummaryResponse"),
        ("autobot-backend/api/analytics_bug_prediction.py", "GET /trends", "BugPredictionTrendsResponse"),
        (
            "autobot-backend/api/analytics_code.py",
            "GET /code/communication-chains",
            "AnalyticsCodeCommunicationChainsResponse",
        ),
        ("autobot-backend/api/analytics_code.py", "GET /code/quality-metrics", "AnalyticsCodeQualityMetricsResponse"),
        (
            "autobot-backend/api/analytics_code.py",
            "POST /code/analyze/communication-chains",
            "AnalyticsCodeCommunicationChainsResponse",
        ),
        ("autobot-backend/api/analytics_code_generation.py", "GET /stats", "CodeGenerationStatsResponse"),
        ("autobot-backend/api/analytics_code_review.py", "GET /review/{review_id}", "CodeReviewReviewByIdResponse"),
        ("autobot-backend/api/analytics_continuous_learning.py", "GET /status", "ContinuousLearningStatusResponse"),
        (
            "autobot-backend/api/analytics_continuous_learning.py",
            "POST /feedback",
            "ContinuousLearningFeedbackResponse",
        ),
        ("autobot-backend/api/analytics_continuous_learning.py", "POST /retrain", "ContinuousLearningRetrainResponse"),
        ("autobot-backend/api/analytics_continuous_learning.py", "POST /start", "ContinuousLearningStartStopResponse"),
        ("autobot-backend/api/analytics_continuous_learning.py", "POST /stop", "ContinuousLearningStartStopResponse"),
        ("autobot-backend/api/analytics_conversation.py", "GET /bottlenecks", "ConversationBottlenecksResponse"),
        ("autobot-backend/api/analytics_conversation.py", "GET /distribution", "ConversationDistributionResponse"),
        ("autobot-backend/api/analytics_conversation.py", "GET /flows", "ConversationFlowsResponse"),
        ("autobot-backend/api/analytics_conversation.py", "GET /intents", "ConversationIntentsResponse"),
        ("autobot-backend/api/analytics_cost.py", "GET /by-agent/{agent_id}", "SingleAgentCostResponse"),
        ("autobot-backend/api/analytics_cost.py", "GET /by-agent/{agent_id}/budget", "AgentBudgetStatusResponse"),
        ("autobot-backend/api/analytics_cost.py", "PUT /by-agent/{agent_id}/budget", "AgentBudgetSetResponse"),
        ("autobot-backend/api/analytics_log_patterns.py", "GET /hotspots", "LogPatternHotspotsResponse"),
        ("autobot-backend/api/analytics_log_patterns.py", "GET /pattern/{pattern_id}", "LogPatternDetailResponse"),
        ("autobot-backend/api/analytics_log_patterns.py", "GET /realtime", "LogPatternRealtimeResponse"),
        ("autobot-backend/api/analytics_log_patterns.py", "GET /stats", "LogPatternStatsResponse"),
        ("autobot-backend/api/analytics_maintenance.py", "GET /dashboard", "MaintenanceDashboardResponse"),
        ("autobot-backend/api/analytics_maintenance.py", "GET /report/executive", "MaintenanceCustomReportResponse"),
        ("autobot-backend/api/analytics_maintenance.py", "POST /report", "MaintenanceCustomReportResponse"),
        ("autobot-backend/api/analytics_pattern_learning.py", "POST /feedback", "PatternLearningFeedbackResponse"),
        ("autobot-backend/api/analytics_pattern_learning.py", "POST /learn", "PatternLearningLearnCycleResponse"),
        ("autobot-backend/api/analytics_pattern_learning.py", "POST /patterns", "PatternLearningRegisterResponse"),
        ("autobot-backend/api/analytics_performance.py", "GET /categories", "PerformanceCategoriesResponse"),
        ("autobot-backend/api/analytics_performance.py", "GET /history", "PerformanceHistoryResponse"),
        ("autobot-backend/api/analytics_performance.py", "GET /hotspots", "PerformanceHotspotsResponse"),
        ("autobot-backend/api/analytics_performance.py", "GET /patterns", "PerformancePatternsListResponse"),
        (
            "autobot-backend/api/analytics_performance.py",
            "GET /patterns/{pattern_id}",
            "PerformancePatternDetailResponse",
        ),
        ("autobot-backend/api/analytics_performance.py", "POST /analyze-content", "PerformanceAnalyzeContentResponse"),
        ("autobot-backend/api/analytics_quality.py", "GET /complexity", "QualityComplexityResponse"),
        ("autobot-backend/api/analytics_quality.py", "GET /drill-down/{category}", "QualityDrillDownResponse"),
        ("autobot-backend/api/analytics_quality.py", "GET /health-score", "QualityHealthScoreResponse"),
        ("autobot-backend/api/analytics_quality.py", "GET /metrics", "QualityMetricsResponse"),
        ("autobot-backend/api/analytics_quality.py", "GET /patterns", "QualityPatternsResponse"),
        ("autobot-backend/api/analytics_quality.py", "GET /snapshot", "QualitySnapshotResponse"),
        ("autobot-backend/api/analytics_quality.py", "GET /trends", "QualityTrendsResponse"),
        ("autobot-backend/api/code_search.py", "DELETE /cache", "CodeSearchCacheClearResultResponse"),
        ("autobot-backend/api/code_search.py", "GET /search", "CodeSearchGetResponse"),
        ("autobot-backend/api/code_search.py", "POST /index", "CodeSearchIndexResultResponse"),
        ("autobot-backend/api/embeddings.py", "GET /models", "EmbeddingModelsData"),
        ("autobot-backend/api/embeddings.py", "GET /settings", "EmbeddingSettingsData"),
        ("autobot-backend/api/embeddings.py", "GET /status", "EmbeddingStatusData"),
        ("autobot-backend/api/embeddings.py", "POST /providers/{provider_name}/refresh-models", "EmbeddingRefreshData"),
        ("autobot-backend/api/embeddings.py", "PUT /settings", "EmbeddingUpdateData"),
        ("autobot-backend/api/error_resilience.py", "GET /circuit-breakers", "CircuitBreakerStatusResponse"),
        ("autobot-backend/api/error_resilience.py", "GET /error-budgets", "ErrorBudgetStatusResponse"),
        ("autobot-backend/api/integration_cicd.py", "GET /{provider}/pipelines", "CICDPipelinesResponse"),
        (
            "autobot-backend/api/integration_cicd.py",
            "GET /{provider}/pipelines/{pipeline_id}/logs",
            "CICDPipelineLogsResponse",
        ),
        (
            "autobot-backend/api/integration_cicd.py",
            "GET /{provider}/pipelines/{pipeline_id}/status",
            "CICDPipelineStatusResponse",
        ),
        (
            "autobot-backend/api/integration_cicd.py",
            "POST /{provider}/pipelines/{pipeline_id}/trigger",
            "CICDPipelineTriggerResponse",
        ),
        ("autobot-backend/api/integration_cloud.py", "GET /{provider}/account", "CloudAccountInfoResponse"),
        ("autobot-backend/api/integration_cloud.py", "GET /{provider}/resources", "CloudResourcesResponse"),
        ("autobot-backend/api/integration_cloud.py", "GET /{provider}/storage", "CloudStorageResponse"),
        (
            "autobot-backend/api/integration_database.py",
            "POST /mongodb/query-collection",
            "IntegrationMongoQueryResponse",
        ),
        (
            "autobot-backend/api/integration_database.py",
            "POST /test-connection",
            "IntegrationDatabaseConnectionTestResponse",
        ),
        (
            "autobot-backend/api/integration_database.py",
            "POST /{provider}/databases",
            "IntegrationDatabaseListResponse",
        ),
        ("autobot-backend/api/integration_database.py", "POST /{provider}/query", "IntegrationDatabaseQueryResponse"),
        ("autobot-backend/api/integration_database.py", "POST /{provider}/tables", "IntegrationTablesListResponse"),
        ("autobot-backend/api/integration_github.py", "GET /{owner}/{repo}", "GitHubRepositoryResponse"),
        ("autobot-backend/api/integration_github.py", "GET /{owner}/{repo}/commits", "GitHubCommitsResponse"),
        ("autobot-backend/api/integration_github.py", "GET /{owner}/{repo}/commits/{ref}", "GitHubCommitResponse"),
        (
            "autobot-backend/api/integration_github.py",
            "GET /{owner}/{repo}/contents/{path:path}",
            "GitHubFileContentsResponse",
        ),
        ("autobot-backend/api/integration_github.py", "GET /{owner}/{repo}/issues", "GitHubIssuesResponse"),
        (
            "autobot-backend/api/integration_github.py",
            "GET /{owner}/{repo}/issues/{issue_number}",
            "GitHubIssueResponse",
        ),
        (
            "autobot-backend/api/integration_github.py",
            "GET /{owner}/{repo}/pull-requests",
            "GitHubPullRequestsResponse",
        ),
        (
            "autobot-backend/api/integration_github.py",
            "GET /{owner}/{repo}/pull-requests/{pull_number}",
            "GitHubPullRequestResponse",
        ),
        (
            "autobot-backend/api/integration_github.py",
            "GET /{owner}/{repo}/pull-requests/{pull_number}/comments",
            "GitHubPRCommentsResponse",
        ),
        (
            "autobot-backend/api/integration_github.py",
            "GET /{owner}/{repo}/pull-requests/{pull_number}/diff",
            "GitHubPullRequestDiffResponse",
        ),
        (
            "autobot-backend/api/integration_github.py",
            "GET /{owner}/{repo}/tree/{tree_sha}",
            "GitHubRepositoryTreeResponse",
        ),
        (
            "autobot-backend/api/integration_github.py",
            "POST /{owner}/{repo}/pull-requests/{pull_number}/comments",
            "GitHubPRCommentResponse",
        ),
        (
            "autobot-backend/api/integration_github.py",
            "POST /{owner}/{repo}/pull-requests/{pull_number}/reviews",
            "GitHubPRReviewResponse",
        ),
        ("autobot-backend/api/integration_monitoring.py", "GET /{provider}/alerts", "MonitoringAlertsResponse"),
        ("autobot-backend/api/integration_monitoring.py", "GET /{provider}/hosts", "MonitoringHostsResponse"),
        ("autobot-backend/api/integration_monitoring.py", "POST /{provider}/events", "MonitoringEventsResponse"),
        ("autobot-backend/api/integration_monitoring.py", "POST /{provider}/metrics", "MonitoringMetricsResponse"),
        ("autobot-backend/api/integration_project_management.py", "GET /{provider}/issues", "PMIssuesResponse"),
        ("autobot-backend/api/integration_project_management.py", "GET /{provider}/projects", "PMProjectsResponse"),
        ("autobot-backend/api/integration_project_management.py", "GET /{provider}/search", "PMIssueSearchResponse"),
        (
            "autobot-backend/api/integration_project_management.py",
            "PATCH /{provider}/issues/{issue_id}",
            "PMIssueUpdateResponse",
        ),
        ("autobot-backend/api/integration_project_management.py", "POST /{provider}/issues", "PMIssueCreateResponse"),
        (
            "autobot-backend/api/integration_version_control.py",
            "GET /{provider}/repositories",
            "VCSRepositoriesResponse",
        ),
        (
            "autobot-backend/api/integration_version_control.py",
            "GET /{provider}/repositories/{repo_id}/branches",
            "VCSBranchesResponse",
        ),
        (
            "autobot-backend/api/integration_version_control.py",
            "GET /{provider}/repositories/{repo_id}/commits",
            "VCSCommitInfoResponse",
        ),
        (
            "autobot-backend/api/integration_version_control.py",
            "GET /{provider}/repositories/{repo_id}/pull-requests",
            "VCSPullRequestsResponse",
        ),
        ("autobot-backend/api/knowledge_ai_stack.py", "GET /ai-stack/stats", "AIStackStatsData"),
        ("autobot-backend/api/knowledge_ai_stack.py", "GET /health/status", "AIStackHealthStatusData"),
        ("autobot-backend/api/knowledge_ai_stack.py", "GET /system/insights", "AIStackSystemInsightsData"),
        ("autobot-backend/api/knowledge_ai_stack.py", "POST /analyze/documents", "AIStackDocumentAnalysisData"),
        ("autobot-backend/api/knowledge_ai_stack.py", "POST /query/reformulate", "AIStackQueryReformulateData"),
        ("autobot-backend/api/knowledge_ai_stack.py", "POST /search/rag", "AIStackRagSearchData"),
        ("autobot-backend/api/knowledge_ai_stack_extraction.py", "POST /extract", "AIStackKnowledgeExtractData"),
        (
            "autobot-backend/api/knowledge_graph_routes.py",
            "GET /documents/{document_id}/overview",
            "KnowledgeGraphDocumentOverviewResponse",
        ),
        (
            "autobot-backend/api/knowledge_graph_routes.py",
            "GET /summaries/{summary_id}/drill-down",
            "KnowledgeGraphDrillDownResponse",
        ),
        ("autobot-backend/api/llm.py", "GET /config", "LLMConfigResponse"),
        (
            "autobot-backend/api/llm_optimization.py",
            "GET /models/performance/history/{model_name}",
            "LLMModelPerformanceHistoryResponse",
        ),
        ("autobot-backend/api/logs.py", "GET /list", "LogFileMetadata"),
        ("autobot-backend/api/long_running_operations.py", "GET /{operation_id}", "LongRunningOperationStatusResponse"),
        ("autobot-backend/api/manual_mcp.py", "GET /mcp/tools", "ManualMCPToolItem"),
        ("autobot-backend/api/memory.py", "DELETE /entities/orphans", "MemoryOrphanCleanupResponse"),
        ("autobot-backend/api/memory.py", "DELETE /entities/{entity_id}", "MemoryDeleteEntityResponse"),
        ("autobot-backend/api/memory.py", "DELETE /relations", "MemoryDeleteRelationResponse"),
        ("autobot-backend/api/memory.py", "GET /entities", "MemoryEntityData"),
        ("autobot-backend/api/memory.py", "GET /entities/all", "MemoryEntityListResponse"),
        ("autobot-backend/api/memory.py", "GET /entities/orphans", "MemoryOrphanScanResponse"),
        ("autobot-backend/api/memory.py", "GET /entities/{entity_id}/relations", "MemoryRelatedEntitiesResponse"),
        ("autobot-backend/api/memory.py", "GET /graph", "MemoryEntityGraphData"),
        ("autobot-backend/api/memory.py", "PATCH /entities/{entity_id}/invalidate", "MemoryEntityInvalidateResponse"),
        ("autobot-backend/api/memory.py", "PATCH /entities/{entity_id}/observations", "MemoryEntityData"),
        ("autobot-backend/api/memory.py", "PATCH /relations/invalidate", "MemoryRelationInvalidateResponse"),
        ("autobot-backend/api/memory.py", "POST /entities", "MemoryEntityData"),
        ("autobot-backend/api/memory.py", "POST /relations", "MemoryRelationData"),
        ("autobot-backend/api/multimodal.py", "GET /performance/stats", "MultimodalPerfStatsData"),
        ("autobot-backend/api/multimodal.py", "GET /performance/summary", "MultimodalPerfSummaryData"),
        ("autobot-backend/api/multimodal.py", "GET /stats", "MultimodalStatsData"),
        ("autobot-backend/api/multimodal.py", "POST /embeddings/generate", "MultimodalEmbeddingData"),
        ("autobot-backend/api/multimodal.py", "POST /fusion/combine", "MultimodalFusionData"),
        ("autobot-backend/api/multimodal.py", "POST /performance/batch-size", "MultimodalBatchSizeData"),
        ("autobot-backend/api/multimodal.py", "POST /performance/optimize", "MultimodalOptimizeData"),
        ("autobot-backend/api/playwright.py", "POST /back", "PlaywrightBrowserActionResponse"),
        ("autobot-backend/api/playwright.py", "POST /forward", "PlaywrightBrowserActionResponse"),
        ("autobot-backend/api/playwright.py", "POST /interact", "PlaywrightBrowserActionResponse"),
        ("autobot-backend/api/playwright.py", "POST /navigate", "PlaywrightBrowserActionResponse"),
        ("autobot-backend/api/playwright.py", "POST /reload", "PlaywrightBrowserActionResponse"),
        ("autobot-backend/api/playwright.py", "POST /worker-screenshot", "PlaywrightBrowserActionResponse"),
        ("autobot-backend/api/prometheus_mcp.py", "POST /mcp/{tool_name}", "PrometheusMCPExecuteResponse"),
        ("autobot-backend/api/registry.py", "GET /router/{router_name}", "RegistryRouterDetailResponse"),
        ("autobot-backend/api/registry.py", "GET /routers", "RegistryRoutersResponse"),
        ("autobot-backend/api/sandbox.py", "GET /examples", "SandboxExamplesResponse"),
        ("autobot-backend/api/sandbox.py", "GET /security-levels", "SandboxSecurityLevelsResponse"),
        ("autobot-backend/api/sandbox.py", "GET /stats", "SandboxStatsResponse"),
        ("autobot-backend/api/sandbox.py", "POST /execute", "SandboxExecutionResponse"),
        ("autobot-backend/api/sandbox.py", "POST /execute/batch", "SandboxExecutionResponse"),
        ("autobot-backend/api/sandbox.py", "POST /execute/script", "SandboxExecutionResponse"),
        ("autobot-backend/api/sequential_thinking_mcp.py", "GET /mcp/tools", "SequentialThinkingMCPToolsResponse"),
        ("autobot-backend/api/services.py", "GET /services/health", "ServicesHealthAggregateResponse"),
        ("autobot-backend/api/skills.py", "GET /{name}", "SkillDetailResponse"),
        ("autobot-backend/api/skills.py", "GET /{name}/health", "SkillHealthResponse"),
        ("autobot-backend/api/skills.py", "GET /{name}/metrics", "SkillMetricsResponse"),
        ("autobot-backend/api/skills.py", "GET /{name}/suggestions", "SkillSuggestionsResponse"),
        ("autobot-backend/api/skills.py", "POST /initialize", "SkillsInitializeResponse"),
        ("autobot-backend/api/system.py", "GET /api/cache/stats", "SystemCacheCoordinatorStatsResponse"),
        ("autobot-backend/api/terminal.py", "GET /stats", "TerminalStatsResponse"),
        ("autobot-backend/api/usage.py", "GET /by-user/{user_id}", "UsageByUserSingleResponse"),
        ("autobot-backend/api/usage.py", "GET /me", "UsageMyUsageResponse"),
        ("autobot-backend/api/voice.py", "POST /voices/create", "VoiceCreateResponse"),
    }
)

#: Frozen count. It may only go DOWN. Raising it is never correct: a new
#: pass-through route means the model should declare its fields, not that the
#: guard should stop asking.
PASSTHROUGH_FROZEN_AT = 174

#: Routes the sweep INDEXES, which is its reach. A floor, not a target: a
#: detector that broke and found nothing would otherwise report an empty
#: unverifiable set, which reads exactly like "every route is auditable"
#: (MEASUREMENT_DISCIPLINE.md).
#:
#: BOUND TO REACH, NOT TO FINDINGS (CodeRabbit, #17899). This was
#: `MIN_PASSTHROUGH_FILES = 35`, measured against the files that produced a
#: finding -- 48 today. Two things were wrong with that. Draining the findings
#: by FIXING the routes would have driven 48 below 35 and failed the guard as
#: "a broken detector reported as a clean tree", so the guard punished the
#: repair it exists to prompt. And a detector that silently stopped parsing
#: most of the tree could still clear a floor of 35 on a handful of findings.
#: Reach today is 5075 files parsed / 2766 routes indexed, so the floor sits
#: well below it and only a real collapse of the sweep trips it.
MIN_ROUTES_INDEXED = 2000
