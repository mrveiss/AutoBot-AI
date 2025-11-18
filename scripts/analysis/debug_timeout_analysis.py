#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Debug script to identify and fix blocking operations causing timeout workarounds
"""
import asyncio
import time
import logging
import traceback
import aiohttp
import json
from typing import Dict, Any

# Configure logging to see what's happening
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TimeoutAnalyzer:
    """Analyze and test various components for blocking operations"""
    
    def __init__(self):
        self.results = {}
        self.backend_url = ServiceURLs.BACKEND_LOCAL
        
    async def test_backend_health(self) -> Dict[str, Any]:
        """Test if backend is responsive"""
        try:
            start_time = time.time()
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.backend_url}/api/health", timeout=5) as response:
                    duration = time.time() - start_time
                    status = response.status
                    data = await response.json()
                    return {
                        "success": True,
                        "duration": duration,
                        "status": status,
                        "data": data
                    }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "duration": time.time() - start_time
            }
    
    async def test_chat_endpoint_simple(self) -> Dict[str, Any]:
        """Test a simple chat message"""
        try:
            start_time = time.time()
            
            payload = {
                "message": "Hello, what time is it?",
                "chat_id": "test-timeout-analysis"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.backend_url}/api/chats/test-timeout-analysis/message", 
                    json=payload,
                    timeout=30  # Generous timeout to see if it completes
                ) as response:
                    duration = time.time() - start_time
                    status = response.status
                    data = await response.json() if response.status == 200 else await response.text()
                    return {
                        "success": response.status == 200,
                        "duration": duration,
                        "status": status,
                        "response_length": len(str(data)) if data else 0,
                        "data_preview": str(data)[:200] + "..." if len(str(data)) > 200 else str(data)
                    }
        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": "Chat endpoint timed out after 30 seconds",
                "duration": time.time() - start_time,
                "blocking_detected": True
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "duration": time.time() - start_time,
                "traceback": traceback.format_exc()
            }
    
    async def test_knowledge_base_direct(self) -> Dict[str, Any]:
        """Test knowledge base operations directly"""
        try:
            start_time = time.time()
            
            # Test importing knowledge base
            from src.knowledge_base import KnowledgeBase
            
            # Test creating KB instance (was this blocking?)
            kb_create_start = time.time()
            kb = await asyncio.to_thread(lambda: KnowledgeBase())
            kb_create_time = time.time() - kb_create_start
            
            # Test initializing KB (was this blocking?)
            init_start = time.time()
            try:
                await asyncio.wait_for(kb.ainit(), timeout=5.0)
                init_success = True
                init_error = None
            except asyncio.TimeoutError:
                init_success = False  
                init_error = "KB initialization timed out after 5 seconds"
            except Exception as e:
                init_success = False
                init_error = str(e)
            init_time = time.time() - init_start
            
            # Test basic search (was this blocking?)
            search_start = time.time()
            search_success = False
            search_error = None
            search_results = []
            
            if init_success:
                try:
                    search_results = await asyncio.wait_for(
                        kb.search("test query", limit=1),
                        timeout=3.0
                    )
                    search_success = True
                except asyncio.TimeoutError:
                    search_error = "KB search timed out after 3 seconds"
                except Exception as e:
                    search_error = str(e)
            else:
                search_error = "Skipped due to init failure"
                
            search_time = time.time() - search_start
            total_time = time.time() - start_time
            
            return {
                "success": init_success and search_success,
                "total_duration": total_time,
                "kb_create_time": kb_create_time,
                "init_success": init_success,
                "init_time": init_time,
                "init_error": init_error,
                "search_success": search_success,
                "search_time": search_time,
                "search_error": search_error,
                "search_results_count": len(search_results) if search_results else 0
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "duration": time.time() - start_time,
                "traceback": traceback.format_exc()
            }
    
    async def test_llm_interface_direct(self) -> Dict[str, Any]:
        """Test LLM interface operations directly"""
        try:
            start_time = time.time()
            
            # Test importing LLM interface
            from src.llm_interface import LLMInterface
            
            # Test creating LLM instance
            llm_create_start = time.time()
            llm = LLMInterface()
            llm_create_time = time.time() - llm_create_start
            
            # Test simple chat completion (was this hanging in infinite loops?)
            chat_start = time.time()
            messages = [{"role": "user", "content": "Say 'hello' and nothing else"}]
            
            try:
                response = await asyncio.wait_for(
                    llm.chat_completion(messages, llm_type="general"),
                    timeout=10.0
                )
                chat_success = True
                chat_error = None
                response_length = len(str(response)) if response else 0
            except asyncio.TimeoutError:
                chat_success = False
                chat_error = "LLM chat completion timed out after 10 seconds"
                response_length = 0
            except Exception as e:
                chat_success = False
                chat_error = str(e)
                response_length = 0
                
            chat_time = time.time() - chat_start
            total_time = time.time() - start_time
            
            return {
                "success": chat_success,
                "total_duration": total_time,
                "llm_create_time": llm_create_time,
                "chat_success": chat_success,
                "chat_time": chat_time,
                "chat_error": chat_error,
                "response_length": response_length
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "duration": time.time() - start_time,
                "traceback": traceback.format_exc()
            }
    
    async def test_simple_workflow_direct(self) -> Dict[str, Any]:
        """Test the SimpleChatWorkflow directly"""
        try:
            start_time = time.time()
            
            from src.simple_chat_workflow import SimpleChatWorkflow
            from src.constants import NetworkConstants, ServiceURLs
            
            # Create workflow instance
            workflow_create_start = time.time()
            workflow = SimpleChatWorkflow()
            workflow_create_time = time.time() - workflow_create_start
            
            # Test processing a message (this uses the timeout workarounds)
            process_start = time.time()
            try:
                result = await asyncio.wait_for(
                    workflow.process_message("Hello, what time is it?", "test-chat"),
                    timeout=25.0  # Slightly longer than internal 20s timeout
                )
                process_success = True
                process_error = None
                response_length = len(result.response) if result and result.response else 0
            except asyncio.TimeoutError:
                process_success = False
                process_error = "SimpleChatWorkflow timed out after 25 seconds"
                response_length = 0
            except Exception as e:
                process_success = False
                process_error = str(e)
                response_length = 0
                
            process_time = time.time() - process_start
            total_time = time.time() - start_time
            
            return {
                "success": process_success,
                "total_duration": total_time,
                "workflow_create_time": workflow_create_time,
                "process_success": process_success,
                "process_time": process_time,
                "process_error": process_error,
                "response_length": response_length
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "duration": time.time() - start_time,
                "traceback": traceback.format_exc()
            }
    
    async def run_analysis(self):
        """Run all timeout analysis tests"""
        logger.info("Starting timeout analysis...")
        
        # Test 1: Backend health
        logger.info("Testing backend health...")
        self.results["backend_health"] = await self.test_backend_health()
        
        # Test 2: Knowledge base operations
        logger.info("Testing knowledge base operations...")
        self.results["knowledge_base"] = await self.test_knowledge_base_direct()
        
        # Test 3: LLM interface operations  
        logger.info("Testing LLM interface operations...")
        self.results["llm_interface"] = await self.test_llm_interface_direct()
        
        # Test 4: Simple workflow operations
        logger.info("Testing SimpleChatWorkflow...")
        self.results["simple_workflow"] = await self.test_simple_workflow_direct()
        
        # Test 5: Chat endpoint
        logger.info("Testing chat endpoint...")
        self.results["chat_endpoint"] = await self.test_chat_endpoint_simple()
        
        logger.info("Analysis complete!")
    
    def print_results(self):
        """Print comprehensive analysis results"""
        print("\n" + "="*80)
        print("TIMEOUT ANALYSIS RESULTS")
        print("="*80)
        
        for test_name, result in self.results.items():
            print(f"\n{test_name.upper().replace('_', ' ')}:")
            print("-" * 40)
            
            if result.get("success"):
                print(f"✅ SUCCESS - Duration: {result.get('duration', 0):.2f}s")
            else:
                print(f"❌ FAILED - Duration: {result.get('duration', 0):.2f}s")
                if result.get("error"):
                    print(f"   Error: {result['error']}")
                if result.get("blocking_detected"):
                    print(f"   ⚠️  BLOCKING OPERATION DETECTED")
            
            # Print detailed timing information
            for key, value in result.items():
                if key.endswith("_time") and isinstance(value, (int, float)):
                    print(f"   {key.replace('_', ' ').title()}: {value:.3f}s")
                elif key.endswith("_success") and isinstance(value, bool):
                    status = "✅" if value else "❌"
                    print(f"   {key.replace('_', ' ').title()}: {status}")
        
        print(f"\n{'='*80}")
        print("BLOCKING OPERATIONS SUMMARY")
        print("="*80)
        
        blocking_operations = []
        for test_name, result in self.results.items():
            if not result.get("success") or result.get("duration", 0) > 5.0:
                blocking_operations.append({
                    "test": test_name,
                    "duration": result.get("duration", 0),
                    "error": result.get("error", "Slow operation"),
                    "blocking": result.get("blocking_detected", False)
                })
        
        if blocking_operations:
            print("Found potential blocking operations:")
            for op in blocking_operations:
                print(f"  - {op['test']}: {op['duration']:.2f}s - {op['error']}")
        else:
            print("No obvious blocking operations detected.")

async def main():
    analyzer = TimeoutAnalyzer()
    await analyzer.run_analysis()
    analyzer.print_results()

if __name__ == "__main__":
    asyncio.run(main())