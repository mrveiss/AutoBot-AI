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

_T2 = (
    "TRACKED_GAP #16654: puts KB content into a chat, agent or RAG path without the user's scope "
    "(#16664 is closed; the parent's AC1 covers every remaining production path)"
)
_T4 = (
    "TRACKED_GAP #16654: MCP knowledge access with no user identity (owner: non-private facts only); "
    "#16666 is closed, the parent's AC1 covers the rest"
)
_MCP_NON_PRIVATE = (
    "SCOPED: the stdio/token MCP server has no user, so it reads non-private facts only "
    "(non_private_where on the query and filter_non_private_results on the hits; owner ruling on #16654, #16666)"
)
_EXPLORER = (
    "ADMIN_ONLY: the raw ChromaDB explorer returns any collection by name; every route of "
    "api/knowledge_chroma.py carries Depends(check_admin_permission) (#16689), and quarantined rows are audited"
)
_IMPL_DEDUP = (
    "IMPL: the store path's duplicate check on the KB's own collection; returns an id, never content to a caller"
)
_IMPL_SEARCH = (
    "IMPL: the KB's own vector-search primitive; applying the ownership filter is its callers' job, "
    "and #16654 AC1 tracks the callers that skip it"
)
_SUMMARIES = (
    "SCOPED: the service's only callers are the summary routes in api/knowledge_graph_routes.py, which pass every "
    "summary through knowledge.summary_visibility (the source fact's canonical visibility, fail closed) (#16665)"
)
_RAG_CACHE = (
    "SCOPED: a RAG cache lookup restricted by a ChromaDB where on the caller's visibility scope key "
    "(sha256 of user, org, groups and the kb:acl_epoch), and its hit is post-filtered by RAGService (#16664, landed)"
)
_RAW_ADMIN = "ADMIN_ONLY: raw KB-collection read reachable only behind an admin gate"
_RAW_ADMIN_NO_QUARANTINE = (
    "ADMIN_ONLY: the reindex job feeds chunk text to an LLM, so it reads through "
    "knowledge.quarantine.without_quarantine -- a research-quarantined chunk is never enriched (#19163)"
)
_ORPHAN_REPAIR = (
    "ADMIN_ONLY: #16927 orphan-repair reads a fact's own metadata to judge/reassign it; "
    "reachable only through api/admin_orphan_repair.py's router-level "
    'Depends(require_role("admin", "superadmin"))'
)
_RAW_REPAIR = "NOT_USER_FACING: operator vector-repair CLI; returns row ids and booleans, no fact content"
_RAW_ADMIN_MEMORY = "ADMIN_ONLY: platform-admin user reassignment over the verbatim and trajectory stores, not KB facts"
_CACHE_EVICT = "NOT_USER_FACING: cache eviction reads metadata only"
_WATCH_RECONCILE = (
    "NOT_USER_FACING: the watch folder resolving its own filesystem state against the KB. "
    "It runs from a filesystem observer with no user in context, returns fact ids, counts and a "
    "status -- never fact content -- and a visibility filter would make it WRONG rather than "
    "safer: a reconciliation delete scoped to one user's view would skip the rows that user "
    "cannot see, leaving documents for deleted files that nothing can ever remove. The rows it "
    "matches carry no owner at all (build_watch_metadata writes source/category/tags/folder_id/"
    "filename/file_path/collection), which is itself open as the watch-folder visibility ruling "
    "on #17533"
)
_SYSTEM_IMPORT = (
    "NOT_USER_FACING: #19216 system-knowledge import resolving a store 'duplicate' to the fact it matched. "
    "It runs from the import job with no user in context, reads only that fact's metadata (type, name, "
    "link id) to decide whether to merge the link id, and returns a fact id and a status, never content, "
    "to a caller or a prompt. The read is unfiltered so the import can SEE who holds the fact: it writes "
    "only to an ownerless, platform-wide one (is_ownerless_platform_fact, #19296) and reports any other "
    "unresolved, never written; a scoped read would hide the owner it must check"
)
_SCOPED_ADMIN_ROUTER = (
    "SCOPED: route requires Depends(check_admin_permission) (403 for non-admins), and "
    "check_access already grants admins unconditional read (#16665)"
)

_RAG_LEG = (
    "SCOPED: reached only through RAGService (services/rag_service.py:230,241,507), which post-filters every leg with "
    "filter_ranked (#16664), and the module's convenience functions, which take a required principal (#18944); "
    "services/knowledge_sync_service.py only initialises it"
)
_LIBRARIAN_UNCALLED = (
    "NOT_USER_FACING: no production caller -- agents/system_knowledge_manager.py uses the librarian's store_* methods "
    "only, so this reader is unreachable from any route, agent or job (#16665 trace)"
)
_PRESERVE = (
    "NOT_USER_FACING: reads the fact only to check it exists and belongs to the session before marking it preserved; "
    "the route returns a status and the fact id, never content"
)
_ADAPTER = (
    "SCOPED: the adapter's only production caller is services/rag_service.py (:995), whose results pass "
    "filter_ranked before use (#16664); get_all_facts has no production caller"
)
_RESEARCH_QUARANTINE = (
    "NOT_USER_FACING: searches the research quarantine collection for corroborating candidates; those are "
    "system-written web-research facts, and only a corroboration verdict -- never the fact -- leaves it"
)

ALLOWLIST: dict[tuple[str, str], str] = {
    ("autobot-backend/advanced_rag_optimizer.py", "AdvancedRAGOptimizer._perform_semantic_search"): _RAG_LEG,
    ("autobot-backend/advanced_rag_optimizer.py", "AdvancedRAGOptimizer._retrieve_hybrid_results"): _RAG_LEG,
    ("autobot-backend/agents/kb_librarian/librarian.py", "KBLibrarian.get_tool_instructions"): _LIBRARIAN_UNCALLED,
    ("autobot-backend/agents/kb_librarian/librarian.py", "KBLibrarian.search_tool_knowledge"): _LIBRARIAN_UNCALLED,
    ("autobot-backend/agents/kb_librarian/stable_ids.py", "_adopt_duplicate"): _SYSTEM_IMPORT,
    ("autobot-backend/ai_hardware_accelerator.py", "AIHardwareAccelerator._gpu_semantic_search"): _T2,
    ("autobot-backend/api/chat_knowledge.py", "_preserve_single_fact"): _PRESERVE,
    (
        "autobot-backend/api/chat_sessions.py",
        "get_share_preview",
    ): "TRACKED_GAP #16671: session fact sharing reads facts through an unwired kb_manager",
    ("autobot-backend/api/knowledge.py", "search_man_pages"): _SCOPED_ADMIN_ROUTER,
    (
        "autobot-backend/api/knowledge_categories.py",
        "get_facts_in_category",
    ): _SCOPED_ADMIN_ROUTER,
    (
        "autobot-backend/api/knowledge_category_counts.py",
        "_get_or_compute_category_counts",
    ): (
        "SCOPED: filtered by _visible_to_every_authenticated_user, a caller-independent "
        "predicate (#16665) -- the cached count is shared by every caller (one Redis key "
        "per category), so a per-caller check_access() would return a different answer "
        "per caller and break the shared cache; the guard's FILTER_HELPERS list only "
        "recognizes the per-caller helpers, not this intentionally caller-independent one"
    ),
    (
        "autobot-backend/api/knowledge_collections.py",
        "export_collection",
    ): _SCOPED_ADMIN_ROUTER,
    (
        "autobot-backend/api/knowledge_collections.py",
        "get_facts_in_collection",
    ): _SCOPED_ADMIN_ROUTER,
    ("autobot-backend/api/knowledge_metadata.py", "search_by_metadata"): _SCOPED_ADMIN_ROUTER,
    (
        "autobot-backend/api/knowledge_ownership.py",
        "_fetch_fact_details",
    ): "SCOPED: the fact ids come from the caller's own ownership index (#688)",
    (
        "autobot-backend/api/knowledge_ownership.py",
        "get_shared_facts",
    ): "SCOPED: the fact ids come from the caller's own ownership index (#688)",
    ("autobot-backend/api/knowledge_relations.py", "get_fact_relations"): _SCOPED_ADMIN_ROUTER,
    ("autobot-backend/api/knowledge_relations.py", "hybrid_search"): _SCOPED_ADMIN_ROUTER,
    ("autobot-backend/api/knowledge_relations.py", "traverse_relations"): _SCOPED_ADMIN_ROUTER,
    (
        "autobot-backend/api/knowledge_search_aggregator.py",
        "_expand_fact_relations",
    ): (
        "SCOPED: every related fact is passed through _related_fact_is_accessible "
        "(#16665), which calls filter_search_results_by_permission -- the guard's "
        "single-hop AST scan doesn't see a filter call made from a locally-defined "
        "helper one level down, but the read is genuinely filtered before use"
    ),
    (
        "autobot-backend/api/knowledge_search_aggregator.py",
        "_get_fact_relations_for_graph",
    ): (
        "SCOPED: fact_ids come from _get_facts_for_graph's already-filtered output "
        "(#16665), and both ends of every returned edge are re-checked against that "
        "same fact_ids set -- include_fact_details=False means no fact content is "
        "ever fetched here"
    ),
    (
        "autobot-backend/api/knowledge_search_aggregator.py",
        "_process_relations_for_citations",
    ): (
        "SCOPED: every related fact is passed through _related_fact_is_accessible "
        "(#16665), which calls filter_search_results_by_permission -- the guard's "
        "single-hop AST scan doesn't see a filter call made from a locally-defined "
        "helper one level down, but the read is genuinely filtered before use"
    ),
    ("autobot-backend/api/knowledge_tags.py", "get_facts_by_tag"): _SCOPED_ADMIN_ROUTER,
    ("autobot-backend/api/knowledge_tags.py", "search_facts_by_tags"): _SCOPED_ADMIN_ROUTER,
    (
        "autobot-backend/api/knowledge_verification.py",
        "list_pending_verification",
    ): _SCOPED_ADMIN_ROUTER,
    (
        "autobot-backend/api/memory_lifecycle.py",
        "_reinforcement_section",
    ): (
        "SCOPED: route requires Depends(check_admin_permission), and its own _slim() "
        "helper strips every fact field except fact_id/quality_score/access_count/"
        "last_accessed before it reaches the response -- fact content never leaves (#16665)"
    ),
    (
        "autobot-backend/knowledge/quarantine.py",
        "read_every_fact",
    ): (
        "NOT_USER_FACING: the backup and export serialisers read every fact through the audited "
        "include_quarantined opt-out (one audit entry per read; the read fails closed if it cannot be "
        "written) and write operator files or return an admin-gated export; nothing reaches a chat or "
        "prompt (#19163)"
    ),
    (
        "autobot-backend/knowledge/vector_search_engine.py",
        "_CPUBackend.search",
    ): "IMPL: the KB's own CPU backend calling its vector primitive",
    ("autobot-backend/mcp_server/autobot_server.py", "AutoBotMCPServer._kb_get_document"): _MCP_NON_PRIVATE,
    ("autobot-backend/mcp_server/autobot_server.py", "AutoBotMCPServer._kb_search"): _MCP_NON_PRIVATE,
    ("autobot-backend/npu_semantic_search.py", "NPUSemanticSearch._handle_search_error"): _T2,
    ("autobot-backend/npu_semantic_search.py", "NPUSemanticSearch._perform_vector_search"): _T2,
    (
        "autobot-backend/services/claim_classifier.py",
        "ClaimClassifier._search_knowledge_base",
    ): "TRACKED_GAP #16673: un-awaited KB search; scope as the claimant once it runs (#16654 AC1)",
    (
        "autobot-backend/services/command_extraction_service.py",
        "search_commands",
    ): "TRACKED_GAP #16672: dead import; must read with fact visibility once wired",
    ("autobot-backend/services/knowledge_base_adapter.py", "KnowledgeBaseAdapter.get_all_facts"): _ADAPTER,
    ("autobot-backend/services/knowledge_base_adapter.py", "KnowledgeBaseAdapter.search"): _ADAPTER,
    ("autobot-backend/services/orphan_repair_types.py", "KnowledgeFactRepairer._metadata"): _ORPHAN_REPAIR,
    ("autobot-backend/services/orphan_repair_types.py", "KnowledgeFactRepairer.find_orphans"): _ORPHAN_REPAIR,
    ("autobot-backend/services/research/orchestrator.py", "_gather_candidate_sources"): _RESEARCH_QUARANTINE,
    (
        "autobot-backend/utils/system_validator.py",
        "SystemValidator.validate_hybrid_search",
    ): "NOT_USER_FACING: a health check that only times a probe query",
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
    ("autobot-backend/knowledge/facts.py", "FactsMixin._find_duplicate"): (
        _IMPL_DEDUP + "; the query uses without_quarantine, so a quarantined fact is neither a duplicate nor "
        "has its id returned to the store caller (#19163)"
    ),
    ("autobot-backend/knowledge/search.py", "SearchMixin._query_chromadb"): _IMPL_SEARCH,
    ("autobot-backend/api/knowledge_lint_chunks.py", "_fetch_all_chunks._load"): _RAW_ADMIN,
    ("autobot-backend/api/knowledge_vectorization.py", "_fetch_chunks_by_ids"): _RAW_ADMIN_NO_QUARANTINE,
    ("autobot-backend/api/knowledge_vectorization.py", "_fetch_unenriched_ids"): _RAW_ADMIN_NO_QUARANTINE,
    ("autobot-backend/knowledge/summary_search.py", "SummarySearchService.search_summaries"): _SUMMARIES,
    ("autobot-backend/knowledge/summary_search.py", "SummarySearchService.get_document_overview"): _SUMMARIES,
    ("autobot-backend/knowledge/summary_search.py", "SummarySearchService.drill_down"): _SUMMARIES,
    ("autobot-backend/knowledge/summary_visibility.py", "_source_metadata"): (
        "SCOPED: reads only the source fact's metadata, which visible_summaries hands straight to "
        "filter_for_user_id; the fact's content never leaves the function (#16665)"
    ),
    ("autobot-backend/knowledge/vector_repair.py", "scan_poisoned_rows"): _RAW_REPAIR,
    ("autobot-backend/knowledge/vector_repair.py", "has_reachable_vector"): _RAW_REPAIR,
    ("autobot-backend/memory/ownership_reassign.py", "_reassign_kb_facts_chroma"): _RAW_ADMIN,
    ("autobot-backend/memory/ownership_reassign.py", "_reassign_chroma_store"): _RAW_ADMIN_MEMORY,
    ("autobot-backend/services/semantic_query_cache.py", "SemanticQueryCache.lookup"): _RAG_CACHE,
    ("autobot-backend/services/semantic_query_cache.py", "SemanticQueryCache._maybe_evict"): _CACHE_EVICT,
    ("autobot-backend/services/semantic_query_cache.py", "SemanticQueryCache.clear"): _RAW_ADMIN,
    ("autobot-backend/services/topic_retrieval_cache.py", "TopicRetrievalCache.lookup"): _RAG_CACHE,
    ("autobot-backend/services/topic_retrieval_cache.py", "TopicRetrievalCache._maybe_evict"): _CACHE_EVICT,
    ("autobot-backend/services/kb_watch_ingest.py", "remove_watched_file"): _WATCH_RECONCILE,
    (
        "autobot-backend/knowledge/claude_memory_importer.py",
        "import_memory_file",
    ): (
        "SCOPED: fact_id is `f'{CATEGORY}:{owner_id}:{slug}'` (#17124) -- the existence check "
        "this read feeds can only ever find a fact already scoped to the same owner_id "
        "the importer is running as, so it can't read (or the subsequent update_fact "
        "can't overwrite) a fact belonging to a different owner"
    ),
}
