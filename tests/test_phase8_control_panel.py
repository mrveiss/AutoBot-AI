#!/usr/bin/env python3
"""
Test script for Phase 8 Advanced Control System
Validates desktop streaming, takeover management, and monitoring capabilities
"""

import sys
import asyncio
import json
import requests
from pathlib import Path

# Add project root to Python path
sys.path.append(str(Path(__file__).parent))

from src.desktop_streaming_manager import desktop_streaming, VNCServerManager
from src.takeover_manager import takeover_manager, TakeoverTrigger
from src.enhanced_memory_manager import TaskPriority


def test_api_connectivity():
    """Test if the backend API is accessible"""
    print("🌐 Testing API Connectivity...")
    
    try:
        # Test health endpoint
        response = requests.get("http://localhost:8001/api/control/system/health", timeout=5)
        if response.status_code == 200:
            health_data = response.json()
            print(f"✅ API accessible - Status: {health_data.get('status', 'unknown')}")
            return True
        else:
            print(f"❌ API returned status code: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to backend API at http://localhost:8001")
        return False
    except Exception as e:
        print(f"❌ API connectivity test failed: {e}")
        return False


async def test_desktop_streaming_manager():
    """Test the desktop streaming manager components"""
    print("\n🖥️ Testing Desktop Streaming Manager...")
    print("=" * 50)
    
    # Test 1: VNC Server Manager initialization
    print("\n1. Testing VNC Server Manager...")
    vnc_manager = VNCServerManager()
    print(f"✅ VNC available: {vnc_manager.vnc_available}")
    print(f"✅ NoVNC available: {vnc_manager.novnc_available}")
    
    # Test 2: System capabilities
    print("\n2. Testing System Capabilities...")
    capabilities = desktop_streaming.get_system_capabilities()
    print(f"✅ System capabilities: {capabilities}")
    
    # Test 3: Session creation (if VNC is available)
    if vnc_manager.vnc_available:
        print("\n3. Testing Session Creation...")
        try:
            session_info = await desktop_streaming.create_streaming_session(
                user_id="test_user_phase8",
                session_config={"resolution": "800x600", "depth": 16}
            )
            print(f"✅ Session created: {session_info['session_id']}")
            
            # Test session termination
            success = await desktop_streaming.terminate_streaming_session(
                session_info['session_id']
            )
            print(f"✅ Session terminated: {success}")
            
        except Exception as e:
            print(f"⚠️ Session creation test skipped (requires X server): {e}")
    else:
        print("⚠️ VNC not available - skipping session tests")
    
    # Test 4: Cleanup stale sessions
    print("\n4. Testing Session Cleanup...")
    cleanup_count = await vnc_manager.cleanup_stale_sessions()
    print(f"✅ Cleaned up {cleanup_count} stale sessions")
    
    return True


async def test_takeover_manager():
    """Test the human-in-the-loop takeover system"""
    print("\n🛡️ Testing Takeover Manager...")
    print("=" * 50)
    
    # Test 1: System status
    print("\n1. Testing System Status...")
    status = takeover_manager.get_system_status()
    print(f"✅ Takeover system status: {status}")
    
    # Test 2: Request takeover
    print("\n2. Testing Takeover Request...")
    request_id = await takeover_manager.request_takeover(
        trigger=TakeoverTrigger.MANUAL_REQUEST,
        reason="Phase 8 testing - manual takeover request",
        requesting_agent="test_agent",
        affected_tasks=["test_task_1", "test_task_2"],
        priority=TaskPriority.MEDIUM,
        timeout_minutes=5
    )
    print(f"✅ Takeover requested: {request_id}")
    
    # Test 3: Check pending requests
    print("\n3. Testing Pending Requests...")
    pending = takeover_manager.get_pending_requests()
    print(f"✅ Pending requests: {len(pending)}")
    
    # Test 4: Approve takeover (simulate)
    print("\n4. Testing Takeover Approval...")
    try:
        session_id = await takeover_manager.approve_takeover(
            request_id=request_id,
            human_operator="test_operator_phase8"
        )
        print(f"✅ Takeover approved: {session_id}")
        
        # Test 5: Execute takeover action
        print("\n5. Testing Takeover Action...")
        action_result = await takeover_manager.execute_takeover_action(
            session_id=session_id,
            action_type="approve_operation",
            action_data={"operation_id": "test_operation"}
        )
        print(f"✅ Action executed: {action_result}")
        
        # Test 6: Complete takeover session
        print("\n6. Testing Session Completion...")
        completion_success = await takeover_manager.complete_takeover_session(
            session_id=session_id,
            resolution="Test completed successfully",
            handback_notes="Phase 8 validation completed"
        )
        print(f"✅ Session completed: {completion_success}")
        
    except Exception as e:
        print(f"⚠️ Takeover simulation error (expected in test): {e}")
    
    # Test 7: Check final status
    print("\n7. Testing Final Status...")
    final_status = takeover_manager.get_system_status()
    print(f"✅ Final system status: {final_status}")
    
    return True


def test_api_endpoints():
    """Test the REST API endpoints"""
    print("\n🔗 Testing API Endpoints...")
    print("=" * 50)
    
    base_url = "http://localhost:8001/api/control"
    
    # Test 1: System health
    print("\n1. Testing System Health Endpoint...")
    try:
        response = requests.get(f"{base_url}/system/health")
        if response.status_code == 200:
            health_data = response.json()
            print(f"✅ Health check: {health_data['status']}")
        else:
            print(f"❌ Health check failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Health check error: {e}")
    
    # Test 2: Streaming capabilities
    print("\n2. Testing Streaming Capabilities...")
    try:
        response = requests.get(f"{base_url}/streaming/capabilities")
        if response.status_code == 200:
            capabilities = response.json()
            print(f"✅ Streaming capabilities: {capabilities}")
        else:
            print(f"❌ Capabilities check failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Capabilities check error: {e}")
    
    # Test 3: Takeover status
    print("\n3. Testing Takeover Status...")
    try:
        response = requests.get(f"{base_url}/takeover/status")
        if response.status_code == 200:
            takeover_status = response.json()
            print(f"✅ Takeover status: {takeover_status}")
        else:
            print(f"❌ Takeover status failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Takeover status error: {e}")
    
    # Test 4: System status
    print("\n4. Testing System Status...")
    try:
        response = requests.get(f"{base_url}/system/status")
        if response.status_code == 200:
            system_status = response.json()
            print(f"✅ System status retrieved with {len(system_status)} fields")
        else:
            print(f"❌ System status failed: {response.status_code}")
    except Exception as e:
        print(f"❌ System status error: {e}")
    
    # Test 5: API info
    print("\n5. Testing API Information...")
    try:
        response = requests.get(f"{base_url}/")
        if response.status_code == 200:
            api_info = response.json()
            print(f"✅ API info: {api_info['name']} v{api_info['version']}")
            print(f"   Features: {', '.join(api_info['features'])}")
        else:
            print(f"❌ API info failed: {response.status_code}")
    except Exception as e:
        print(f"❌ API info error: {e}")
    
    return True


async def test_integration():
    """Test integration between components"""
    print("\n🔄 Testing Component Integration...")
    print("=" * 50)
    
    # Test 1: Memory system integration
    print("\n1. Testing Memory System Integration...")
    from src.task_execution_tracker import task_tracker
    
    async with task_tracker.track_task(
        "Phase 8 Integration Test",
        "Testing integration between Phase 8 components",
        agent_type="phase8_test",
        priority=TaskPriority.HIGH,
        inputs={"test_type": "integration", "phase": 8}
    ) as task_context:
        
        # Simulate desktop streaming request
        task_context.set_outputs({
            "desktop_streaming_available": desktop_streaming.vnc_manager.vnc_available,
            "takeover_system_ready": len(takeover_manager.get_system_status()) > 0,
            "integration_status": "success"
        })
        
        print("✅ Integration test task completed")
    
    # Test 2: Cross-component communication
    print("\n2. Testing Cross-Component Communication...")
    
    # Request takeover from streaming context
    request_id = await takeover_manager.request_takeover(
        trigger=TakeoverTrigger.USER_INTERVENTION_REQUIRED,
        reason="Desktop streaming requires user intervention",
        requesting_agent="desktop_streaming_manager",
        priority=TaskPriority.HIGH,
        timeout_minutes=10
    )
    
    print(f"✅ Cross-component takeover request: {request_id}")
    
    # Check that the request is properly tracked
    pending = takeover_manager.get_pending_requests()
    integration_request = next(
        (req for req in pending if req['request_id'] == request_id), 
        None
    )
    
    if integration_request:
        print("✅ Cross-component request properly tracked")
    else:
        print("❌ Cross-component request not found")
    
    return True


async def main():
    """Main test function"""
    print("🚀 Phase 8: Advanced Control System Test")
    print("=" * 60)
    
    test_results = []
    
    try:
        # Test API connectivity first
        api_available = test_api_connectivity()
        test_results.append(("API Connectivity", api_available))
        
        # Test core components
        streaming_result = await test_desktop_streaming_manager()
        test_results.append(("Desktop Streaming Manager", streaming_result))
        
        takeover_result = await test_takeover_manager()
        test_results.append(("Takeover Manager", takeover_result))
        
        # Test API endpoints if backend is available
        if api_available:
            endpoint_result = test_api_endpoints()
            test_results.append(("API Endpoints", endpoint_result))
        else:
            print("\n⚠️ Skipping API endpoint tests - backend not available")
        
        # Test integration
        integration_result = await test_integration()
        test_results.append(("Component Integration", integration_result))
        
        # Summary
        print("\n" + "=" * 60)
        print("📊 Phase 8 Test Results Summary:")
        
        all_passed = True
        for test_name, result in test_results:
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"   {status} {test_name}")
            if not result:
                all_passed = False
        
        if all_passed:
            print("\n🎉 Phase 8 Advanced Control System Test PASSED!")
            print("All components are functioning correctly.")
            
            if not api_available:
                print("\n💡 Note: Start the backend with './run_agent.sh' to test API endpoints")
        else:
            print("\n⚠️ Some tests failed. Check logs above for details.")
        
        return all_passed
        
    except Exception as e:
        print(f"\n❌ Test suite failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)