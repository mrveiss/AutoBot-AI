#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Comprehensive analysis of Redis vector store options for AutoBot.
Tests both LangChain and LlamaIndex with proper configuration.
"""

import asyncio
import json
import logging
import sys
from typing import Any, Dict, List, Tuple

from constants import ServiceURLs

# Add project root to path
sys.path.insert(0, "/home/kali/Desktop/AutoBot")

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def _parse_index_info(index_info):
    """Parse raw Redis FT.INFO output into a dict.

    Helper for analyze_existing_data (#825).
    """
    info_dict = {}
    for i in range(0, len(index_info), 2):
        if i + 1 < len(index_info):
            info_dict[index_info[i]] = index_info[i + 1]
    return info_dict


def _extract_vector_config(info_dict):
    """Extract vector field configuration from parsed index info.

    Helper for analyze_existing_data (#825).
    """
    vector_config = {}
    if "attributes" in info_dict:
        attrs = info_dict["attributes"]
        for j in range(0, len(attrs), 6):
            if j + 1 < len(attrs) and attrs[j + 1] == "vector":
                vector_config = {
                    "identifier": attrs[j],
                    "attribute": attrs[j + 1],
                    "type": attrs[j + 2],
                    "algorithm": attrs[j + 3],
                    "data_type": attrs[j + 4],
                    "dim": attrs[j + 5] if j + 5 < len(attrs) else "unknown",
                }
                break
    return vector_config


def _build_sample_doc(key, doc_data):
    """Build sample document analysis from raw key data.

    Helper for analyze_existing_data (#825).
    """
    return {
        "key": key,
        "fields": list(doc_data.keys()),
        "has_vector": "vector" in doc_data,
        "has_text": "text" in doc_data,
        "has_metadata": any("metadata" in k for k in doc_data.keys()),
        "text_preview": doc_data.get("text", "")[:100]
        if "text" in doc_data
        else None,
    }


def _configure_llamaindex(ollama_base_url, embedding_model, llm_model, redis_host, redis_port, redis_db):
    """Configure LlamaIndex LLM, embeddings, and vector store connection.

    Helper for test_llamaindex_with_existing_data (#825).

    Returns:
        Tuple of (embed_model, index).
    """
    from llama_index.core import Settings, VectorStoreIndex
    from llama_index.embeddings.ollama import OllamaEmbedding
    from llama_index.llms.ollama import Ollama
    from llama_index.vector_stores.redis import RedisVectorStore
    from llama_index.vector_stores.redis.schema import RedisVectorStoreSchema

    llm = Ollama(
        model=llm_model,
        base_url=ollama_base_url,
        request_timeout=10.0,
    )
    embed_model = OllamaEmbedding(
        model_name=embedding_model, base_url=ollama_base_url,
    )

    Settings.llm = llm
    Settings.embed_model = embed_model

    schema = RedisVectorStoreSchema(
        index_name="llama_index",
        prefix="llama_index/vector",
        overwrite=False,
    )
    vector_store = RedisVectorStore(
        schema=schema,
        redis_url="redis://%s:%s" % (redis_host, redis_port),
        redis_kwargs={"db": redis_db},
    )
    index = VectorStoreIndex.from_vector_store(
        vector_store=vector_store, embed_model=embed_model,
    )
    return embed_model, index


def _assess_result_quality(result_count):
    """Assess quality of search results based on count.

    Helper for test methods (#825).
    """
    if result_count > 5:
        return "EXCELLENT"
    elif result_count > 0:
        return "GOOD"
    return "POOR"


def _init_langchain_embeddings(embedding_model, ollama_base_url):
    """Initialize LangChain embeddings with fallback.

    Helper for test_langchain_new_approach (#825).
    """
    try:
        from langchain_ollama import OllamaEmbeddings
        logger.info("Using langchain-ollama embeddings")
    except ImportError:
        from langchain_community.embeddings import OllamaEmbeddings
        logger.info("Using community ollama embeddings")

    return OllamaEmbeddings(
        model=embedding_model, base_url=ollama_base_url,
    )


class RedisVectorStoreAnalyzer:
    def __init__(self):
        self.redis_host = "localhost"
        self.redis_port = 6379
        self.redis_db = 2
        self.ollama_base_url = ServiceURLs.OLLAMA_LOCAL
        self.embedding_model = "nomic-embed-text:latest"

    async def get_available_models(self) -> List[str]:
        """Get available Ollama models"""
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "%s/api/tags" % self.ollama_base_url,
                )
                if response.status_code == 200:
                    data = response.json()
                    return [model["name"] for model in data.get("models", [])]
        except Exception as e:
            logger.error("Failed to get models: %s", e)
        return []

    async def analyze_existing_data(self) -> Dict[str, Any]:
        """Analyze the existing Redis vector data structure"""
        logger.info("Analyzing existing Redis data structure...")

        try:
            import redis

            client = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                db=self.redis_db,
                decode_responses=True,
            )

            index_info = client.execute_command("FT.INFO", "llama_index")
            info_dict = _parse_index_info(index_info)
            vector_config = _extract_vector_config(info_dict)

            sample_keys = list(
                client.scan_iter(match="llama_index/vector*", count=3),
            )
            sample_docs = [
                _build_sample_doc(key, client.hgetall(key))
                for key in sample_keys
            ]

            analysis = {
                "total_documents": info_dict.get("num_docs", 0),
                "index_name": info_dict.get("index_name", "unknown"),
                "vector_dimension": vector_config.get("dim", "unknown"),
                "vector_algorithm": vector_config.get("algorithm", "unknown"),
                "vector_data_type": vector_config.get("data_type", "unknown"),
                "index_size_mb": info_dict.get("total_index_memory_sz_mb", 0),
                "sample_documents": sample_docs,
                "key_prefixes": info_dict.get("prefixes", []),
            }

            logger.info(
                "Analysis complete: %s docs, %s dim vectors",
                analysis["total_documents"],
                analysis["vector_dimension"],
            )
            return analysis

        except Exception as e:
            logger.error("Data analysis failed: %s", e)
            return {}

    async def test_llamaindex_with_existing_data_basic(
        self,
    ) -> Tuple[bool, int, str]:
        """Test LlamaIndex with existing data (basic version)"""
        logger.info("\nTesting LlamaIndex with existing data...")

        try:
            models = await self.get_available_models()
            llm_model = models[0] if models else "gemma3:270m"
            logger.info("Using LLM model: %s", llm_model)

            _embed_model, index = _configure_llamaindex(
                self.ollama_base_url, self.embedding_model,
                llm_model, self.redis_host, self.redis_port, self.redis_db,
            )

            query_engine = index.as_query_engine()
            test_query = "kubernetes deployment configuration"
            response = await asyncio.to_thread(query_engine.query, test_query)

            result_count = (
                len(response.source_nodes)
                if hasattr(response, "source_nodes")
                else 0
            )

            logger.info("LlamaIndex successful: %s results", result_count)
            return True, result_count, _assess_result_quality(result_count)

        except Exception as e:
            logger.error("LlamaIndex test failed: %s", e)
            return False, 0, "FAILED"

    async def test_langchain_new_approach(self) -> Tuple[bool, int, str]:
        """Test LangChain with modern approach"""
        logger.info("\nTesting LangChain with modern approach...")

        try:
            from langchain_redis import RedisVectorStore

            embeddings = _init_langchain_embeddings(
                self.embedding_model, self.ollama_base_url,
            )

            redis_url = "redis://%s:%s/%s" % (
                self.redis_host, self.redis_port, self.redis_db,
            )
            vector_store = RedisVectorStore(
                embeddings=embeddings,
                index_name="autobot_langchain_test",
                redis_url=redis_url,
            )

            test_docs = [
                "Kubernetes deployment configuration for AutoBot system",
                "Docker compose setup with Redis and backend services",
                "Vector store integration with semantic search capabilities",
            ]
            test_metadata = [
                {"source": "test", "category": "deployment", "type": "kubernetes"},
                {"source": "test", "category": "deployment", "type": "docker"},
                {"source": "test", "category": "integration", "type": "vector"},
            ]

            await asyncio.to_thread(
                vector_store.add_texts, test_docs, metadatas=test_metadata,
            )

            results = await asyncio.to_thread(
                vector_store.similarity_search,
                "deployment configuration setup", k=5,
            )

            logger.info("LangChain successful: %s results", len(results))
            self._test_langchain_filters(vector_store)

            assessment = "EXCELLENT" if len(results) >= len(test_docs) else "GOOD"
            return True, len(results), assessment

        except Exception as e:
            logger.error("LangChain test failed: %s", e)
            import traceback
            logger.error(traceback.format_exc())
            return False, 0, "FAILED"

    def _test_langchain_filters(self, vector_store):
        """Test LangChain filtered search if supported.

        Helper for test_langchain_new_approach (#825).
        """
        try:
            filtered_results = vector_store.similarity_search(
                "configuration", k=3, filter={"category": "deployment"},
            )
            logger.info("Filtered search: %s results", len(filtered_results))
        except Exception as filter_e:
            logger.warning("Filtering not supported: %s", filter_e)

    async def test_direct_redis_access(self) -> Tuple[bool, int, str]:
        """Test direct Redis FT.SEARCH capabilities"""
        logger.info("\nTesting direct Redis FT.SEARCH capabilities...")

        try:
            import redis

            client = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                db=self.redis_db,
                decode_responses=True,
            )

            queries = [
                "deployment configuration",
                "@text:kubernetes",
                "@text:(docker AND redis)",
                "*",
            ]

            results = {}
            for query in queries:
                try:
                    search_result = client.execute_command(
                        "FT.SEARCH", "llama_index", query, "LIMIT", "0", "5",
                    )
                    count = search_result[0] if search_result else 0
                    results[query] = count
                    logger.info("Query '%s': %s results", query, count)
                except Exception as e:
                    logger.warning("Query '%s' failed: %s", query, e)
                    results[query] = 0

            total_accessible = max(results.values())
            logger.info("Direct Redis access: %s max results", total_accessible)
            return True, total_accessible, _assess_result_quality(total_accessible)

        except Exception as e:
            logger.error("Direct Redis test failed: %s", e)
            return False, 0, "FAILED"

    async def generate_migration_complexity_estimate(
        self, analysis: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Estimate complexity of different migration approaches"""
        logger.info("\nEstimating migration complexity...")

        llamaindex_fix = {
            "complexity": "LOW",
            "time_estimate": "2-4 hours",
            "risk": "LOW",
            "changes_required": [
                "Fix LLM model configuration in knowledge_base.py",
                "Ensure Settings.llm is set before query_engine creation",
                "Add proper error handling for model availability",
                "Test with existing 13,383 vectors",
            ],
            "data_migration": "NONE - works with existing data",
        }

        langchain_migration = {
            "complexity": "MEDIUM-HIGH",
            "time_estimate": "1-2 days",
            "risk": "MEDIUM",
            "changes_required": [
                "Install and configure langchain-redis package",
                "Export existing 13,383 vectors from Redis",
                "Convert LlamaIndex format to LangChain format",
                "Re-index all documents with LangChain",
                "Update all knowledge_base.py methods",
                "Update API endpoints to use LangChain interfaces",
                "Test data integrity and search quality",
            ],
            "data_migration": "FULL - requires re-indexing all documents",
        }

        hybrid_approach = {
            "complexity": "HIGH",
            "time_estimate": "3-5 days",
            "risk": "HIGH",
            "changes_required": [
                "Implement dual vector store support",
                "Create abstraction layer for both libraries",
                "Handle data synchronization between stores",
                "Maintain compatibility with existing APIs",
                "Complex configuration management",
            ],
            "data_migration": "PARTIAL - gradual migration possible",
        }

        return {
            "llamaindex_fix": llamaindex_fix,
            "langchain_migration": langchain_migration,
            "hybrid_approach": hybrid_approach,
            "existing_data_size": analysis.get("total_documents", 0),
            "existing_data_quality": "HIGH"
            if analysis.get("total_documents", 0) > 10000
            else "MEDIUM",
        }

    async def run_comprehensive_analysis(self):
        """Run complete analysis and generate recommendation"""
        logger.info(
            "Starting comprehensive Redis vector store analysis for AutoBot\n"
        )

        data_analysis = await self.analyze_existing_data()
        direct_result = await self.test_direct_redis_access()
        llamaindex_result = await self.test_llamaindex_with_existing_data()
        langchain_result = await self.test_langchain_new_approach()
        migration_analysis = await self.generate_migration_complexity_estimate(
            data_analysis,
        )

        recommendation = self.generate_recommendation(
            data_analysis,
            direct_result[0], direct_result[1],
            llamaindex_result[0], llamaindex_result[1], llamaindex_result[2],
            langchain_result[0], langchain_result[1], langchain_result[2],
            migration_analysis,
        )

        self.print_analysis_report(
            data_analysis, direct_result, llamaindex_result,
            langchain_result, migration_analysis, recommendation,
        )

        return recommendation

    def generate_recommendation(
        self, data_analysis, direct_success, direct_count,
        llamaindex_success, llamaindex_count, llamaindex_assessment,
        langchain_success, langchain_count, langchain_assessment,
        migration_analysis,
    ) -> Dict[str, Any]:
        """Generate final recommendation based on all test results"""
        existing_data_valuable = data_analysis.get("total_documents", 0) > 10000

        if existing_data_valuable and direct_success:
            if llamaindex_success:
                return {
                    "approach": "FIX_LLAMAINDEX",
                    "confidence": "HIGH",
                    "reasoning": [
                        "13,383 high-quality vectors already indexed",
                        "Data is accessible and properly structured",
                        "LlamaIndex can be fixed with minimal effort",
                        "No data migration required",
                    ],
                    "implementation": migration_analysis["llamaindex_fix"],
                }
            elif langchain_success:
                return {
                    "approach": "MIGRATE_TO_LANGCHAIN",
                    "confidence": "MEDIUM",
                    "reasoning": [
                        "LangChain works better out of the box",
                        "Modern langchain-redis package available",
                        "Better async support and error handling",
                        "Worth migration for maintainability",
                    ],
                    "implementation": migration_analysis["langchain_migration"],
                }
            else:
                return {
                    "approach": "INVESTIGATE_FURTHER",
                    "confidence": "LOW",
                    "reasoning": [
                        "Valuable data but neither library works",
                        "Configuration issues need resolution",
                        "May need custom Redis integration",
                    ],
                    "implementation": {
                        "complexity": "HIGH", "time_estimate": "1 week",
                    },
                }
        else:
            return {
                "approach": "START_FRESH_WITH_LANGCHAIN",
                "confidence": "MEDIUM",
                "reasoning": [
                    "Limited existing data or data not accessible",
                    "LangChain provides better foundation",
                    "Modern architecture and documentation",
                ],
                "implementation": migration_analysis["langchain_migration"],
            }

    def print_analysis_report(
        self, data_analysis, direct_results, llamaindex_results,
        langchain_results, migration_analysis, recommendation,
    ):
        """Print comprehensive analysis report"""
        logger.info("\n" + "=" * 80)
        logger.info("AUTOBOT REDIS VECTOR STORE ANALYSIS REPORT")
        logger.info("=" * 80)

        self._print_data_section(data_analysis)
        self._print_test_section(direct_results, llamaindex_results, langchain_results)
        self._print_recommendation_section(recommendation)
        logger.info("\n" + "=" * 80)

    def _print_data_section(self, data_analysis):
        """Print existing data analysis section.

        Helper for print_analysis_report (#825).
        """
        logger.info("\nEXISTING DATA ANALYSIS:")
        logger.info("  Total Documents: %s", data_analysis.get("total_documents", 0))
        logger.info("  Vector Dimensions: %s", data_analysis.get("vector_dimension", "unknown"))
        logger.info("  Index Size: %s MB", data_analysis.get("index_size_mb", 0))
        logger.info("  Algorithm: %s", data_analysis.get("vector_algorithm", "unknown"))

    def _print_test_section(self, direct, llamaindex, langchain):
        """Print integration test results section.

        Helper for print_analysis_report (#825).
        """
        logger.info("\nINTEGRATION TEST RESULTS:")
        for name, results in [("Direct Redis", direct), ("LlamaIndex", llamaindex), ("LangChain", langchain)]:
            status = "OK" if results[0] else "FAILED"
            logger.info(
                "  %s: %s (%s results) - %s", name, status, results[1], results[2],
            )

    def _print_recommendation_section(self, recommendation):
        """Print recommendation section.

        Helper for print_analysis_report (#825).
        """
        logger.info("\nFINAL RECOMMENDATION: %s", recommendation["approach"])
        logger.info("  Confidence: %s", recommendation["confidence"])
        logger.info("  Reasoning:")
        for reason in recommendation["reasoning"]:
            logger.info("    - %s", reason)

        impl = recommendation["implementation"]
        logger.info("\nIMPLEMENTATION PLAN:")
        logger.info("  Complexity: %s", impl.get("complexity", "unknown"))
        logger.info("  Time Estimate: %s", impl.get("time_estimate", "unknown"))
        logger.info("  Risk Level: %s", impl.get("risk", "unknown"))
        logger.info("  Data Migration: %s", impl.get("data_migration", "unknown"))

        if "changes_required" in impl:
            logger.info("  Required Changes:")
            for change in impl["changes_required"]:
                logger.info("    - %s", change)

    async def test_llamaindex_with_existing_data(self) -> Tuple[bool, int, str]:
        """Test LlamaIndex with existing data using correct configuration"""
        logger.info("\nTesting LlamaIndex with existing data...")

        try:
            models = await self.get_available_models()
            llm_model = models[0] if models else "gemma3:270m"
            logger.info("Using LLM model: %s", llm_model)

            _embed_model, index = _configure_llamaindex(
                self.ollama_base_url, self.embedding_model,
                llm_model, self.redis_host, self.redis_port, self.redis_db,
            )

            retriever = index.as_retriever(similarity_top_k=5)
            nodes = await asyncio.to_thread(
                retriever.retrieve, "kubernetes deployment guide",
            )

            result_count = len(nodes)
            logger.info("LlamaIndex retrieval successful: %s results", result_count)

            if result_count > 0:
                for i, node in enumerate(nodes[:2]):
                    logger.info("  Result %s: %s...", i + 1, node.text[:100])

            return True, result_count, _assess_result_quality(result_count)

        except Exception as e:
            logger.error("LlamaIndex test failed: %s", e)
            import traceback
            logger.error(traceback.format_exc())
            return False, 0, "FAILED"


async def main():
    analyzer = RedisVectorStoreAnalyzer()
    recommendation = await analyzer.run_comprehensive_analysis()

    from pathlib import Path

    output_file = Path(
        "/home/kali/Desktop/AutoBot/reports/redis_vector_recommendation.json"
    )
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(recommendation, f, indent=2)

    logger.info("\nDetailed recommendation saved to: %s", output_file)


if __name__ == "__main__":
    asyncio.run(main())
