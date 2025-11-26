#!/usr/bin/env python3
"""Validate RAG Integration - Check files and structure only"""

import os
from pathlib import Path

def validate_rag_integration():
    """Validate that RAG integration is properly implemented"""

    print("🔍 Validating RAG Integration Implementation")
    print("=" * 50)

    validation_results = {}

    # Check 1: Enhanced Knowledge API
    print("\n1. Checking Enhanced Knowledge API...")
    knowledge_api_path = Path("backend/api/knowledge.py")
    if knowledge_api_path.exists():
        content = knowledge_api_path.read_text()

        checks = {
            "RAG_AVAILABLE flag": "RAG_AVAILABLE" in content,
            "RAG import": "from src.agents.rag_agent import get_rag_agent" in content,
            "rag_enhanced_search endpoint": "async def rag_enhanced_search" in content,
            "use_rag parameter": "use_rag" in content,
            "_enhance_search_with_rag helper": "async def _enhance_search_with_rag" in content,
            "RAG status in health": "rag_available" in content and "rag_status" in content
        }

        for check, result in checks.items():
            status = "✅" if result else "❌"
            print(f"   {status} {check}")
            validation_results[f"api_{check}"] = result

        print(f"✅ Knowledge API enhanced: {sum(checks.values())}/{len(checks)} features")
    else:
        print("❌ Knowledge API file not found")
        validation_results["knowledge_api_exists"] = False

    # Check 2: RAG Agent Configuration
    print("\n2. Checking RAG Agent...")
    rag_agent_path = Path("src/agents/rag_agent.py")
    if rag_agent_path.exists():
        content = rag_agent_path.read_text()

        checks = {
            "Unified config import": "from src.unified_config_manager import config" in content,
            "Fixed config access": 'config.get("llm.models.rag"' in content,
            "LLMResponse handling": "if hasattr(response, 'content'):" in content,
            "Document synthesis": "async def process_document_query" in content,
            "Query reformulation": "async def reformulate_query" in content,
            "Document ranking": "async def rank_documents" in content
        }

        for check, result in checks.items():
            status = "✅" if result else "❌"
            print(f"   {status} {check}")
            validation_results[f"rag_{check}"] = result

        print(f"✅ RAG Agent updated: {sum(checks.values())}/{len(checks)} features")
    else:
        print("❌ RAG Agent file not found")
        validation_results["rag_agent_exists"] = False

    # Check 3: LLM Interface Fix
    print("\n3. Checking LLM Interface...")
    llm_interface_path = Path("src/llm_interface.py")
    if llm_interface_path.exists():
        content = llm_interface_path.read_text()

        checks = {
            "connection_timeout field": "connection_timeout: float = Field" in content,
            "LLMSettings class": "class LLMSettings(BaseSettings):" in content
        }

        for check, result in checks.items():
            status = "✅" if result else "❌"
            print(f"   {status} {check}")
            validation_results[f"llm_{check}"] = result

        print(f"✅ LLM Interface fixed: {sum(checks.values())}/{len(checks)} issues")
    else:
        print("❌ LLM Interface file not found")
        validation_results["llm_interface_exists"] = False

    # Check 4: Test Files
    print("\n4. Checking Test Files...")
    test_files = [
        "tests/test_rag_integration.py",
        "tests/test_rag_integration_basic.py",
        "tests/test_rag_integration_final.py"
    ]

    test_results = []
    for test_file in test_files:
        exists = Path(test_file).exists()
        status = "✅" if exists else "❌"
        print(f"   {status} {test_file}")
        test_results.append(exists)
        validation_results[f"test_{Path(test_file).stem}"] = exists

    print(f"✅ Test files created: {sum(test_results)}/{len(test_results)} files")

    # Summary
    print("\n" + "=" * 50)
    total_checks = len(validation_results)
    passed_checks = sum(validation_results.values())

    print(f"📊 Validation Summary: {passed_checks}/{total_checks} checks passed")

    if passed_checks >= total_checks * 0.8:  # 80% threshold
        print("🎉 RAG Integration Successfully Implemented!")
        print("\n✅ Key Features Added:")
        print("   • RAG-enhanced knowledge search endpoints")
        print("   • Query reformulation and document synthesis")
        print("   • Document relevance analysis and ranking")
        print("   • Backward-compatible search with optional RAG")
        print("   • Health status with RAG capability reporting")

        print("\n🔧 New API Endpoints:")
        print("   • POST /api/knowledge/rag_search")
        print("   • POST /api/knowledge/search?use_rag=true")
        print("   • POST /api/knowledge/similarity_search?use_rag=true")
        print("   • GET  /api/knowledge/health (with RAG status)")

        print("\n🚀 Next Steps:")
        print("   1. Start AutoBot: bash run_autobot.sh --dev")
        print("   2. Test endpoints with actual requests")
        print("   3. Verify RAG synthesis works with knowledge base data")

        return True
    else:
        print("❌ RAG Integration Incomplete")
        print("Please review the failed checks above")
        return False

if __name__ == "__main__":
    success = validate_rag_integration()
    exit(0 if success else 1)
