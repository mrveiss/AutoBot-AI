"""
RAG Agent - Specialized for Retrieval-Augmented Generation tasks.

Uses Llama 3.2 3B model for complex document synthesis, query reformulation,
and context ranking. Handles knowledge base integration and document analysis.
"""

import logging
import json
from typing import Dict, Any, List, Optional, Tuple
from src.llm_interface import LLMInterface
from src.config import config as global_config_manager

logger = logging.getLogger(__name__)


class RAGAgent:
    """RAG agent for document synthesis and knowledge integration."""

    def __init__(self):
        """Initialize the RAG Agent with 3B model for complex reasoning."""
        self.llm_interface = LLMInterface()
        self.model_name = global_config_manager.get_task_specific_model("rag")
        self.agent_type = "rag"
        
        logger.info(f"RAG Agent initialized with model: {self.model_name}")

    async def process_document_query(
        self, 
        query: str,
        documents: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Process a query against retrieved documents and synthesize response.
        
        Args:
            query: User's question or request
            documents: List of retrieved documents with content and metadata
            context: Optional additional context
            
        Returns:
            Dict containing synthesized response and analysis
        """
        try:
            logger.info(f"RAG Agent processing query with {len(documents)} documents")
            
            # Prepare RAG-focused system prompt
            system_prompt = self._get_rag_system_prompt()
            
            # Build document context
            document_context = self._build_document_context(documents)
            
            # Create messages with context
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "system", "content": f"Retrieved Documents:\n{document_context}"},
                {"role": "user", "content": query}
            ]
            
            # Generate synthesis with higher complexity settings
            response = await self.llm_interface.chat_completion(
                messages=messages,
                llm_type="rag",  # Uses RAG-specific model
                temperature=0.5,  # Balanced creativity for synthesis
                max_tokens=1024,  # Allow longer responses for synthesis
                top_p=0.9
            )
            
            # Extract and structure response
            synthesis_result = self._extract_synthesis_response(response)
            
            # Add document analysis
            document_analysis = self._analyze_document_relevance(query, documents)
            
            return {
                "status": "success",
                "synthesized_response": synthesis_result.get("response", ""),
                "confidence_score": synthesis_result.get("confidence", 0.8),
                "document_analysis": document_analysis,
                "sources_used": [doc.get("metadata", {}).get("filename", "Unknown") 
                               for doc in documents],
                "agent_type": "rag",
                "model_used": self.model_name,
                "metadata": {
                    "agent": "RAGAgent",
                    "documents_processed": len(documents),
                    "synthesis_complexity": "high"
                }
            }
            
        except Exception as e:
            logger.error(f"RAG Agent error: {e}")
            return {
                "status": "error",
                "synthesized_response": "I encountered an error while synthesizing information from the documents.",
                "error": str(e),
                "agent_type": "rag",
                "model_used": self.model_name
            }

    async def reformulate_query(
        self, 
        original_query: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Reformulate a query to improve retrieval effectiveness.
        
        Args:
            original_query: The user's original query
            context: Optional context for reformulation
            
        Returns:
            Dict containing reformulated queries and analysis
        """
        try:
            logger.info(f"RAG Agent reformulating query: {original_query[:50]}...")
            
            system_prompt = self._get_query_reformulation_prompt()
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Original query: {original_query}"}
            ]
            
            response = await self.llm_interface.chat_completion(
                messages=messages,
                llm_type="rag",
                temperature=0.6,
                max_tokens=512,
                top_p=0.85
            )
            
            reformulation_result = self._extract_reformulation_response(response)
            
            return {
                "status": "success",
                "original_query": original_query,
                **reformulation_result,
                "agent_type": "rag",
                "model_used": self.model_name
            }
            
        except Exception as e:
            logger.error(f"Query reformulation error: {e}")
            return {
                "status": "error",
                "original_query": original_query,
                "reformulated_queries": [original_query],
                "error": str(e)
            }

    async def rank_documents(
        self,
        query: str,
        documents: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Rank documents by relevance to the query.
        
        Args:
            query: The search query
            documents: List of documents to rank
            
        Returns:
            List of documents with relevance scores
        """
        try:
            logger.info(f"RAG Agent ranking {len(documents)} documents")
            
            # For now, use simple scoring - can be enhanced with more sophisticated ranking
            scored_documents = []
            
            for i, doc in enumerate(documents):
                content = doc.get("content", "").lower()
                query_lower = query.lower()
                
                # Simple relevance scoring
                score = 0.0
                query_words = query_lower.split()
                
                for word in query_words:
                    if word in content:
                        score += 1.0
                
                # Normalize by query length
                if len(query_words) > 0:
                    score = score / len(query_words)
                
                # Add document metadata
                scored_doc = doc.copy()
                scored_doc["relevance_score"] = score
                scored_doc["rank"] = i + 1
                scored_documents.append(scored_doc)
            
            # Sort by relevance score
            scored_documents.sort(key=lambda x: x["relevance_score"], reverse=True)
            
            # Update ranks after sorting
            for i, doc in enumerate(scored_documents):
                doc["rank"] = i + 1
            
            return scored_documents
            
        except Exception as e:
            logger.error(f"Document ranking error: {e}")
            return documents  # Return original list on error

    def _get_rag_system_prompt(self) -> str:
        """Get system prompt for RAG synthesis tasks."""
        return """You are a document synthesis specialist focused on creating comprehensive, accurate responses.

Your task is to analyze retrieved documents and synthesize a coherent response that:

1. ACCURACY: Base your response strictly on the provided documents
2. SYNTHESIS: Combine information from multiple sources when relevant
3. ATTRIBUTION: Clearly indicate which documents support your statements
4. COMPLETENESS: Address all aspects of the user's question
5. CLARITY: Present information in a clear, organized manner

RESPONSE FORMAT:
Structure your response as follows:
- Direct answer to the user's question
- Supporting details from the documents
- If conflicting information exists, acknowledge it
- If documents don't fully answer the question, state what's missing

CITATION STYLE:
When referencing documents, use: [Document: filename or source]

QUALITY STANDARDS:
- Never fabricate information not in the documents
- If documents are insufficient, say so clearly
- Prioritize more recent or authoritative sources
- Maintain objectivity and avoid bias"""

    def _get_query_reformulation_prompt(self) -> str:
        """Get system prompt for query reformulation."""
        return """You are a query reformulation expert. Your task is to take user queries and create multiple improved versions for better document retrieval.

Generate reformulated queries that:
1. Use different terminology while maintaining meaning
2. Break complex queries into focused sub-questions
3. Add relevant context or domain-specific terms
4. Consider alternative phrasings

Respond in JSON format:
{
    "reformulated_queries": ["query1", "query2", "query3"],
    "key_concepts": ["concept1", "concept2"],
    "search_strategy": "explanation of approach"
}

Focus on creating 2-4 reformulated queries that would retrieve different but relevant documents."""

    def _build_document_context(self, documents: List[Dict[str, Any]]) -> str:
        """Build formatted context from retrieved documents."""
        context_parts = []
        
        for i, doc in enumerate(documents):
            filename = doc.get("metadata", {}).get("filename", f"Document_{i+1}")
            content = doc.get("content", "")
            
            # Truncate very long documents
            if len(content) > 1000:
                content = content[:1000] + "... [truncated]"
            
            context_parts.append(f"[Document: {filename}]\n{content}\n")
        
        return "\n".join(context_parts)

    def _analyze_document_relevance(
        self, 
        query: str, 
        documents: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Analyze relevance of documents to the query."""
        analysis = {
            "total_documents": len(documents),
            "high_relevance": 0,
            "medium_relevance": 0,
            "low_relevance": 0,
            "document_details": []
        }
        
        query_words = set(query.lower().split())
        
        for doc in documents:
            content = doc.get("content", "").lower()
            filename = doc.get("metadata", {}).get("filename", "Unknown")
            
            # Count matching words
            content_words = set(content.split())
            matches = len(query_words.intersection(content_words))
            relevance_ratio = matches / len(query_words) if query_words else 0
            
            if relevance_ratio > 0.7:
                relevance = "high"
                analysis["high_relevance"] += 1
            elif relevance_ratio > 0.3:
                relevance = "medium"
                analysis["medium_relevance"] += 1
            else:
                relevance = "low"
                analysis["low_relevance"] += 1
            
            analysis["document_details"].append({
                "filename": filename,
                "relevance": relevance,
                "match_ratio": relevance_ratio,
                "content_length": len(doc.get("content", ""))
            })
        
        return analysis

    def _extract_synthesis_response(self, response: Any) -> Dict[str, Any]:
        """Extract synthesis response from LLM output."""
        try:
            content = self._extract_response_content(response)
            
            # For now, return the content as-is with default confidence
            # Could be enhanced to parse structured responses
            return {
                "response": content,
                "confidence": 0.8,  # Default confidence
                "structured": False
            }
            
        except Exception as e:
            logger.error(f"Error extracting synthesis response: {e}")
            return {
                "response": "Error in response extraction",
                "confidence": 0.0,
                "structured": False
            }

    def _extract_reformulation_response(self, response: Any) -> Dict[str, Any]:
        """Extract query reformulation from LLM output."""
        try:
            content = self._extract_response_content(response)
            
            # Try to parse JSON response
            try:
                parsed = json.loads(content)
                return {
                    "reformulated_queries": parsed.get("reformulated_queries", []),
                    "key_concepts": parsed.get("key_concepts", []),
                    "search_strategy": parsed.get("search_strategy", "")
                }
            except json.JSONDecodeError:
                # Fallback: extract queries from text
                return {
                    "reformulated_queries": [content],
                    "key_concepts": [],
                    "search_strategy": "Text-based extraction"
                }
                
        except Exception as e:
            logger.error(f"Error extracting reformulation response: {e}")
            return {
                "reformulated_queries": [],
                "key_concepts": [],
                "search_strategy": "Error in extraction"
            }

    def _extract_response_content(self, response: Any) -> str:
        """Extract text content from LLM response."""
        try:
            if isinstance(response, dict):
                if "message" in response and isinstance(response["message"], dict):
                    content = response["message"].get("content")
                    if content:
                        return content.strip()
                
                if "choices" in response and isinstance(response["choices"], list):
                    if len(response["choices"]) > 0:
                        choice = response["choices"][0]
                        if "message" in choice and "content" in choice["message"]:
                            return choice["message"]["content"].strip()
                
                if "content" in response:
                    return response["content"].strip()
            
            if isinstance(response, str):
                return response.strip()
            
            return str(response)
            
        except Exception as e:
            logger.error(f"Error extracting response content: {e}")
            return "Error extracting response content"

    def is_rag_appropriate(self, message: str, has_documents: bool = False) -> bool:
        """
        Determine if a message requires RAG processing.
        
        Args:
            message: The user's message
            has_documents: Whether documents were retrieved
            
        Returns:
            bool: True if RAG agent should handle synthesis
        """
        rag_patterns = [
            "based on", "according to", "summarize", "synthesis", "analyze documents",
            "what do the documents say", "find information about", "research",
            "comprehensive answer", "detailed analysis"
        ]
        
        message_lower = message.lower()
        
        # Strong indicator: documents are available
        if has_documents:
            return True
        
        # Check for RAG-appropriate language patterns
        return any(pattern in message_lower for pattern in rag_patterns)


# Singleton instance
_rag_agent_instance = None


def get_rag_agent() -> RAGAgent:
    """Get the singleton RAG Agent instance."""
    global _rag_agent_instance
    if _rag_agent_instance is None:
        _rag_agent_instance = RAGAgent()
    return _rag_agent_instance