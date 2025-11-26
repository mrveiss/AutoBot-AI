#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Simple validation script for Chat Knowledge Management System
Tests the backend components without requiring a full server restart
"""

import asyncio
import json
import logging
import tempfile
import uuid
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_chat_knowledge_components():
    """Test the chat knowledge management components"""
    logger.info("🧪 Testing Chat Knowledge Management Components")

    try:
        # Import the components
        from backend.api.chat_knowledge import (
            ChatKnowledgeManager,
            KnowledgeDecision,
            FileAssociationType
        )

        # Initialize manager
        manager = ChatKnowledgeManager()
        logger.info("✅ ChatKnowledgeManager initialized")

        # Test chat context creation
        test_chat_id = f"test_chat_{uuid.uuid4().hex[:8]}"
        context = await manager.create_or_update_context(
            chat_id=test_chat_id,
            topic="Test Chat for Knowledge Management",
            keywords=["test", "knowledge", "management"]
        )
        logger.info(f"✅ Context created for chat: {context.chat_id}")

        # Test temporary knowledge addition
        knowledge_id = await manager.add_temporary_knowledge(
            chat_id=test_chat_id,
            content="This is a test knowledge item that demonstrates the chat knowledge management system.",
            metadata={"type": "test", "priority": "medium"}
        )
        logger.info(f"✅ Temporary knowledge added: {knowledge_id}")

        # Test getting knowledge for decision
        pending_items = await manager.get_knowledge_for_decision(test_chat_id)
        logger.info(f"✅ Retrieved {len(pending_items)} pending knowledge items")

        if pending_items:
            # Test applying a knowledge decision
            success = await manager.apply_knowledge_decision(
                chat_id=test_chat_id,
                knowledge_id=pending_items[0]["id"],
                decision=KnowledgeDecision.KEEP_TEMPORARY
            )
            logger.info(f"✅ Knowledge decision applied: {success}")

        # Test file association
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("Test file content for chat knowledge system validation")
            temp_file_path = f.name

        association = await manager.associate_file(
            chat_id=test_chat_id,
            file_path=temp_file_path,
            association_type=FileAssociationType.UPLOAD,
            metadata={"test": True}
        )
        logger.info(f"✅ File associated: {association.file_name}")

        # Test knowledge search
        search_results = await manager.search_chat_knowledge(
            query="test knowledge",
            chat_id=test_chat_id,
            include_temporary=True
        )
        logger.info(f"✅ Search returned {len(search_results)} results")

        logger.info("🎉 All chat knowledge components working correctly!")
        return True

    except Exception as e:
        logger.error(f"❌ Component test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_frontend_components():
    """Test frontend component compilation"""
    logger.info("🧪 Testing Frontend Components")

    try:
        # Check if Vue components exist and have correct structure
        import os

        components_to_check = [
            "autobot-vue/src/components/KnowledgePersistenceDialog.vue",
            "autobot-vue/src/components/AdvancedStepConfirmationModal.vue",
            "autobot-vue/src/composables/useToast.js"
        ]

        for component_path in components_to_check:
            if os.path.exists(component_path):
                with open(component_path, 'r') as f:
                    content = f.read()
                    if len(content) > 100:  # Basic content check
                        logger.info(f"✅ Component exists and has content: {os.path.basename(component_path)}")
                    else:
                        logger.warning(f"⚠️ Component seems empty: {os.path.basename(component_path)}")
            else:
                logger.error(f"❌ Component missing: {os.path.basename(component_path)}")
                return False

        logger.info("🎉 All frontend components are present!")
        return True

    except Exception as e:
        logger.error(f"❌ Frontend component check failed: {e}")
        return False


def test_api_endpoints():
    """Test API endpoint definitions"""
    logger.info("🧪 Testing API Endpoints")

    try:
        from backend.api.chat_knowledge import router

        routes = router.routes
        expected_endpoints = [
            "/context/create",
            "/files/associate",
            "/files/upload",
            "/knowledge/add_temporary",
            "/knowledge/pending",
            "/knowledge/decide",
            "/compile",
            "/search",
            "/context"
        ]

        found_endpoints = []
        for route in routes:
            path = str(route.path)
            found_endpoints.append(path)
            logger.info(f"✅ Endpoint found: {route.methods} {path}")

        missing_endpoints = []
        for expected in expected_endpoints:
            if not any(expected in found for found in found_endpoints):
                missing_endpoints.append(expected)

        if missing_endpoints:
            logger.warning(f"⚠️ Missing endpoints: {missing_endpoints}")
        else:
            logger.info("🎉 All expected API endpoints are defined!")

        return len(missing_endpoints) == 0

    except Exception as e:
        logger.error(f"❌ API endpoint test failed: {e}")
        return False


async def main():
    """Run all validation tests"""
    logger.info("🎯 Chat Knowledge Management System Validation")
    logger.info("=" * 60)

    tests = [
        ("Backend Components", test_chat_knowledge_components()),
        ("Frontend Components", test_frontend_components()),
        ("API Endpoints", test_api_endpoints())
    ]

    results = []
    for test_name, test_func in tests:
        logger.info(f"Running {test_name}...")
        try:
            if asyncio.iscoroutine(test_func):
                result = await test_func
            else:
                result = test_func
            results.append((test_name, result))
            status = "✅ PASSED" if result else "❌ FAILED"
            logger.info(f"{status} - {test_name}")
        except Exception as e:
            logger.error(f"❌ EXCEPTION in {test_name}: {e}")
            results.append((test_name, False))

        logger.info("-" * 40)

    # Summary
    passed = sum(1 for _, result in results if result)
    total = len(results)

    logger.info("=" * 60)
    logger.info("📊 VALIDATION SUMMARY")
    logger.info("=" * 60)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"{status} {test_name}")

    logger.info("-" * 60)
    logger.info(f"🎯 RESULT: {passed}/{total} tests passed")

    if passed == total:
        logger.info("🎉 VALIDATION SUCCESSFUL - System ready for deployment!")
        logger.info("💡 To enable in production, restart backend with: ./run_agent.sh")
    else:
        logger.warning(f"⚠️ {total - passed} validation issues found")

    return passed == total

if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
