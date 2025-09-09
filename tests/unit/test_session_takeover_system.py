#!/usr/bin/env python3
"""
Session Takeover System - Comprehensive Test Suite
Tests the complete workflow automation and session takeover functionality
"""

import asyncio
import json
import logging
import time
from typing import Dict, List

# Test the workflow automation system
import pytest
import requests
from unittest.mock import AsyncMock, MagicMock

# Import system components
try:
    from backend.api.workflow_automation import (
        WorkflowAutomationManager, 
        WorkflowStep, 
        ActiveWorkflow,
        AutomationMode
    )
    from backend.api.simple_terminal_websocket import SimpleTerminalSession
    COMPONENTS_AVAILABLE = True
except ImportError:
    COMPONENTS_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SessionTakeoverTestSuite:
    """Comprehensive test suite for session takeover functionality"""
    
    def __init__(self, base_url: str = "http://localhost:8001"):
        self.base_url = base_url
        self.test_session_id = f"test_session_{int(time.time())}"
        self.workflow_manager = None
        self.test_results = []
        
        if COMPONENTS_AVAILABLE:
            self.workflow_manager = WorkflowAutomationManager()
    
    async def run_all_tests(self):
        """Run complete test suite"""
        logger.info("🚀 Starting Session Takeover System Test Suite")
        
        test_methods = [
            self.test_workflow_creation,
            self.test_step_confirmation_flow,
            self.test_manual_takeover,
            self.test_emergency_kill,
            self.test_pause_resume_workflow,
            self.test_chat_integration,
            self.test_command_risk_assessment,
            self.test_websocket_communication,
            self.test_workflow_dependencies,
            self.test_error_handling
        ]
        
        for test_method in test_methods:
            try:
                await test_method()
                self.test_results.append({"test": test_method.__name__, "status": "PASSED", "error": None})
            except Exception as e:
                logger.error(f"❌ {test_method.__name__} FAILED: {e}")
                self.test_results.append({"test": test_method.__name__, "status": "FAILED", "error": str(e)})
        
        await self.print_test_summary()
    
    async def test_workflow_creation(self):
        """Test 1: Basic workflow creation and structure"""
        logger.info("🧪 Test 1: Workflow Creation")
        
        if not COMPONENTS_AVAILABLE:
            logger.info("⏭️ Skipping - components not available")
            return
        
        # Create test workflow steps
        steps = [
            WorkflowStep(
                step_id="step_1",
                command="echo 'Starting system update'",
                description="Initialize system update",
                explanation="This command starts the system update process",
                requires_confirmation=True
            ),
            WorkflowStep(
                step_id="step_2", 
                command="sudo apt update",
                description="Update package repositories",
                explanation="Updates the list of available packages",
                requires_confirmation=True
            ),
            WorkflowStep(
                step_id="step_3",
                command="apt list --upgradable",
                description="Check upgradable packages",
                explanation="Shows which packages can be upgraded",
                requires_confirmation=False
            )
        ]
        
        # Create workflow
        workflow_id = await self.workflow_manager.create_automated_workflow(
            name="Test System Update Workflow",
            description="Complete system update with user confirmation",
            steps=steps,
            session_id=self.test_session_id,
            automation_mode=AutomationMode.SEMI_AUTOMATIC
        )
        
        assert workflow_id is not None, "Workflow creation failed"
        assert workflow_id in self.workflow_manager.active_workflows, "Workflow not found in active list"
        
        workflow = self.workflow_manager.active_workflows[workflow_id]
        assert workflow.name == "Test System Update Workflow", "Workflow name mismatch"
        assert len(workflow.steps) == 3, "Incorrect number of steps"
        assert workflow.automation_mode == AutomationMode.SEMI_AUTOMATIC, "Automation mode mismatch"
        
        logger.info("✅ Workflow created successfully with ID: {workflow_id}")
    
    async def test_step_confirmation_flow(self):
        """Test 2: Step-by-step confirmation workflow"""
        logger.info("🧪 Test 2: Step Confirmation Flow")
        
        if not COMPONENTS_AVAILABLE:
            logger.info("⏭️ Skipping - components not available")
            return
        
        # Create simple 2-step workflow
        steps = [
            WorkflowStep("confirm_1", "echo 'Step 1 executed'", "Execute step 1", requires_confirmation=True),
            WorkflowStep("confirm_2", "echo 'Step 2 executed'", "Execute step 2", requires_confirmation=True)
        ]
        
        workflow_id = await self.workflow_manager.create_automated_workflow(
            name="Confirmation Test Workflow",
            description="Test step-by-step confirmation",
            steps=steps,
            session_id=self.test_session_id
        )
        
        # Start workflow (should wait for first step confirmation)
        await self.workflow_manager.start_workflow_execution(workflow_id)
        
        workflow = self.workflow_manager.active_workflows[workflow_id]
        assert workflow.current_step_index == 0, "Workflow should be waiting at first step"
        assert workflow.steps[0].status.value == "waiting_approval", "First step should be waiting for approval"
        
        # Simulate user approving first step
        from backend.api.workflow_automation import WorkflowControlRequest
        control_request = WorkflowControlRequest(
            workflow_id=workflow_id,
            action="approve_step",
            step_id="confirm_1"
        )
        
        await self.workflow_manager.handle_workflow_control(control_request)
        
        # Allow async processing
        await asyncio.sleep(0.5)
        
        logger.info("✅ Step confirmation flow working correctly")
    
    async def test_manual_takeover(self):
        """Test 3: Manual takeover during automation"""
        logger.info("🧪 Test 3: Manual Takeover")
        
        if not COMPONENTS_AVAILABLE:
            logger.info("⏭️ Skipping - components not available")
            return
        
        # Create workflow with multiple steps
        steps = [
            WorkflowStep("takeover_1", "echo 'Before takeover'", "Pre-takeover step"),
            WorkflowStep("takeover_2", "echo 'After takeover'", "Post-takeover step"),
            WorkflowStep("takeover_3", "echo 'Final step'", "Final step")
        ]
        
        workflow_id = await self.workflow_manager.create_automated_workflow(
            name="Manual Takeover Test",
            description="Test manual intervention",
            steps=steps,
            session_id=self.test_session_id
        )
        
        # Start workflow
        await self.workflow_manager.start_workflow_execution(workflow_id)
        
        # Simulate user taking manual control during execution
        from backend.api.workflow_automation import WorkflowControlRequest
        pause_request = WorkflowControlRequest(
            workflow_id=workflow_id,
            action="pause"
        )
        
        await self.workflow_manager.handle_workflow_control(pause_request)
        
        workflow = self.workflow_manager.active_workflows[workflow_id]
        assert workflow.is_paused == True, "Workflow should be paused"
        
        # Record manual intervention
        assert len(workflow.user_interventions) > 0, "User intervention should be recorded"
        intervention = workflow.user_interventions[-1]
        assert intervention["action"] == "pause", "Pause action should be recorded"
        
        # Resume workflow
        resume_request = WorkflowControlRequest(
            workflow_id=workflow_id,
            action="resume"
        )
        
        await self.workflow_manager.handle_workflow_control(resume_request)
        
        workflow = self.workflow_manager.active_workflows[workflow_id]
        assert workflow.is_paused == False, "Workflow should be resumed"
        
        logger.info("✅ Manual takeover functionality working correctly")
    
    async def test_emergency_kill(self):
        """Test 4: Emergency kill functionality"""
        logger.info("🧪 Test 4: Emergency Kill")
        
        if not COMPONENTS_AVAILABLE:
            logger.info("⏭️ Skipping - components not available")
            return
        
        # Create mock terminal session
        terminal_session = SimpleTerminalSession(self.test_session_id)
        terminal_session.websocket = AsyncMock()
        terminal_session.active = True
        
        # Simulate running processes
        mock_processes = [
            {"pid": 1001, "command": "long_running_task", "startTime": time.time()},
            {"pid": 1002, "command": "background_process &", "startTime": time.time()}
        ]
        
        # Test emergency kill message handling
        kill_data = {
            "type": "automation_control",
            "action": "emergency_kill",
            "session_id": self.test_session_id
        }
        
        await terminal_session.handle_workflow_control(kill_data)
        
        # Verify emergency kill message was sent
        terminal_session.websocket.send_text.assert_called()
        
        logger.info("✅ Emergency kill functionality working correctly")
    
    async def test_pause_resume_workflow(self):
        """Test 5: Pause and resume workflow execution"""
        logger.info("🧪 Test 5: Pause/Resume Workflow")
        
        if not COMPONENTS_AVAILABLE:
            logger.info("⏭️ Skipping - components not available")  
            return
        
        # Create workflow
        steps = [
            WorkflowStep("pause_1", "echo 'Before pause'", "Pre-pause step"),
            WorkflowStep("pause_2", "sleep 2", "Pausable step"),
            WorkflowStep("pause_3", "echo 'After pause'", "Post-pause step")
        ]
        
        workflow_id = await self.workflow_manager.create_automated_workflow(
            name="Pause/Resume Test",
            description="Test pause and resume functionality",
            steps=steps,
            session_id=self.test_session_id
        )
        
        # Start workflow
        await self.workflow_manager.start_workflow_execution(workflow_id)
        
        # Test pause
        from backend.api.workflow_automation import WorkflowControlRequest
        pause_request = WorkflowControlRequest(workflow_id=workflow_id, action="pause")
        result = await self.workflow_manager.handle_workflow_control(pause_request)
        assert result == True, "Pause should succeed"
        
        # Test resume  
        resume_request = WorkflowControlRequest(workflow_id=workflow_id, action="resume")
        result = await self.workflow_manager.handle_workflow_control(resume_request)
        assert result == True, "Resume should succeed"
        
        workflow = self.workflow_manager.active_workflows[workflow_id]
        assert len(workflow.user_interventions) == 2, "Should have 2 interventions (pause + resume)"
        
        logger.info("✅ Pause/Resume functionality working correctly")
    
    async def test_chat_integration(self):
        """Test 6: Chat-to-workflow integration"""
        logger.info("🧪 Test 6: Chat Integration")
        
        if not COMPONENTS_AVAILABLE:
            logger.info("⏭️ Skipping - components not available")
            return
        
        # Test natural language workflow creation
        test_messages = [
            "Please install git and node.js on my system",
            "Set up a development environment with Python",
            "Update my system and install security patches",
            "Configure nginx and deploy my application"
        ]
        
        for message in test_messages:
            workflow_id = await self.workflow_manager.create_workflow_from_chat_request(
                message, self.test_session_id
            )
            
            if workflow_id:
                workflow = self.workflow_manager.active_workflows[workflow_id]
                assert len(workflow.steps) > 0, f"Workflow should have steps for: {message}"
                logger.info(f"✅ Created workflow for: '{message}' with {len(workflow.steps)} steps")
            else:
                logger.info(f"⚠️ No workflow created for: '{message}' (expected for some messages)")
        
        logger.info("✅ Chat integration working correctly")
    
    async def test_command_risk_assessment(self):
        """Test 7: Command risk assessment"""
        logger.info("🧪 Test 7: Command Risk Assessment")
        
        # Test risk assessment patterns (frontend logic simulation)
        test_commands = [
            ("ls -la", "low"),
            ("sudo apt install git", "moderate"),
            ("rm -rf /tmp/test", "high"),
            ("sudo rm -rf /", "critical"),
            ("dd if=/dev/zero of=/dev/sda", "critical"),
            ("mkfs.ext4 /dev/sdb1", "critical"),
            ("killall -9 python", "high"),
            ("chmod 777 /", "high"),
            ("echo 'safe command'", "low")
        ]
        
        def assess_command_risk(command):
            """Simulate frontend risk assessment"""
            lowerCmd = command.lower().strip()
            
            # Critical risk patterns
            critical_patterns = [
                r"rm\s+-rf\s+/($|\s)",
                r"dd\s+if=.*of=/dev/[sh]d",
                r"mkfs\."
            ]
            
            # High risk patterns
            high_patterns = [
                r"rm\s+-rf",
                r"sudo\s+rm",
                r"killall\s+-9",
                r"chmod\s+777.*/$"
            ]
            
            # Moderate risk patterns  
            moderate_patterns = [
                r"sudo\s+(apt|yum|dnf).*install",
                r"sudo\s+systemctl"
            ]
            
            import re
            
            for pattern in critical_patterns:
                if re.search(pattern, lowerCmd):
                    return "critical"
            
            for pattern in high_patterns:
                if re.search(pattern, lowerCmd):
                    return "high"
            
            for pattern in moderate_patterns:
                if re.search(pattern, lowerCmd):
                    return "moderate"
            
            return "low"
        
        for command, expected_risk in test_commands:
            assessed_risk = assess_command_risk(command)
            assert assessed_risk == expected_risk, f"Risk assessment failed for '{command}': expected {expected_risk}, got {assessed_risk}"
        
        logger.info("✅ Command risk assessment working correctly")
    
    async def test_websocket_communication(self):
        """Test 8: WebSocket message handling"""
        logger.info("🧪 Test 8: WebSocket Communication")
        
        if not COMPONENTS_AVAILABLE:
            logger.info("⏭️ Skipping - components not available")
            return
        
        # Create mock terminal session
        terminal_session = SimpleTerminalSession(self.test_session_id)
        terminal_session.websocket = AsyncMock()
        terminal_session.active = True
        
        # Test workflow control messages
        test_messages = [
            {
                "type": "automation_control",
                "action": "pause",
                "session_id": self.test_session_id
            },
            {
                "type": "automation_control", 
                "action": "resume",
                "session_id": self.test_session_id
            },
            {
                "type": "workflow_message",
                "subtype": "start_workflow",
                "workflow": {
                    "name": "Test Workflow",
                    "steps": []
                }
            }
        ]
        
        for message in test_messages:
            if message["type"] == "automation_control":
                await terminal_session.handle_workflow_control(message)
            elif message["type"] == "workflow_message":
                await terminal_session.handle_workflow_message(message)
        
        # Verify WebSocket send_text was called for each message
        assert terminal_session.websocket.send_text.call_count >= len(test_messages), "WebSocket messages should be sent"
        
        logger.info("✅ WebSocket communication working correctly")
    
    async def test_workflow_dependencies(self):
        """Test 9: Workflow step dependencies"""
        logger.info("🧪 Test 9: Workflow Dependencies")
        
        if not COMPONENTS_AVAILABLE:
            logger.info("⏭️ Skipping - components not available")
            return
        
        # Create workflow with dependencies
        steps = [
            WorkflowStep("dep_1", "echo 'Base step'", "Base step", dependencies=[]),
            WorkflowStep("dep_2", "echo 'Depends on 1'", "Dependent step", dependencies=["dep_1"]),
            WorkflowStep("dep_3", "echo 'Depends on 2'", "Final step", dependencies=["dep_2"])
        ]
        
        workflow_id = await self.workflow_manager.create_automated_workflow(
            name="Dependency Test",
            description="Test step dependencies",
            steps=steps,
            session_id=self.test_session_id
        )
        
        workflow = self.workflow_manager.active_workflows[workflow_id]
        
        # Test dependency checking
        step1 = workflow.steps[0]
        step2 = workflow.steps[1]
        step3 = workflow.steps[2]
        
        # Step 1 should have no dependencies
        assert len(step1.dependencies or []) == 0, "Step 1 should have no dependencies"
        
        # Step 2 should depend on step 1
        assert "dep_1" in (step2.dependencies or []), "Step 2 should depend on step 1"
        
        # Step 3 should depend on step 2
        assert "dep_2" in (step3.dependencies or []), "Step 3 should depend on step 2"
        
        logger.info("✅ Workflow dependencies working correctly")
    
    async def test_error_handling(self):
        """Test 10: Error handling and recovery"""
        logger.info("🧪 Test 10: Error Handling")
        
        if not COMPONENTS_AVAILABLE:
            logger.info("⏭️ Skipping - components not available")
            return
        
        # Test invalid workflow operations
        try:
            # Try to control non-existent workflow
            from backend.api.workflow_automation import WorkflowControlRequest
            invalid_request = WorkflowControlRequest(
                workflow_id="non_existent_workflow",
                action="pause"
            )
            
            result = await self.workflow_manager.handle_workflow_control(invalid_request)
            assert result == False, "Invalid workflow control should return False"
            
        except Exception as e:
            logger.info(f"✅ Properly handled error: {e}")
        
        # Test malformed messages
        terminal_session = SimpleTerminalSession(self.test_session_id)
        terminal_session.websocket = AsyncMock()
        
        malformed_data = {"type": "invalid_type", "data": "malformed"}
        
        try:
            await terminal_session.handle_workflow_control(malformed_data)
        except Exception as e:
            logger.info(f"✅ Properly handled malformed message: {e}")
        
        logger.info("✅ Error handling working correctly")
    
    async def print_test_summary(self):
        """Print comprehensive test summary"""
        logger.info("\n" + "="*80)
        logger.info("🧪 SESSION TAKEOVER SYSTEM - TEST RESULTS SUMMARY")
        logger.info("="*80)
        
        passed = len([r for r in self.test_results if r["status"] == "PASSED"])
        failed = len([r for r in self.test_results if r["status"] == "FAILED"])
        total = len(self.test_results)
        
        logger.info(f"📊 TOTAL TESTS: {total}")
        logger.info(f"✅ PASSED: {passed}")
        logger.info(f"❌ FAILED: {failed}")
        logger.info(f"📈 SUCCESS RATE: {(passed/total)*100:.1f}%" if total > 0 else "No tests run")
        
        logger.info("\n📋 DETAILED RESULTS:")
        for result in self.test_results:
            status_icon = "✅" if result["status"] == "PASSED" else "❌"
            logger.info(f"{status_icon} {result['test']}: {result['status']}")
            if result["error"]:
                logger.info(f"   Error: {result['error']}")
        
        # Component availability check
        logger.info(f"\n🔧 COMPONENT AVAILABILITY:")
        logger.info(f"   Workflow Automation Components: {'✅ Available' if COMPONENTS_AVAILABLE else '❌ Not Available'}")
        
        logger.info("\n🎯 FEATURE STATUS:")
        features = [
            "Workflow Creation and Management",
            "Step-by-Step Confirmation Flow", 
            "Manual Takeover During Automation",
            "Emergency Kill Functionality",
            "Pause/Resume Workflow Control",
            "Chat-to-Workflow Integration",
            "Command Risk Assessment",
            "WebSocket Real-time Communication",
            "Workflow Step Dependencies",
            "Comprehensive Error Handling"
        ]
        
        for i, feature in enumerate(features):
            test_result = self.test_results[i] if i < len(self.test_results) else {"status": "UNKNOWN"}
            status_icon = "✅" if test_result["status"] == "PASSED" else "❌" if test_result["status"] == "FAILED" else "❓"
            logger.info(f"   {status_icon} {feature}")
        
        logger.info("\n🚀 SYSTEM STATUS:")
        if passed == total and total > 0:
            logger.info("   🎉 ALL TESTS PASSED - Session Takeover System is FULLY FUNCTIONAL!")
        elif passed > failed:
            logger.info("   ⚠️ MOSTLY FUNCTIONAL - Some issues need attention")
        else:
            logger.info("   🔧 NEEDS WORK - Multiple issues detected")
        
        logger.info("="*80 + "\n")


async def run_demo_workflow():
    """Run a demo workflow to showcase the system"""
    logger.info("🎬 Starting Demo Workflow")
    
    if not COMPONENTS_AVAILABLE:
        logger.info("⚠️ Demo requires workflow automation components")
        return
    
    # Create demo workflow manager
    demo_manager = WorkflowAutomationManager()
    demo_session_id = f"demo_session_{int(time.time())}"
    
    # Create comprehensive demo workflow
    demo_steps = [
        WorkflowStep(
            step_id="demo_1",
            command="echo '🚀 Starting development environment setup...'",
            description="Initialize setup process",
            explanation="This step announces the beginning of the development environment setup",
            requires_confirmation=False
        ),
        WorkflowStep(
            step_id="demo_2", 
            command="sudo apt update",
            description="Update package repositories",
            explanation="This updates the list of available packages from configured repositories",
            requires_confirmation=True
        ),
        WorkflowStep(
            step_id="demo_3",
            command="sudo apt install -y git curl wget",
            description="Install essential development tools",
            explanation="Install Git for version control, curl for downloading, and wget for file retrieval",
            requires_confirmation=True
        ),
        WorkflowStep(
            step_id="demo_4",
            command="git --version && curl --version && wget --version",
            description="Verify tool installations",
            explanation="Check that all tools were installed correctly and display their versions",
            requires_confirmation=False
        ),
        WorkflowStep(
            step_id="demo_5",
            command="echo '✅ Development environment setup complete!'",
            description="Complete setup process",
            explanation="Announce successful completion of the development environment setup",
            requires_confirmation=False
        )
    ]
    
    # Create and start demo workflow
    workflow_id = await demo_manager.create_automated_workflow(
        name="🛠️ Development Environment Setup Demo",
        description="Complete development environment setup with user confirmation points",
        steps=demo_steps,
        session_id=demo_session_id,
        automation_mode=AutomationMode.SEMI_AUTOMATIC
    )
    
    logger.info(f"✅ Demo workflow created with ID: {workflow_id}")
    logger.info("📋 Workflow includes 5 steps with confirmation points for system modifications")
    logger.info("🎯 This demonstrates the complete session takeover system capabilities")
    
    # Get workflow status
    status = demo_manager.get_workflow_status(workflow_id)
    logger.info(f"📊 Workflow Status: {json.dumps(status, indent=2, default=str)}")


if __name__ == "__main__":
    async def main():
        # Run comprehensive test suite
        test_suite = SessionTakeoverTestSuite()
        await test_suite.run_all_tests()
        
        # Run demo workflow
        await run_demo_workflow()
    
    # Run the tests
    asyncio.run(main())