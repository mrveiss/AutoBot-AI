"""
Mock LLM Interface for testing atomic facts extraction without real LLM calls.

DEPRECATED: This file is deprecated in favor of the unified MockProvider in 
src/llm_interface_unified.py. Use the unified interface for new code.
"""

import json
import asyncio
from typing import List, Dict, Any
import re

# Import unified interface for migration
from src.llm_interface_unified import get_unified_llm_interface, ProviderType
from src.utils.config_manager import config_manager


class MockLLMInterface:
    """
    Mock LLM interface that generates realistic fact extraction responses.
    
    DEPRECATED: Use the unified interface with mock provider instead:
    
    # Old usage:
    mock_llm = MockLLMInterface()
    
    # New usage:
    config_manager.set("llm.mock.enabled", True)
    llm = get_unified_llm_interface()
    """
    
    def __init__(self):
        self.response_templates = {
            "autobot": {
                "subject": "AutoBot",
                "predicate": "is",
                "object": "an intelligent automation platform",
                "fact_type": "FACT",
                "temporal_type": "STATIC", 
                "confidence": 0.9
            },
            "python": {
                "subject": "AutoBot", 
                "predicate": "uses",
                "object": "Python programming language",
                "fact_type": "FACT",
                "temporal_type": "STATIC",
                "confidence": 0.85
            },
            "redis": {
                "subject": "AutoBot",
                "predicate": "uses",
                "object": "Redis for caching",
                "fact_type": "FACT",
                "temporal_type": "STATIC",
                "confidence": 0.8
            },
            "version": {
                "subject": "AutoBot", 
                "predicate": "will be updated to",
                "object": "version 2.0",
                "fact_type": "PREDICTION",
                "temporal_type": "DYNAMIC",
                "confidence": 0.7
            },
            "opinion": {
                "subject": "I",
                "predicate": "think",
                "object": "AutoBot is the best platform",
                "fact_type": "OPINION", 
                "temporal_type": "ATEMPORAL",
                "confidence": 0.6
            }
        }
    
    def _extract_facts_from_content(self, content: str) -> List[Dict[str, Any]]:
        """Extract facts based on content analysis."""
        facts = []
        content_lower = content.lower()
        
        # Simple pattern matching for different types of facts
        if "autobot" in content_lower:
            if "automation platform" in content_lower or "intelligent" in content_lower:
                facts.append({
                    **self.response_templates["autobot"],
                    "entities": ["AutoBot", "automation platform"],
                    "context": "Definition of AutoBot",
                    "reasoning": "Clear definitional statement"
                })
        
        if "python" in content_lower:
            facts.append({
                **self.response_templates["python"],
                "entities": ["AutoBot", "Python"],
                "context": "Technology stack",
                "reasoning": "Programming language specification"
            })
        
        if "redis" in content_lower:
            facts.append({
                **self.response_templates["redis"],
                "entities": ["AutoBot", "Redis"],
                "context": "Caching system",
                "reasoning": "Infrastructure component"
            })
        
        if "version 2.0" in content_lower or "will be updated" in content_lower:
            facts.append({
                **self.response_templates["version"],
                "entities": ["AutoBot", "version 2.0"],
                "context": "Future development",
                "reasoning": "Planned update"
            })
        
        if "think" in content_lower or "opinion" in content_lower or "believe" in content_lower:
            facts.append({
                **self.response_templates["opinion"],
                "entities": ["AutoBot"],
                "context": "User opinion",
                "reasoning": "Subjective statement"
            })
        
        # Add some additional facts based on content patterns
        if "chromadb" in content_lower:
            facts.append({
                "subject": "AutoBot",
                "predicate": "uses",
                "object": "ChromaDB for vector storage",
                "fact_type": "FACT",
                "temporal_type": "STATIC",
                "confidence": 0.85,
                "entities": ["AutoBot", "ChromaDB"],
                "context": "Vector database",
                "reasoning": "Storage system specification"
            })
        
        if "created" in content_lower and "1991" in content_lower:
            facts.append({
                "subject": "Python",
                "predicate": "was created in",
                "object": "1991",
                "fact_type": "FACT",
                "temporal_type": "TEMPORAL_BOUND",
                "confidence": 0.95,
                "entities": ["Python", "1991"],
                "context": "Historical fact",
                "reasoning": "Well-established historical information"
            })
        
        if "most popular" in content_lower:
            facts.append({
                "subject": "Python",
                "predicate": "is",
                "object": "most popular programming language for data science",
                "fact_type": "FACT", 
                "temporal_type": "DYNAMIC",
                "confidence": 0.8,
                "entities": ["Python", "data science"],
                "context": "Current popularity",
                "reasoning": "Current market status"
            })
        
        if "will release" in content_lower or "2024" in content_lower:
            facts.append({
                "subject": "OpenAI",
                "predicate": "will release",
                "object": "GPT-5 in 2024",
                "fact_type": "PREDICTION",
                "temporal_type": "TEMPORAL_BOUND",
                "confidence": 0.6,
                "entities": ["OpenAI", "GPT-5"],
                "context": "Future release",
                "reasoning": "Predicted future event"
            })
        
        # Ensure we have at least one fact
        if not facts and content.strip():
            facts.append({
                "subject": "Content",
                "predicate": "contains",
                "object": "information",
                "fact_type": "FACT",
                "temporal_type": "STATIC",
                "confidence": 0.5,
                "entities": ["Content"],
                "context": "Generic content analysis",
                "reasoning": "Fallback fact for any content"
            })
        
        return facts[:10]  # Limit to 10 facts max
    
    async def chat_completion(self, 
                            messages: List[Dict[str, str]], 
                            llm_type: str = "task",
                            structured_output: bool = False,
                            **kwargs) -> Dict[str, Any]:
        """Mock chat completion that generates realistic fact extraction responses."""
        
        # Simulate processing delay
        await asyncio.sleep(0.1)
        
        # Extract content from messages
        user_message = ""
        for message in messages:
            if message.get("role") == "user":
                user_message = message.get("content", "")
                break
        
        # Extract the actual text content from the prompt
        content_match = re.search(r"Text to analyze:\s*(.*?)(?:\n\nContext:|$)", user_message, re.DOTALL)
        if content_match:
            content = content_match.group(1).strip()
        else:
            content = user_message
        
        # Generate facts based on content
        facts = self._extract_facts_from_content(content)
        
        # Format as expected JSON response
        response_data = {"facts": facts}
        response_json = json.dumps(response_data, indent=2)
        
        return {
            "choices": [
                {
                    "message": {
                        "content": response_json
                    }
                }
            ]
        }