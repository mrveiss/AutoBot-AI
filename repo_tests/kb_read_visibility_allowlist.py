# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Data module for ``repo_tests/kb_read_visibility_guard_test.py``'s ``ALLOWLIST`` (#16667).

Every production function that reads knowledge-base facts without applying the
ownership filter, keyed ``(repo-relative file, enclosing function) -> reason``. Reasons:

* ``TRACKED_GAP #NNNN`` -- a real gap; the named #16654 sub-issue removes the entry.
* ``SCOPED`` -- the read is already limited to facts the caller may see by construction.
* ``NOT_USER_FACING`` -- the result never reaches a user or a prompt.
* ``IMPL`` -- the knowledge base reading its own store.
* ``ADMIN_ONLY`` -- a raw read reachable only behind an admin gate (the owner ruled raw
  collection access that bypasses visibility admin-only, #16654). This is a manual
  classification: nothing ties it to the route's ``Depends(check_admin_permission)``, so a
  refactor that drops the gate is not caught here -- re-check it when touching those routes.

THIS MAPPING ONLY SHRINKS. A path that starts filtering must leave in the same PR (the
guard fails on a stale entry), and the guard's ``UNFILTERED_READ_CEILING`` is lowered with
it. That ceiling is checked against the detected reads, not this mapping's length (#16667).
"""

from __future__ import annotations

_T2 = "TRACKED_GAP #16664: puts KB content into a chat, agent or RAG path without the user's scope"
_T3 = "TRACKED_GAP #16665: returns KB facts to an API caller without the caller's scope"
_T4 = "TRACKED_GAP #16666: MCP knowledge access with no user identity (owner: non-private facts only)"
_EXPLORER = (
    "TRACKED_GAP #16666: the raw ChromaDB explorer returns any collection, private facts included, "
    "to any signed-in user; #16689 makes it admin-only"
)
_IMPL_DEDUP = (
    "IMPL: the store path's duplicate check on the KB's own collection; returns an id, never content to a caller"
)
_IMPL_SEARCH = (
    "IMPL: the KB's own vector-search primitive; applying the ownership filter is its callers' job, "
    "and #16664 tracks the callers that skip it"
)
_SUMMARIES = "TRACKED_GAP #16694: raw knowledge_summaries reads served to any signed-in user"
_RAG_CACHE = "TRACKED_GAP #16664: a query-keyed RAG cache shared across users; partition it by visibility scope"
_RAW_ADMIN = "ADMIN_ONLY: raw KB-collection read reachable only behind an admin gate"
_RAW_REPAIR = "NOT_USER_FACING: operator vector-repair CLI; returns row ids and booleans, no fact content"
_RAW_ADMIN_MEMORY = "ADMIN_ONLY: platform-admin user reassignment over the verbatim and trajectory stores, not KB facts"
_CACHE_EVICT = "NOT_USER_FACING: cache eviction reads metadata only"

ALLOWLIST: dict[tuple[str, str], str] = {
    ("autobot-backend/advanced_rag_optimizer.py", "AdvancedRAGOptimizer._perform_semantic_search"): _T2,
    ("autobot-backend/advanced_rag_optimizer.py", "AdvancedRAGOptimizer._retrieve_hybrid_results"): _T2,
    ("autobot-backend/advanced_rag_optimizer.py", "advanced_knowledge_search"): _T2,
    ("autobot-backend/agents/kb_librarian/librarian.py", "KBLibrarian.get_tool_instructions"): _T2,
    ("autobot-backend/agents/kb_librarian/librarian.py", "KBLibrarian.search_tool_knowledge"): _T2,
    ("autobot-backend/agents/kb_librarian_agent.py", "KBLibrarianAgent.search_knowledge"): _T2,
    ("autobot-backend/agents/knowledge_retrieval_agent.py", "KnowledgeRetrievalAgent.find_similar_documents"): _T2,
    ("autobot-backend/agents/knowledge_retrieval_agent.py", "KnowledgeRetrievalAgent.process_query"): _T2,
    ("autobot-backend/ai_hardware_accelerator.py", "AIHardwareAccelerator._gpu_semantic_search"): _T2,
    ("autobot-backend/api/agent.py", "_enhance_context_with_kb"): _T2,
    ("autobot-backend/api/agent.py", "comprehensive_research_task"): _T2,
    ("autobot-backend/api/ai_stack_integration.py", "chat"): _T3,
    ("autobot-backend/api/ai_stack_integration.py", "knowledge_search"): _T3,
    ("autobot-backend/api/ai_stack_integration.py", "rag_query"): _T3,
    ("autobot-backend/api/chat.py", "_enhance_with_knowledge_base"): _T2,
    ("autobot-backend/api/chat.py", "process_chat_message"): _T2,
    ("autobot-backend/api/chat_knowledge.py", "_preserve_single_fact"): _T2,
    ("autobot-backend/api/chat_knowledge_manager.py", "ChatKnowledgeManager.search_chat_knowledge"): _T2,
    (
        "autobot-backend/api/chat_sessions.py",
        "get_share_preview",
    ): "TRACKED_GAP #16671: session fact sharing reads facts through an unwired kb_manager",
    ("autobot-backend/api/knowledge.py", "_get_or_compute_category_counts"): _T3,
    ("autobot-backend/api/knowledge.py", "search_man_pages"): _T3,
    ("autobot-backend/api/knowledge_ai_stack.py", "_search_local_knowledge_base"): _T3,
    ("autobot-backend/api/knowledge_ai_stack.py", "rag_search"): _T3,
    ("autobot-backend/api/knowledge_categories.py", "get_facts_in_category"): _T3,
    ("autobot-backend/api/knowledge_collections.py", "export_collection"): _T3,
    ("autobot-backend/api/knowledge_collections.py", "get_facts_in_collection"): _T3,
    ("autobot-backend/api/knowledge_mcp.py", "mcp_langchain_qa_chain"): _T3,
    ("autobot-backend/api/knowledge_mcp.py", "mcp_search_knowledge_base"): _T3,
    ("autobot-backend/api/knowledge_mcp.py", "mcp_summarize_knowledge_topic"): _T3,
    ("autobot-backend/api/knowledge_mcp.py", "mcp_vector_similarity_search"): _T3,
    ("autobot-backend/api/knowledge_mcp.py", "read_kb_resource"): _T3,
    ("autobot-backend/api/knowledge_metadata.py", "search_by_metadata"): _T3,
    (
        "autobot-backend/api/knowledge_ownership.py",
        "_fetch_fact_details",
    ): "SCOPED: the fact ids come from the caller's own ownership index (#688)",
    (
        "autobot-backend/api/knowledge_ownership.py",
        "get_shared_facts",
    ): "SCOPED: the fact ids come from the caller's own ownership index (#688)",
    ("autobot-backend/api/knowledge_rag.py", "advanced_search"): _T3,
    ("autobot-backend/api/knowledge_relations.py", "get_fact_relations"): _T3,
    ("autobot-backend/api/knowledge_relations.py", "hybrid_search"): _T3,
    ("autobot-backend/api/knowledge_relations.py", "traverse_relations"): _T3,
    ("autobot-backend/api/knowledge_search.py", "_aistack_search"): _T3,
    ("autobot-backend/api/knowledge_search.py", "_execute_kb_search"): _T3,
    ("autobot-backend/api/knowledge_search.py", "_search_with_all_queries"): _T3,
    ("autobot-backend/api/knowledge_search_aggregator.py", "_expand_fact_relations"): _T3,
    ("autobot-backend/api/knowledge_search_aggregator.py", "_get_fact_relations_for_graph"): _T3,
    ("autobot-backend/api/knowledge_search_aggregator.py", "_get_facts_for_graph"): _T3,
    ("autobot-backend/api/knowledge_search_aggregator.py", "_process_relations_for_citations"): _T3,
    ("autobot-backend/api/knowledge_search_aggregator.py", "_search_facts"): _T3,
    ("autobot-backend/api/knowledge_search_aggregator.py", "get_llm_context"): _T3,
    ("autobot-backend/api/knowledge_tags.py", "get_facts_by_tag"): _T3,
    ("autobot-backend/api/knowledge_tags.py", "search_facts_by_tags"): _T3,
    ("autobot-backend/api/knowledge_verification.py", "list_pending_verification"): _T3,
    ("autobot-backend/api/memory_lifecycle.py", "_reinforcement_section"): _T3,
    ("autobot-backend/async_chat_workflow.py", "AsyncChatWorkflow._execute_kb_search"): _T2,
    ("autobot-backend/knowledge/adapters/okf_adapter.py", "OKFAdapter.export_from_kb"): _T3,
    ("autobot-backend/knowledge/search_components/agentic_search.py", "AgenticSearchTool._simple_search"): _T2,
    ("autobot-backend/knowledge/search_components/agentic_search.py", "AgenticSearchTool.iterative_search"): _T2,
    (
        "autobot-backend/knowledge/vector_search_engine.py",
        "_CPUBackend.search",
    ): "IMPL: the KB's own CPU backend calling its vector primitive",
    ("autobot-backend/mcp/autobot_server.py", "AutoBotMCPServer._kb_get_document"): _T4,
    ("autobot-backend/mcp/autobot_server.py", "AutoBotMCPServer._kb_search"): _T4,
    ("autobot-backend/memory/agent_diary.py", "AgentDiaryService.read"): _T2,
    ("autobot-backend/memory/agent_diary.py", "AgentDiaryService.search"): _T2,
    ("autobot-backend/memory/essential_story.py", "EssentialStoryGenerator._fetch_top_facts"): _T2,
    ("autobot-backend/npu_semantic_search.py", "NPUSemanticSearch._handle_search_error"): _T2,
    ("autobot-backend/npu_semantic_search.py", "NPUSemanticSearch._perform_vector_search"): _T2,
    ("autobot-backend/services/cag_service.py", "CAGService.get_full_context"): _T2,
    (
        "autobot-backend/services/claim_classifier.py",
        "ClaimClassifier._search_knowledge_base",
    ): "TRACKED_GAP #16673: un-awaited KB search; scope with #16664 once it runs",
    ("autobot-backend/services/claim_verifier.py", "ClaimVerifier.kb_rag_search"): _T2,
    (
        "autobot-backend/services/command_extraction_service.py",
        "search_commands",
    ): "TRACKED_GAP #16672: dead import; must read with fact visibility once wired",
    ("autobot-backend/services/graph_rag_service.py", "GraphRAGService._perform_initial_rag_search"): _T2,
    ("autobot-backend/services/grounded_agent.py", "GroundedAgent._classify_and_verify_claim"): _T2,
    ("autobot-backend/services/knowledge/service.py", "ChatKnowledgeService._search_filter_and_format"): _T2,
    ("autobot-backend/services/knowledge_base_adapter.py", "KnowledgeBaseAdapter.get_all_facts"): _T2,
    ("autobot-backend/services/knowledge_base_adapter.py", "KnowledgeBaseAdapter.search"): _T2,
    ("autobot-backend/services/rag_service.py", "RAGService._execute_search_with_timeout"): _T2,
    ("autobot-backend/services/rag_service.py", "RAGService._fallback_basic_search"): _T2,
    ("autobot-backend/services/research/orchestrator.py", "_gather_candidate_sources"): _T2,
    ("autobot-backend/services/research/planner.py", "filter_skip_known"): _T2,
    ("autobot-backend/task_handlers/knowledge_base_handlers.py", "KBSearchHandler.execute"): _T2,
    ("autobot-backend/tools/tool_registry.py", "ToolRegistry.get_fact"): _T2,
    ("autobot-backend/tools/tool_registry.py", "ToolRegistry.search_knowledge_base"): _T2,
    ("autobot-backend/utils/hybrid_search.py", "HybridSearchEngine._fallback_semantic_search"): _T2,
    ("autobot-backend/utils/hybrid_search.py", "HybridSearchEngine.explain_search"): _T2,
    ("autobot-backend/utils/hybrid_search.py", "HybridSearchEngine.search"): _T2,
    (
        "autobot-backend/utils/system_validator.py",
        "SystemValidator._validate_kb_integration",
    ): "NOT_USER_FACING: a health check that only times a probe query",
    (
        "autobot-infrastructure/shared/mcp/tools/knowledge-base-mcp/autobot_knowledge_mcp/embedded.py",
        "EmbeddedKnowledgeClient.search",
    ): _T4,
    # --- raw ChromaDB reads on KB-content collections (#16667 part 3, classified 2026-09-14) ---
    ("autobot-backend/api/knowledge_chroma.py", "list_documents"): _EXPLORER,
    ("autobot-backend/api/knowledge_chroma.py", "search_collection"): _EXPLORER,
    ("autobot-backend/knowledge/facts.py", "FactsMixin._find_duplicate"): _IMPL_DEDUP,
    ("autobot-backend/knowledge/search.py", "SearchMixin._query_chromadb"): _IMPL_SEARCH,
    ("autobot-backend/api/knowledge_maintenance.py", "_fetch_all_chunks._load"): _RAW_ADMIN,
    ("autobot-backend/api/knowledge_vectorization.py", "_fetch_chunks_by_ids"): _RAW_ADMIN,
    ("autobot-backend/api/knowledge_vectorization.py", "_fetch_unenriched_ids"): _RAW_ADMIN,
    ("autobot-backend/knowledge/summary_search.py", "SummarySearchService.search_summaries"): _SUMMARIES,
    ("autobot-backend/knowledge/summary_search.py", "SummarySearchService.get_document_overview"): _SUMMARIES,
    ("autobot-backend/knowledge/summary_search.py", "SummarySearchService.drill_down"): _SUMMARIES,
    ("autobot-backend/knowledge/vector_repair.py", "scan_poisoned_rows"): _RAW_REPAIR,
    ("autobot-backend/knowledge/vector_repair.py", "has_reachable_vector"): _RAW_REPAIR,
    ("autobot-backend/memory/ownership_reassign.py", "_reassign_kb_facts_chroma"): _RAW_ADMIN,
    ("autobot-backend/memory/ownership_reassign.py", "_reassign_chroma_store"): _RAW_ADMIN_MEMORY,
    ("autobot-backend/services/semantic_query_cache.py", "SemanticQueryCache.lookup"): _RAG_CACHE,
    ("autobot-backend/services/semantic_query_cache.py", "SemanticQueryCache._maybe_evict"): _CACHE_EVICT,
    ("autobot-backend/services/semantic_query_cache.py", "SemanticQueryCache.clear"): _RAW_ADMIN,
    ("autobot-backend/services/topic_retrieval_cache.py", "TopicRetrievalCache.lookup"): _RAG_CACHE,
    ("autobot-backend/services/topic_retrieval_cache.py", "TopicRetrievalCache._maybe_evict"): _CACHE_EVICT,
}
