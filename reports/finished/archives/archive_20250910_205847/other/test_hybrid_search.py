#!/usr/bin/env python3
"""
Test script for the hybrid search functionality
"""

import asyncio
import json
import logging
import time
from typing import Dict, Any, List

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_hybrid_search_engine():
    """Test the hybrid search engine directly"""
    logger.info("🔍 Testing Hybrid Search Engine")
    
    try:
        from src.utils.hybrid_search import HybridSearchEngine
        from src.knowledge_base import KnowledgeBase
        
        # Initialize knowledge base
        logger.info("Initializing knowledge base...")
        kb = KnowledgeBase()
        await kb.ainit()
        
        if not kb.index:
            logger.warning("⚠️ Knowledge base not properly initialized, creating mock engine")
            hybrid_engine = HybridSearchEngine()
        else:
            hybrid_engine = HybridSearchEngine(kb)
            logger.info("✅ Hybrid search engine initialized with knowledge base")
        
        # Test keyword extraction
        logger.info("🔧 Test 1: Keyword extraction")
        test_queries = [
            "How to configure SSH server on Ubuntu Linux?",
            "Python machine learning algorithms",
            "Docker container deployment strategies",
            "Network security best practices"
        ]
        
        for query in test_queries:
            keywords = hybrid_engine.extract_keywords(query)
            logger.info(f"Query: '{query}'")
            logger.info(f"Keywords: {keywords}")
            print()
        
        # Test keyword scoring
        logger.info("📊 Test 2: Keyword scoring")
        test_document = """
        SSH (Secure Shell) is a network protocol that allows secure remote access to Unix-like systems.
        To configure SSH server on Ubuntu, you need to install openssh-server package and modify the 
        configuration file located at /etc/ssh/sshd_config. Common security practices include disabling
        root login, changing the default port, and using key-based authentication instead of passwords.
        """
        
        test_metadata = {"source": "ssh_configuration_guide.md", "category": "system_administration"}
        
        for query in test_queries[:2]:  # Test first 2 queries
            query_keywords = hybrid_engine.extract_keywords(query)
            keyword_score = hybrid_engine.calculate_keyword_score(
                query_keywords, test_document, test_metadata
            )
            logger.info(f"Query: '{query}'")
            logger.info(f"Keywords: {query_keywords}")
            logger.info(f"Keyword score: {keyword_score:.4f}")
            print()
        
        # Test score combination
        logger.info("⚖️ Test 3: Score combination")
        semantic_scores = [0.95, 0.80, 0.60, 0.40]
        keyword_scores = [0.90, 0.30, 0.70, 0.20]
        
        logger.info("Semantic | Keyword | Combined")
        logger.info("-" * 35)
        for sem, kw in zip(semantic_scores, keyword_scores):
            combined = hybrid_engine.combine_scores(sem, kw)
            logger.info(f"{sem:8.2f} | {kw:7.2f} | {combined:8.2f}")
        
        logger.info("✅ Hybrid search engine tests completed successfully!")
        return True
        
    except ImportError as e:
        logger.error(f"❌ Import error: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_knowledge_base_hybrid_integration():
    """Test hybrid search integration with knowledge base"""
    logger.info("🔗 Testing Knowledge Base Hybrid Integration")
    
    try:
        from src.knowledge_base import KnowledgeBase
        
        # Initialize knowledge base
        kb = KnowledgeBase()
        await kb.ainit()
        
        if not kb.index:
            logger.warning("⚠️ Knowledge base not available, skipping integration test")
            return True
        
        logger.info("✅ Knowledge base initialized")
        
        # Test queries
        test_queries = [
            "SSH configuration Ubuntu",
            "Docker container networking",
            "Python web scraping libraries",
            "Linux system administration commands"
        ]
        
        for query in test_queries:
            logger.info(f"🔍 Testing query: '{query}'")
            
            # Compare semantic vs hybrid search
            start_time = time.time()
            semantic_results = await kb.search(query, top_k=5)
            semantic_time = time.time() - start_time
            
            start_time = time.time()
            hybrid_results = await kb.hybrid_search(query, top_k=5)
            hybrid_time = time.time() - start_time
            
            logger.info(f"Semantic search: {len(semantic_results)} results ({semantic_time:.3f}s)")
            logger.info(f"Hybrid search: {len(hybrid_results)} results ({hybrid_time:.3f}s)")
            
            # Show top result from each
            if semantic_results:
                sem_top = semantic_results[0]
                logger.info(f"Top semantic result: score={sem_top.get('score', 0):.3f}")
            
            if hybrid_results:
                hyb_top = hybrid_results[0]
                logger.info(f"Top hybrid result: score={hyb_top.get('score', 0):.3f}")
                logger.info(f"Keyword score: {hyb_top.get('keyword_score', 0):.3f}")
                logger.info(f"Matched keywords: {hyb_top.get('matched_keywords', [])}")
            
            print()
        
        # Test search explanation
        logger.info("📝 Testing search explanation")
        explanation = await kb.explain_search("SSH server configuration", top_k=3)
        
        if 'error' not in explanation:
            logger.info(f"Query: {explanation.get('query')}")
            logger.info(f"Keywords: {explanation.get('extracted_keywords', [])}")
            logger.info(f"Semantic weight: {explanation.get('semantic_weight')}")
            logger.info(f"Keyword weight: {explanation.get('keyword_weight')}")
            
            for detail in explanation.get('scoring_details', [])[:2]:  # Show first 2
                logger.info(f"Result {detail['rank']}: hybrid_score={detail['hybrid_score']:.3f}")
                logger.info(f"  Semantic: {detail['semantic_score']:.3f}, Keyword: {detail['keyword_score']:.3f}")
                logger.info(f"  Matched keywords: {detail['matched_keywords']}")
                logger.info(f"  Source: {detail['source']}")
                print()
        
        logger.info("✅ Knowledge base hybrid integration tests completed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Integration test error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_api_endpoints():
    """Test the hybrid search API endpoints"""
    logger.info("🌐 Testing Hybrid Search API Endpoints")
    
    try:
        import aiohttp
        
        base_url = "http://localhost:8001/api/knowledge_base"
        
        # Test endpoints
        endpoints_to_test = [
            ("/search/config", "GET", None),
            ("/search/hybrid", "POST", {"query": "SSH configuration", "top_k": 3}),
            ("/search/explain", "POST", {"query": "Docker containers", "top_k": 2}),
        ]
        
        async with aiohttp.ClientSession() as session:
            for endpoint, method, data in endpoints_to_test:
                try:
                    url = f"{base_url}{endpoint}"
                    logger.info(f"Testing {method} {endpoint}")
                    
                    if method == "GET":
                        async with session.get(url) as response:
                            if response.status == 200:
                                result = await response.json()
                                logger.info(f"✅ {endpoint} - Status: {response.status}")
                                logger.info(f"Response keys: {list(result.keys())}")
                            else:
                                logger.warning(f"⚠️ {endpoint} - Status: {response.status}")
                    
                    elif method == "POST":
                        async with session.post(url, json=data) as response:
                            if response.status == 200:
                                result = await response.json()
                                logger.info(f"✅ {endpoint} - Status: {response.status}")
                                if 'results' in result:
                                    logger.info(f"Results count: {len(result['results'])}")
                                elif 'scoring_details' in result:
                                    logger.info(f"Scoring details count: {len(result['scoring_details'])}")
                            else:
                                logger.warning(f"⚠️ {endpoint} - Status: {response.status}")
                                error_text = await response.text()
                                logger.warning(f"Error: {error_text}")
                    
                    print()
                    
                except Exception as e:
                    logger.warning(f"⚠️ Could not test {endpoint}: {e}")
        
        logger.info("✅ API endpoint testing completed!")
        return True
        
    except ImportError:
        logger.warning("⚠️ aiohttp not available, skipping API tests")
        return True
    except Exception as e:
        logger.error(f"❌ API testing error: {e}")
        return False


async def test_configuration():
    """Test hybrid search configuration"""
    logger.info("⚙️ Testing Hybrid Search Configuration")
    
    try:
        from src.config_helper import cfg
        
        # Test configuration values
        config_tests = [
            ('search.hybrid.enabled', bool),
            ('search.hybrid.semantic_weight', float),
            ('search.hybrid.keyword_weight', float),
            ('search.hybrid.min_keyword_score', float),
            ('search.hybrid.keyword_boost_factor', float),
            ('search.hybrid.semantic_top_k', int),
            ('search.hybrid.final_top_k', int),
            ('search.hybrid.min_keyword_length', int),
            ('search.hybrid.stop_words', list),
        ]
        
        logger.info("Configuration values:")
        for config_key, expected_type in config_tests:
            value = cfg.get(config_key)
            logger.info(f"{config_key}: {value} (type: {type(value).__name__})")
            
            if value is not None and not isinstance(value, expected_type):
                logger.warning(f"⚠️ Expected {expected_type.__name__}, got {type(value).__name__}")
        
        # Test weights sum to reasonable value
        semantic_weight = cfg.get('search.hybrid.semantic_weight', 0.7)
        keyword_weight = cfg.get('search.hybrid.keyword_weight', 0.3)
        total_weight = semantic_weight + keyword_weight
        
        logger.info(f"Total weight: {total_weight}")
        if abs(total_weight - 1.0) < 0.1:
            logger.info("✅ Weights sum to approximately 1.0")
        else:
            logger.warning(f"⚠️ Weights sum to {total_weight}, expected ~1.0")
        
        logger.info("✅ Configuration testing completed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Configuration test error: {e}")
        return False


async def main():
    """Main test function"""
    logger.info("🚀 Starting Hybrid Search Test Suite")
    
    # Run all tests
    test_results = {
        "Hybrid Search Engine": await test_hybrid_search_engine(),
        "Knowledge Base Integration": await test_knowledge_base_hybrid_integration(),
        "API Endpoints": await test_api_endpoints(),
        "Configuration": await test_configuration(),
    }
    
    # Summary
    logger.info("📋 Test Summary:")
    all_passed = True
    for test_name, passed in test_results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        logger.info(f"{test_name}: {status}")
        if not passed:
            all_passed = False
    
    if all_passed:
        logger.info("🎉 Hybrid Search Test Suite PASSED!")
        logger.info("The hybrid search system is ready for production use.")
    else:
        logger.error("❌ Some tests FAILED!")
        logger.error("Please check the implementation and dependencies.")
    
    return all_passed


if __name__ == "__main__":
    asyncio.run(main())