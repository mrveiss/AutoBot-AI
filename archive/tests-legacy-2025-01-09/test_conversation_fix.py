#!/usr/bin/env python3
"""
Test script to verify the conversation manager fix
"""

import asyncio
import sys
import os

# Add the project root to sys.path
sys.path.insert(0, '/home/kali/Desktop/AutoBot')

async def test_conversation_manager():
    """Test the conversation manager functionality"""
    print("Testing conversation manager fix...")
    
    try:
        # Test 1: Import conversation manager
        print("1. Testing import of conversation manager...")
        from src.conversation import get_conversation_manager
        print("✅ Successfully imported get_conversation_manager")
        
        # Test 2: Get conversation manager instance
        print("2. Testing conversation manager instantiation...")
        manager = get_conversation_manager()
        print(f"✅ Successfully got conversation manager: {manager}")
        
        # Test 3: Test manager functionality
        print("3. Testing conversation manager functionality...")
        conversation = manager.get_or_create_conversation("test123")
        print(f"✅ Successfully created conversation: {conversation.conversation_id}")
        
        # Test 4: Test the validation function from chat_consolidated
        print("4. Testing validation function...")
        from backend.api.chat_consolidated import get_conversation_manager_validated
        get_conversation_manager_func = get_conversation_manager_validated()
        print(f"✅ Successfully got validation function: {get_conversation_manager_func}")
        
        if get_conversation_manager_func is None:
            print("❌ ERROR: get_conversation_manager_validated returned None")
            return False
            
        if not callable(get_conversation_manager_func):
            print("❌ ERROR: get_conversation_manager_validated returned non-callable")
            return False
            
        # Test 5: Test calling the validated function
        print("5. Testing validated function call...")
        manager2 = get_conversation_manager_func()
        print(f"✅ Successfully called validated function: {manager2}")
        
        # Test 6: Test workflow validation
        print("6. Testing workflow validation...")
        from backend.api.chat_consolidated import get_consolidated_workflow_validated
        process_func, result_class = get_consolidated_workflow_validated()
        print(f"✅ Successfully got workflow functions: {process_func}, {result_class}")
        
        if process_func is None:
            print("❌ ERROR: process_chat_message_unified is None")
            return False
            
        if result_class is None:
            print("❌ ERROR: ConsolidatedWorkflowResult is None")
            return False
        
        print("✅ All tests passed! Conversation manager fix is working correctly.")
        return True
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_conversation_manager())
    if success:
        print("\n🎉 SUCCESS: Conversation manager is working correctly!")
        sys.exit(0)
    else:
        print("\n💥 FAILURE: Conversation manager has issues!")
        sys.exit(1)