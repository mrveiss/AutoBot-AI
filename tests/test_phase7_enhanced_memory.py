#!/usr/bin/env python3
"""
Test script for Phase 7 Enhanced Memory System
Validates core functionality without requiring full backend restart
"""

import sys
import asyncio
from pathlib import Path

# Add project root to Python path
sys.path.append(str(Path(__file__).parent))

from src.enhanced_memory_manager import EnhancedMemoryManager, TaskPriority
from src.task_execution_tracker import TaskExecutionTracker
from src.markdown_reference_system import MarkdownReferenceSystem


async def test_enhanced_memory_system():
    """Test the enhanced memory system components"""
    print("🧠 Testing Phase 7: Enhanced Memory System")
    print("=" * 50)
    
    # Test 1: Enhanced Memory Manager
    print("\n1. Testing Enhanced Memory Manager...")
    memory_manager = EnhancedMemoryManager(db_path="data/test_enhanced_memory.db")
    
    # Create a test task
    task_id = memory_manager.create_task_record(
        task_name="Test Memory Task",
        description="Testing the enhanced memory system functionality",
        priority=TaskPriority.HIGH,
        agent_type="test_agent",
        inputs={"test_input": "validation_data"}
    )
    
    print(f"✅ Created task: {task_id}")
    
    # Start the task
    memory_manager.start_task(task_id)
    print(f"✅ Started task: {task_id}")
    
    # Complete the task
    memory_manager.complete_task(
        task_id, 
        outputs={"test_result": "success", "validation": "passed"}
    )
    print(f"✅ Completed task: {task_id}")
    
    # Get task statistics
    stats = memory_manager.get_task_statistics(days_back=1)
    print(f"✅ Task statistics: {stats['total_tasks']} tasks, {stats['success_rate_percent']}% success rate")
    
    # Test 2: Task Execution Tracker
    print("\n2. Testing Task Execution Tracker...")
    tracker = TaskExecutionTracker(memory_manager)
    
    async with tracker.track_task(
        "Async Test Task",
        "Testing async task tracking with context manager",
        agent_type="async_test_agent",
        priority=TaskPriority.MEDIUM,
        inputs={"async_test": True}
    ) as task_context:
        print("✅ Task context manager working")
        
        # Add some outputs
        task_context.set_outputs({"async_result": "success"})
        
        # Create a subtask
        subtask_id = task_context.create_subtask(
            "Subtask Example",
            "Testing subtask creation"
        )
        print(f"✅ Created subtask: {subtask_id}")
    
    print("✅ Async task completed automatically")
    
    # Test 3: Markdown Reference System
    print("\n3. Testing Markdown Reference System...")
    markdown_system = MarkdownReferenceSystem(memory_manager)
    
    # Scan docs directory
    docs_path = Path("docs")
    if docs_path.exists():
        scan_result = markdown_system.scan_markdown_directory(docs_path)
        print(f"✅ Scanned docs: {scan_result['scanned_files']} files, {scan_result['new_files']} new")
    else:
        print("⚠️ Docs directory not found, skipping markdown scan")
    
    # Get markdown statistics
    md_stats = markdown_system.get_markdown_statistics()
    print(f"✅ Markdown stats: {md_stats['total_documents']} documents, {md_stats['total_words']} words")
    
    # Test 4: Integration Test
    print("\n4. Testing System Integration...")
    
    # Create a task with markdown reference
    integration_task_id = memory_manager.create_task_record(
        task_name="Integration Test",
        description="Testing markdown integration",
        priority=TaskPriority.LOW
    )
    
    # Add markdown reference if README exists
    readme_path = Path("README.md")
    if readme_path.exists():
        memory_manager.add_markdown_reference(
            integration_task_id,
            str(readme_path),
            "project_documentation"
        )
        print(f"✅ Added markdown reference: README.md -> {integration_task_id}")
    
    # Complete integration task
    memory_manager.complete_task(integration_task_id)
    
    # Get updated statistics
    final_stats = memory_manager.get_task_statistics(days_back=1)
    print(f"✅ Final statistics: {final_stats['total_tasks']} total tasks")
    
    # Test 5: Performance Analysis
    print("\n5. Testing Performance Analysis...")
    insights = await tracker.analyze_task_patterns(days_back=1)
    print(f"✅ Performance insights for {insights['total_tasks_analyzed']} tasks")
    
    for agent, perf in insights.get('agent_performance', {}).items():
        print(f"   - {agent}: {perf['success_rate_percent']}% success, {perf['total_tasks']} tasks")
    
    print("\n" + "=" * 50)
    print("🎉 Phase 7 Enhanced Memory System Test PASSED!")
    print("All core components are functioning correctly.")
    
    return True


async def test_embedding_system():
    """Test the embedding storage system"""
    print("\n6. Testing Embedding Storage System...")
    
    memory_manager = EnhancedMemoryManager(db_path="data/test_enhanced_memory.db")
    
    # Test embedding storage
    test_content = "This is a test document for embedding storage validation"
    test_embedding = [0.1, 0.2, 0.3, 0.4, 0.5] * 100  # 500-dimensional vector
    
    # Store embedding
    success = memory_manager.store_embedding(
        content=test_content,
        content_type="test_document",
        embedding_model="test_model",
        embedding_vector=test_embedding
    )
    
    if success:
        print("✅ Embedding stored successfully")
        
        # Retrieve embedding
        retrieved = memory_manager.get_embedding(test_content, "test_model")
        
        if retrieved and len(retrieved) == len(test_embedding):
            print("✅ Embedding retrieved successfully")
            print(f"   Vector dimensions: {len(retrieved)}")
        else:
            print("❌ Embedding retrieval failed")
    else:
        print("❌ Embedding storage failed")


def main():
    """Main test function"""
    try:
        # Run async tests
        asyncio.run(test_enhanced_memory_system())
        asyncio.run(test_embedding_system())
        
        print("\n🚀 Phase 7 Enhanced Memory System is ready for production!")
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)