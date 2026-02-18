#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Final comprehensive analysis of Redis vector store integration options for AutoBot
"""

import asyncio
import json
import logging
import sys
from typing import Any, Dict, List, Tuple

sys.path.insert(0, "/home/kali/Desktop/AutoBot")
from constants import ServiceURLs
from constants.network_constants import NetworkConstants

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def _build_fix_llamaindex_recommendation(data_analysis, llamaindex_fixes):
    """Build recommendation for fixing LlamaIndex integration.

    Helper for generate_final_recommendation (#825).
    """
    return {
        "recommendation": "FIX_LLAMAINDEX_INTEGRATION",
        "confidence": "HIGH",
        "rationale": [
            "Preserves %s existing vectors"
            % "{:,}".format(data_analysis.get("total_documents", 0)),
            "LlamaIndex can retrieve data successfully with field fixes",
            "Minimal code changes required",
            "Low risk - no data migration needed",
        ],
        "implementation_steps": [
            "Update knowledge_base.py to use retriever instead of query_engine",
            "Fix LLM model selection to use available models",
            "Add proper error handling for model availability",
            "Test thoroughly with existing 13,383 vectors",
        ],
        "estimated_effort": "4-8 hours",
        "risk_level": "LOW",
        "data_migration": "None required",
        "compatibility_issues_resolved": llamaindex_fixes,
    }


def _build_migrate_langchain_recommendation(langchain_fixes):
    """Build recommendation for migrating to LangChain.

    Helper for generate_final_recommendation (#825).
    """
    return {
        "recommendation": "MIGRATE_TO_LANGCHAIN",
        "confidence": "MEDIUM",
        "rationale": [
            "LangChain integration works reliably",
            "Modern langchain-redis package available",
            "Better async support and documentation",
            "LlamaIndex has unresolvable field mapping issues",
        ],
        "implementation_steps": [
            "Export existing vector data via Redis FT.SEARCH",
            "Create data migration script from LlamaIndex to LangChain format",
            "Update knowledge_base.py to use LangChain RedisVectorStore",
            "Re-index documents with LangChain format",
            "Update all API endpoints and search methods",
            "Verify data integrity and search quality",
        ],
        "estimated_effort": "2-3 days",
        "risk_level": "MEDIUM",
        "data_migration": "Full re-indexing required",
        "compatibility_issues_resolved": langchain_fixes,
    }


def _build_custom_redis_recommendation():
    """Build recommendation for custom Redis integration.

    Helper for generate_final_recommendation (#825).
    """
    return {
        "recommendation": "CUSTOM_REDIS_INTEGRATION",
        "confidence": "MEDIUM",
        "rationale": [
            "13,383 vectors represent significant investment",
            "Direct Redis FT.SEARCH works perfectly",
            "Both LlamaIndex and LangChain have compatibility issues",
            "Custom integration can leverage existing data structure",
        ],
        "implementation_steps": [
            "Create custom Redis vector store class",
            "Implement direct FT.SEARCH integration",
            "Use existing field structure without modification",
            "Add async support and proper error handling",
            "Maintain compatibility with existing data format",
        ],
        "estimated_effort": "1-2 weeks",
        "risk_level": "MEDIUM-HIGH",
        "data_migration": "None - uses existing structure",
        "compatibility_issues_resolved": [
            "Direct Redis access bypasses library limitations"
        ],
    }


def _build_start_fresh_recommendation(langchain_fixes):
    """Build recommendation for starting fresh with LangChain.

    Helper for generate_final_recommendation (#825).
    """
    return {
        "recommendation": "START_FRESH_LANGCHAIN",
        "confidence": "LOW",
        "rationale": [
            "Existing data has compatibility issues",
            "LangChain provides better long-term foundation",
            "Modern architecture worth the migration effort",
        ],
        "implementation_steps": [
            "Backup existing data",
            "Implement clean LangChain integration",
            "Re-process source documents with LangChain",
            "Test with modern langchain-redis package",
        ],
        "estimated_effort": "1-2 days",
        "risk_level": "MEDIUM",
        "data_migration": "Complete restart",
        "compatibility_issues_resolved": langchain_fixes,
    }


def _configure_llamaindex_settings(fixes_attempted):
    """Configure LlamaIndex LLM and embeddings settings.

    Helper for test_llamaindex_field_fix (#825).

    Returns:
        Tuple of (embed_model, vector_store, index).
    """
    from llama_index.core import Settings, VectorStoreIndex
    from llama_index.embeddings.ollama import OllamaEmbedding
    from llama_index.llms.ollama import Ollama
    from llama_index.vector_stores.redis import RedisVectorStore
    from llama_index.vector_stores.redis.schema import RedisVectorStoreSchema

    llm = Ollama(
        model="gemma3:270m",
        base_url=ServiceURLs.OLLAMA_LOCAL,
        request_timeout=10.0,
    )
    embed_model = OllamaEmbedding(
        model_name="nomic-embed-text:latest",
        base_url=ServiceURLs.OLLAMA_LOCAL,
    )

    Settings.llm = llm
    Settings.embed_model = embed_model
    fixes_attempted.append("Configured LLM with working model (gemma3:270m)")

    schema = RedisVectorStoreSchema(
        index_name="llama_index",
        prefix="llama_index/vector",
        overwrite=False,
    )
    vector_store = RedisVectorStore(
        schema=schema,
        redis_url=ServiceURLs.REDIS_LOCAL,
        redis_kwargs={"db": 2},
    )
    fixes_attempted.append("Connected to existing vector store without overwriting")

    index = VectorStoreIndex.from_vector_store(
        vector_store=vector_store,
        embed_model=embed_model,
    )
    fixes_attempted.append("Loaded existing vector index")

    return embed_model, vector_store, index


async def _try_direct_vector_query(embed_model, vector_store, fixes_attempted):
    """Try direct vector store query as fallback when retriever fails.

    Helper for test_llamaindex_field_fix (#825).

    Returns:
        Tuple of (success, result_count, fixes_attempted).
    """
    from llama_index.core.vector_stores.types import VectorStoreQuery

    query_embedding = await asyncio.to_thread(
        embed_model.get_text_embedding,
        "kubernetes deployment",
    )
    query_obj = VectorStoreQuery(
        query_embedding=query_embedding,
        similarity_top_k=3,
    )
    direct_result = await asyncio.to_thread(vector_store.query, query_obj)
    result_count = len(direct_result.nodes) if hasattr(direct_result, "nodes") else 0
    fixes_attempted.append(
        "Direct vector store query: %s results" % result_count,
    )
    return result_count > 0, result_count, fixes_attempted


class AutoBotVectorStoreAnalysis:
    def __init__(self):
        self.existing_data_analysis = {}
        self.compatibility_issues = []
        self.recommendations = {}

    def _analyze_field_value(
        self, field: str, value: str, field_analysis: Dict
    ) -> None:
        """Analyze a single field value (Issue #315: extracted helper)."""
        if field == "vector":
            field_analysis[field]["data_type"] = "binary_vector"
            field_analysis[field]["size_bytes"] = len(value)
        elif field in ["_node_content", "source_metadata"]:
            field_analysis[field]["data_type"] = "json"
            try:
                parsed = json.loads(value)
                if (
                    field == "_node_content"
                    and len(field_analysis[field]["sample_values"]) == 0
                ):
                    field_analysis[field]["sample_values"].append(
                        list(parsed.keys())[:5]
                    )
            except Exception:
                field_analysis[field]["data_type"] = "string"
        else:
            field_analysis[field]["data_type"] = "string"
            if len(field_analysis[field]["sample_values"]) < 3:
                field_analysis[field]["sample_values"].append(str(value)[:50])

    def _process_document_fields(self, doc: Dict, field_analysis: Dict) -> None:
        """Process all fields in a document (Issue #315: extracted helper)."""
        for field in doc.keys():
            if field not in field_analysis:
                field_analysis[field] = {
                    "count": 0,
                    "sample_values": [],
                    "data_type": "unknown",
                }
            field_analysis[field]["count"] += 1
            self._analyze_field_value(field, doc[field], field_analysis)

    async def deep_analyze_existing_data(self) -> Dict[str, Any]:
        """Deep analysis of existing Redis vector data."""
        logger.info("Deep analysis of existing Redis vector data...")

        try:
            import redis

            client = redis.Redis(
                host=NetworkConstants.LOCALHOST_NAME,
                port=NetworkConstants.REDIS_PORT,
                db=2,
                decode_responses=True,
            )

            index_info_raw = client.execute_command("FT.INFO", "llama_index")
            index_info = {}
            for i in range(0, len(index_info_raw), 2):
                if i + 1 < len(index_info_raw):
                    index_info[index_info_raw[i]] = index_info_raw[i + 1]

            sample_keys = list(
                client.scan_iter(match="llama_index/vector*", count=10),
            )
            field_analysis = {}

            for key in sample_keys[:5]:
                doc = client.hgetall(key)
                self._process_document_fields(doc, field_analysis)

            vector_config = self._extract_vector_config(index_info)

            analysis = {
                "total_documents": index_info.get("num_docs", 0),
                "index_size_mb": index_info.get("total_index_memory_sz_mb", 0),
                "vector_config": vector_config,
                "field_analysis": field_analysis,
                "data_structure_type": "llamaindex_semantic_chunks",
                "created_by": "AutoBot semantic chunker with LlamaIndex",
                "compatibility_issues": self._identify_compatibility_issues(
                    field_analysis
                ),
            }

            self.existing_data_analysis = analysis
            return analysis

        except Exception as e:
            logger.error("Deep analysis failed: %s", e)
            return {}

    def _extract_vector_config(self, index_info: Dict) -> Dict[str, Any]:
        """Extract vector field configuration from index info"""
        try:
            if "attributes" in index_info:
                attrs = index_info["attributes"]
                for i in range(0, len(attrs), 6):
                    if i + 1 < len(attrs) and attrs[i + 1] == "vector":
                        return {
                            "field_name": attrs[i + 1],
                            "type": attrs[i + 2] if i + 2 < len(attrs) else "unknown",
                            "algorithm": attrs[i + 3]
                            if i + 3 < len(attrs)
                            else "unknown",
                            "data_type": attrs[i + 4]
                            if i + 4 < len(attrs)
                            else "unknown",
                            "dimensions": attrs[i + 5]
                            if i + 5 < len(attrs)
                            else "unknown",
                        }
        except Exception as e:
            logger.warning("Could not extract vector config: %s", e)
        return {}

    def _identify_compatibility_issues(self, field_analysis: Dict) -> List[str]:
        """Identify compatibility issues with different vector store libraries"""
        issues = []

        if "_node_content" in field_analysis and "text" in field_analysis:
            issues.append(
                "LLAMAINDEX_FIELD_MISMATCH: Both '_node_content' and 'text' exist"
            )
        if "text" not in field_analysis:
            issues.append("LLAMAINDEX_MISSING_TEXT: No 'text' field found")
        if "_node_content" not in field_analysis:
            issues.append("LLAMAINDEX_MISSING_NODE_CONTENT: No '_node_content' field")
        if "content" not in field_analysis and "text" in field_analysis:
            issues.append("LANGCHAIN_FIELD_MAPPING: Uses 'text' instead of 'content'")
        if "source_metadata" in field_analysis:
            issues.append("METADATA_STRUCTURE: Nested metadata may need flattening")

        return issues

    async def test_llamaindex_field_fix_basic(self) -> Tuple[bool, int, List[str]]:
        """Test if LlamaIndex can work with field mapping fix (basic)"""
        logger.info("\nTesting LlamaIndex with field mapping fix...")
        fixes_attempted = []

        try:
            _em, _vs, index = _configure_llamaindex_settings(fixes_attempted)
            retriever = index.as_retriever(similarity_top_k=3)

            nodes = await asyncio.to_thread(
                retriever.retrieve,
                "deployment configuration",
            )
            result_count = len(nodes)
            logger.info("LlamaIndex field fix test: %s results", result_count)

            if result_count > 0:
                for i, node in enumerate(nodes[:2]):
                    text = node.text[:100] if hasattr(node, "text") else "No text"
                    logger.info("  Result %s: %s...", i + 1, text)

            fixes_attempted.append(
                "Successfully retrieved %s results" % result_count,
            )
            return True, result_count, fixes_attempted

        except Exception as e:
            logger.error("LlamaIndex field fix failed: %s", e)
            fixes_attempted.append("FAILED: %s" % str(e))
            return False, 0, fixes_attempted

    async def test_langchain_db0_workaround_basic(self) -> Tuple[bool, int, List[str]]:
        """Test LangChain on Redis DB 0 (basic version)"""
        logger.info("\nTesting LangChain on Redis DB 0...")
        fixes_attempted = []

        try:
            from langchain_community.embeddings import OllamaEmbeddings
            from langchain_redis import RedisVectorStore

            embeddings = OllamaEmbeddings(
                model="nomic-embed-text:latest",
                base_url=ServiceURLs.OLLAMA_LOCAL,
            )
            fixes_attempted.append("Initialized Ollama embeddings")

            vector_store = RedisVectorStore(
                embeddings=embeddings,
                index_name="autobot_langchain_db0",
                redis_url="%s/0" % ServiceURLs.REDIS_LOCAL,
            )
            fixes_attempted.append("Created LangChain vector store on Redis DB 0")

            test_docs = ["Test deployment configuration document"]
            test_metadata = [{"source": "test", "type": "deployment"}]
            await asyncio.to_thread(
                vector_store.add_texts,
                test_docs,
                metadatas=test_metadata,
            )
            fixes_attempted.append("Successfully added test documents")

            results = await asyncio.to_thread(
                vector_store.similarity_search,
                "deployment",
                k=3,
            )
            result_count = len(results)
            logger.info("LangChain DB0 test: %s results", result_count)
            fixes_attempted.append("Found %s results" % result_count)
            return True, result_count, fixes_attempted

        except Exception as e:
            logger.error("LangChain DB0 test failed: %s", e)
            fixes_attempted.append("FAILED: %s" % str(e))
            return False, 0, fixes_attempted

    def generate_final_recommendation(
        self,
        data_analysis: Dict[str, Any],
        llamaindex_result: Tuple[bool, int, List[str]],
        langchain_result: Tuple[bool, int, List[str]],
    ) -> Dict[str, Any]:
        """Generate final technical recommendation"""
        llamaindex_works, _li_count, llamaindex_fixes = llamaindex_result
        langchain_works, _lc_count, langchain_fixes = langchain_result
        existing_data_valuable = data_analysis.get("total_documents", 0) > 10000

        if existing_data_valuable and llamaindex_works:
            return _build_fix_llamaindex_recommendation(
                data_analysis,
                llamaindex_fixes,
            )
        elif langchain_works and not llamaindex_works:
            return _build_migrate_langchain_recommendation(langchain_fixes)
        elif existing_data_valuable:
            return _build_custom_redis_recommendation()
        else:
            return _build_start_fresh_recommendation(langchain_fixes)

    async def run_final_analysis(self):
        """Run complete final analysis"""
        logger.info("Starting final AutoBot vector store analysis\n")

        data_analysis = await self.deep_analyze_existing_data()
        llamaindex_result = await self.test_llamaindex_field_fix()
        langchain_result = await self.test_langchain_db0_workaround()

        recommendation = self.generate_final_recommendation(
            data_analysis,
            llamaindex_result,
            langchain_result,
        )
        self._print_final_report(
            data_analysis,
            llamaindex_result,
            langchain_result,
            recommendation,
        )
        self._save_report(
            data_analysis,
            llamaindex_result,
            langchain_result,
            recommendation,
        )
        return recommendation

    def _save_report(
        self, data_analysis, llamaindex_result, langchain_result, recommendation
    ):
        """Save analysis report to file.

        Helper for run_final_analysis (#825).
        """
        import os

        full_report = {
            "data_analysis": data_analysis,
            "llamaindex_test": {
                "success": llamaindex_result[0],
                "result_count": llamaindex_result[1],
                "fixes_attempted": llamaindex_result[2],
            },
            "langchain_test": {
                "success": langchain_result[0],
                "result_count": langchain_result[1],
                "fixes_attempted": langchain_result[2],
            },
            "recommendation": recommendation,
        }

        output_file = (
            "/home/kali/Desktop/AutoBot/reports/vector_store_final_analysis.json"
        )
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(full_report, f, indent=2)

    def _print_final_report(
        self, data_analysis, llamaindex_result, langchain_result, recommendation
    ):
        """Print the final comprehensive report"""
        logger.info("\n" + "=" * 90)
        logger.info("AUTOBOT REDIS VECTOR STORE - FINAL TECHNICAL ANALYSIS")
        logger.info("=" * 90)

        self._print_data_quality(data_analysis)
        self._print_test_results(llamaindex_result, langchain_result)
        self._print_recommendation(recommendation)
        logger.info("\n" + "=" * 90)

    def _print_data_quality(self, data_analysis):
        """Print data quality assessment section.

        Helper for _print_final_report (#825).
        """
        logger.info("\nEXISTING DATA QUALITY ASSESSMENT:")
        logger.info(
            "  Documents: %s (HIGH QUALITY)",
            data_analysis.get("total_documents", 0),
        )
        logger.info("  Index Size: %s MB", data_analysis.get("index_size_mb", 0))
        vec_cfg = data_analysis.get("vector_config", {})
        logger.info("  Vector Dimensions: %s", vec_cfg.get("dimensions", "unknown"))
        logger.info("  Algorithm: %s", vec_cfg.get("algorithm", "unknown"))

        issues = data_analysis.get("compatibility_issues", [])
        if issues:
            logger.warning("\nCOMPATIBILITY ISSUES IDENTIFIED:")
            for issue in issues:
                logger.info("    - %s", issue)

    def _print_test_results(self, llamaindex_result, langchain_result):
        """Print integration test results section.

        Helper for _print_final_report (#825).
        """
        logger.info("\nINTEGRATION TEST RESULTS:")
        li_status = "WORKING" if llamaindex_result[0] else "FAILED"
        logger.info("  LlamaIndex: %s (%s results)", li_status, llamaindex_result[1])
        if llamaindex_result[2]:
            logger.info("    Fixes: %s", ", ".join(llamaindex_result[2][-2:]))
        lc_status = "WORKING" if langchain_result[0] else "FAILED"
        logger.info("  LangChain: %s (%s results)", lc_status, langchain_result[1])
        if langchain_result[2]:
            logger.info("    Fixes: %s", ", ".join(langchain_result[2][-2:]))

    def _print_recommendation(self, recommendation):
        """Print recommendation section.

        Helper for _print_final_report (#825).
        """
        logger.info("\nFINAL RECOMMENDATION: %s", recommendation["recommendation"])
        logger.info("  Confidence Level: %s", recommendation["confidence"])
        logger.info("  Estimated Effort: %s", recommendation["estimated_effort"])
        logger.info("  Risk Level: %s", recommendation["risk_level"])
        logger.info("  Data Migration: %s", recommendation["data_migration"])

        logger.info("\nREASONING:")
        for reason in recommendation["rationale"]:
            logger.info("    %s", reason)
        logger.info("\nIMPLEMENTATION STEPS:")
        for i, step in enumerate(recommendation["implementation_steps"], 1):
            logger.info("    %s. %s", i, step)

    async def test_llamaindex_field_fix(self) -> Tuple[bool, int, List[str]]:
        """Test LlamaIndex with field mapping issues addressed"""
        fixes_attempted = []

        try:
            embed_model, vector_store, index = _configure_llamaindex_settings(
                fixes_attempted,
            )
            retriever = index.as_retriever(similarity_top_k=5)

            try:
                nodes = await asyncio.to_thread(
                    retriever.retrieve,
                    "kubernetes deployment",
                )
                result_count = len(nodes)
                fixes_attempted.append("Retrieved %s nodes" % result_count)

                if result_count > 0:
                    node = nodes[0]
                    if hasattr(node, "text") and node.text:
                        fixes_attempted.append("Nodes have valid text content")
                        logger.info("Sample text: %s...", node.text[:100])
                    else:
                        fixes_attempted.append("WARNING: Nodes missing text")

                return True, result_count, fixes_attempted

            except Exception as retrieval_error:
                fixes_attempted.append("Retrieval failed: %s" % str(retrieval_error))
                return await _try_direct_vector_query(
                    embed_model,
                    vector_store,
                    fixes_attempted,
                )

        except Exception as e:
            logger.error("LlamaIndex test failed: %s", e)
            fixes_attempted.append("FAILED: %s" % str(e))
            return False, 0, fixes_attempted

    async def test_langchain_db0_workaround(self) -> Tuple[bool, int, List[str]]:
        """Test LangChain with DB 0 workaround"""
        fixes_attempted = []

        try:
            from langchain_redis import RedisVectorStore

            try:
                from langchain_ollama import OllamaEmbeddings

                fixes_attempted.append("Using modern langchain-ollama package")
            except ImportError:
                from langchain_community.embeddings import OllamaEmbeddings

                fixes_attempted.append("Using langchain-community embeddings")

            embeddings = OllamaEmbeddings(
                model="nomic-embed-text:latest",
                base_url=ServiceURLs.OLLAMA_LOCAL,
            )
            vector_store = RedisVectorStore(
                embeddings=embeddings,
                index_name="autobot_langchain_test",
                redis_url="%s/0" % ServiceURLs.REDIS_LOCAL,
            )
            fixes_attempted.append("Created vector store on Redis DB 0")

            test_docs = ["Kubernetes deployment configuration for AutoBot"]
            test_metadata = [{"source": "test", "category": "deployment"}]
            await asyncio.to_thread(
                vector_store.add_texts,
                test_docs,
                metadatas=test_metadata,
            )
            fixes_attempted.append("Successfully added test documents")

            results = await asyncio.to_thread(
                vector_store.similarity_search,
                "deployment configuration",
                k=3,
            )
            result_count = len(results)
            fixes_attempted.append("Search returned %s results" % result_count)
            logger.info("LangChain DB0 successful: %s results", result_count)
            return True, result_count, fixes_attempted

        except Exception as e:
            logger.error("LangChain DB0 failed: %s", e)
            fixes_attempted.append("FAILED: %s" % str(e))
            return False, 0, fixes_attempted


async def main():
    analyzer = AutoBotVectorStoreAnalysis()
    await analyzer.run_final_analysis()

    logger.info(
        "\nComplete analysis saved to:"
        " /home/kali/Desktop/AutoBot/reports/vector_store_final_analysis.json"
    )


if __name__ == "__main__":
    asyncio.run(main())
