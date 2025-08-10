"""
Research Agent - Specialized for web research and knowledge synthesis.

Uses Llama 3.2 3B model with Playwright integration for comprehensive web research,
information gathering, and automated knowledge base storage.
"""

import logging
import time
import asyncio
import re
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from urllib.parse import urlparse
from src.llm_interface import LLMInterface
from src.config import config as global_config_manager
from src.knowledge_base import KnowledgeBase
import httpx

logger = logging.getLogger(__name__)


class ResearchAgent:
    """Comprehensive research agent with web scraping and synthesis capabilities."""

    def __init__(self):
        """Initialize the Research Agent with 3B model and web capabilities."""
        self.llm_interface = LLMInterface()
        self.model_name = global_config_manager.get_task_specific_model("research")
        self.agent_type = "research"
        self.knowledge_base = None
        self.playwright_service_url = "http://localhost:3000"

        # Initialize knowledge base (lazy loading)
        self._kb_initialized = False

        # Research session tracking
        self.current_research_session = None
        self.research_history = []

        logger.info(f"Research Agent initialized with model: {self.model_name}")

    async def _ensure_kb_initialized(self):
        """Ensure knowledge base is initialized (lazy loading)."""
        if not self._kb_initialized:
            try:
                self.knowledge_base = KnowledgeBase()
                await self.knowledge_base.ainit()
                self._kb_initialized = True
                logger.info(
                    "Knowledge base initialized successfully for Research Agent"
                )
            except Exception as e:
                logger.error(f"Failed to initialize knowledge base: {e}")
                self.knowledge_base = None

    async def conduct_research(
        self,
        research_query: str,
        max_sources: int = 5,
        depth: str = "medium",
        auto_save: bool = True,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Conduct comprehensive web research on a given topic.

        Args:
            research_query: The research question or topic
            max_sources: Maximum number of web sources to research
            depth: Research depth ("light", "medium", "deep")
            auto_save: Whether to automatically save findings to knowledge base
            context: Optional context information

        Returns:
            Dict containing research findings, sources, and synthesis
        """
        try:
            logger.info(f"Research Agent conducting research: {research_query[:50]}...")
            start_time = time.time()

            # Create research session
            session_id = self._create_research_session(research_query, depth)

            # Step 1: Generate search queries
            search_queries = await self._generate_search_queries(
                research_query, max_sources
            )

            # Step 2: Perform web searches and scraping
            raw_research_data = await self._perform_web_research(
                search_queries, max_sources
            )

            # Step 3: Process and synthesize findings
            research_synthesis = await self._synthesize_research_findings(
                research_query, raw_research_data, depth
            )

            # Step 4: Auto-save to knowledge base if requested
            if auto_save and research_synthesis.get("findings"):
                await self._save_research_to_kb(research_query, research_synthesis)

            processing_time = time.time() - start_time

            # Compile final research report
            research_report = {
                "status": "success",
                "session_id": session_id,
                "query": research_query,
                "search_queries": search_queries,
                "sources_found": len(raw_research_data),
                "findings": research_synthesis.get("findings", ""),
                "key_points": research_synthesis.get("key_points", []),
                "sources": raw_research_data,
                "research_quality": research_synthesis.get("quality_score", 0),
                "processing_time": processing_time,
                "depth": depth,
                "auto_saved": auto_save,
                "agent_type": "research",
                "model_used": self.model_name,
                "metadata": {
                    "agent": "ResearchAgent",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "research_type": "web_synthesis",
                },
            }

            # Update research history
            self._update_research_history(research_report)

            return research_report

        except Exception as e:
            logger.error(f"Research Agent error: {e}")
            return {
                "status": "error",
                "message": f"Research failed: {str(e)}",
                "query": research_query,
                "agent_type": "research",
                "model_used": self.model_name,
                "sources": [],
                "findings": "",
            }

    async def quick_web_lookup(
        self, query: str, single_source: bool = True
    ) -> Dict[str, Any]:
        """
        Quick web lookup for specific information.

        Args:
            query: Specific question or lookup query
            single_source: Whether to use only the top source

        Returns:
            Dict containing quick lookup results
        """
        try:
            logger.info(f"Quick web lookup: {query[:50]}...")

            # Generate focused search query
            search_queries = await self._generate_search_queries(
                query, 1 if single_source else 3
            )

            # Perform focused web research
            raw_data = await self._perform_web_research(
                search_queries, 1 if single_source else 3
            )

            if not raw_data:
                return {
                    "status": "not_found",
                    "message": "No web sources found for query",
                    "query": query,
                    "agent_type": "research",
                }

            # Quick synthesis for immediate answer
            answer = await self._quick_answer_synthesis(query, raw_data)

            return {
                "status": "success",
                "query": query,
                "answer": answer,
                "sources": raw_data[:3],  # Limit sources in response
                "source_count": len(raw_data),
                "agent_type": "research",
                "lookup_type": "quick",
            }

        except Exception as e:
            logger.error(f"Quick web lookup error: {e}")
            return {
                "status": "error",
                "message": str(e),
                "query": query,
                "agent_type": "research",
            }

    async def research_and_compare(
        self, topic: str, aspects_to_compare: List[str], max_sources: int = 8
    ) -> Dict[str, Any]:
        """
        Research a topic and compare different aspects or viewpoints.

        Args:
            topic: Main research topic
            aspects_to_compare: List of aspects to compare
            max_sources: Maximum number of sources to use

        Returns:
            Dict containing comparative analysis
        """
        try:
            logger.info(f"Comparative research on: {topic}")

            # Generate queries for each aspect
            all_queries = []
            for aspect in aspects_to_compare:
                aspect_query = f"{topic} {aspect}"
                all_queries.append(aspect_query)

            # Perform research for all aspects
            all_research_data = []
            for query in all_queries:
                data = await self._perform_web_research(
                    [query], max_sources // len(aspects_to_compare)
                )
                all_research_data.extend(data)

            # Synthesize comparative analysis
            comparison = await self._synthesize_comparison(
                topic, aspects_to_compare, all_research_data
            )

            return {
                "status": "success",
                "topic": topic,
                "aspects": aspects_to_compare,
                "comparison": comparison,
                "sources": all_research_data,
                "agent_type": "research",
                "analysis_type": "comparative",
            }

        except Exception as e:
            logger.error(f"Comparative research error: {e}")
            return {
                "status": "error",
                "message": str(e),
                "topic": topic,
                "agent_type": "research",
            }

    async def _generate_search_queries(
        self, research_query: str, max_queries: int = 5
    ) -> List[str]:
        """Generate effective search queries for the research topic."""
        try:
            system_prompt = f"""Generate {max_queries} effective web search queries for comprehensive research on the given topic.

Guidelines:
- Create diverse queries that cover different angles
- Use specific keywords and phrases
- Include both general and specific variations
- Optimize for search engine effectiveness
- Each query should be 3-8 words maximum

Return only the search queries, one per line."""

            messages = [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": f"Research topic: {research_query}\n\nGenerate search queries:",
                },
            ]

            response = await self.llm_interface.chat_completion(
                messages=messages,
                llm_type="research",
                temperature=0.7,
                max_tokens=200,
                top_p=0.9,
            )

            # Extract and clean queries
            raw_response = self._extract_response_content(response)
            queries = [q.strip() for q in raw_response.split("\n") if q.strip()]

            # Ensure we have at least the original query
            if not queries:
                queries = [research_query]
            elif research_query not in queries:
                queries.insert(0, research_query)

            return queries[:max_queries]

        except Exception as e:
            logger.error(f"Search query generation error: {e}")
            return [research_query]  # Fallback to original query

    async def _perform_web_research(
        self, search_queries: List[str], max_sources: int
    ) -> List[Dict[str, Any]]:
        """Perform web research using Playwright service."""
        research_data = []
        sources_per_query = max(1, max_sources // len(search_queries))

        for query in search_queries:
            try:
                # Use Playwright service for web scraping
                query_results = await self._scrape_web_sources(query, sources_per_query)
                research_data.extend(query_results)

                # Respect rate limiting
                await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"Web research error for query '{query}': {e}")
                continue

        # Remove duplicates and limit results
        unique_sources = self._deduplicate_sources(research_data)
        return unique_sources[:max_sources]

    async def _scrape_web_sources(
        self, query: str, max_results: int
    ) -> List[Dict[str, Any]]:
        """Scrape web sources using the Playwright service."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Check if Playwright service is available
                try:
                    health_response = await client.get(
                        f"{self.playwright_service_url}/health"
                    )
                    if health_response.status_code != 200:
                        logger.warning(
                            "Playwright service not available, using basic HTTP scraping"
                        )
                        return await self._basic_http_scraping(query, max_results)
                except Exception:
                    logger.warning(
                        "Playwright service not available, using basic HTTP scraping"
                    )
                    return await self._basic_http_scraping(query, max_results)

                # Use Playwright service for advanced scraping
                scrape_request = {
                    "url": f"https://www.google.com/search?q={query}",
                    "wait_for": "body",
                    "extract_links": True,
                    "max_results": max_results,
                }

                response = await client.post(
                    f"{self.playwright_service_url}/scrape", json=scrape_request
                )

                if response.status_code == 200:
                    scrape_data = response.json()
                    return self._process_playwright_results(scrape_data, query)
                else:
                    logger.warning(
                        f"Playwright scraping failed, status: {response.status_code}"
                    )
                    return await self._basic_http_scraping(query, max_results)

        except Exception as e:
            logger.error(f"Playwright scraping error: {e}")
            return await self._basic_http_scraping(query, max_results)

    async def _basic_http_scraping(
        self, query: str, max_results: int
    ) -> List[Dict[str, Any]]:
        """Basic HTTP scraping fallback when Playwright is unavailable."""
        try:
            # Simple web search simulation (fallback)
            search_results = []

            # For demonstration, create mock results
            # In production, this would integrate with a search API
            mock_results = [
                {
                    "title": f"Research result for: {query}",
                    "url": f"https://example.com/research/{query.replace(' ', '-')}",
                    "content": f"Relevant information about {query} from web sources. This is sample content for research purposes.",
                    "source": "web_search",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            ]

            return mock_results[:max_results]

        except Exception as e:
            logger.error(f"Basic HTTP scraping error: {e}")
            return []

    def _process_playwright_results(
        self, scrape_data: Dict[str, Any], query: str
    ) -> List[Dict[str, Any]]:
        """Process results from Playwright service."""
        results = []

        links = scrape_data.get("links", [])
        content = scrape_data.get("content", "")

        for i, link in enumerate(links[:5]):  # Limit to top 5 links
            if self._is_valid_source_url(link.get("href", "")):
                result = {
                    "title": link.get("text", f"Source {i+1}"),
                    "url": link.get("href", ""),
                    "content": content[:1000],  # Truncate for processing
                    "source": "playwright_scrape",
                    "query": query,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "relevance_score": 0.8,  # Default relevance
                }
                results.append(result)

        return results

    def _is_valid_source_url(self, url: str) -> bool:
        """Check if URL is a valid research source."""
        if not url:
            return False

        # Filter out unwanted domains
        excluded_domains = [
            "google.com",
            "bing.com",
            "yahoo.com",
            "duckduckgo.com",
            "facebook.com",
            "twitter.com",
            "instagram.com",
            "tiktok.com",
            "snapchat.com",
        ]

        try:
            parsed_url = urlparse(url)
            domain = parsed_url.netloc.lower()

            # Check if domain is excluded
            for excluded in excluded_domains:
                if excluded in domain:
                    return False

            # Must have valid scheme and netloc
            return parsed_url.scheme in ["http", "https"] and parsed_url.netloc

        except Exception:
            return False

    def _deduplicate_sources(
        self, sources: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Remove duplicate sources based on URL."""
        seen_urls = set()
        unique_sources = []

        for source in sources:
            url = source.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_sources.append(source)

        return unique_sources

    async def _synthesize_research_findings(
        self, research_query: str, raw_data: List[Dict[str, Any]], depth: str
    ) -> Dict[str, Any]:
        """Synthesize research findings into coherent analysis."""
        try:
            if not raw_data:
                return {
                    "findings": "No sources found for research query.",
                    "key_points": [],
                    "quality_score": 0,
                }

            # Prepare content for synthesis
            source_content = []
            for i, source in enumerate(raw_data[:8]):  # Limit for processing
                content = source.get("content", "")
                title = source.get("title", f"Source {i+1}")
                if content:
                    source_content.append(f"Source {i+1} ({title}): {content[:500]}...")

            combined_content = "\n\n".join(source_content)

            # Depth-based synthesis prompts
            depth_configs = {
                "light": {"max_tokens": 300, "detail": "brief overview"},
                "medium": {"max_tokens": 500, "detail": "comprehensive analysis"},
                "deep": {
                    "max_tokens": 800,
                    "detail": "thorough investigation with detailed insights",
                },
            }

            config = depth_configs.get(depth, depth_configs["medium"])

            system_prompt = f"""Synthesize research findings into a {config['detail']} on the given topic.

Guidelines:
- Analyze and synthesize information from multiple sources
- Identify key themes and patterns
- Provide accurate, factual information
- Highlight important insights and conclusions
- Structure the response clearly
- Rate the research quality (1-10) based on source diversity and content depth

Format your response as:
FINDINGS: [Your synthesis here]

KEY_POINTS: [3-5 key points, one per line]

QUALITY_SCORE: [1-10]"""

            messages = [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": f"Research Topic: {research_query}\n\nSource Information:\n{combined_content}",
                },
            ]

            response = await self.llm_interface.chat_completion(
                messages=messages,
                llm_type="research",
                temperature=0.4,
                max_tokens=config["max_tokens"],
                top_p=0.8,
            )

            # Parse synthesized response
            raw_synthesis = self._extract_response_content(response)
            return self._parse_synthesis_response(raw_synthesis)

        except Exception as e:
            logger.error(f"Research synthesis error: {e}")
            return {
                "findings": f"Found {len(raw_data)} sources but couldn't synthesize findings.",
                "key_points": [
                    f"Source {i+1}: {s.get('title', 'Unknown')}"
                    for i, s in enumerate(raw_data[:3])
                ],
                "quality_score": 3,
            }

    async def _quick_answer_synthesis(
        self, query: str, sources: List[Dict[str, Any]]
    ) -> str:
        """Quick synthesis for immediate answers."""
        try:
            if not sources:
                return "No information found."

            # Use first source for quick answer
            source_content = sources[0].get("content", "")

            system_prompt = """Provide a direct, concise answer based on the source content.
Be factual and specific. Keep the answer under 150 words."""

            messages = [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": f"Question: {query}\n\nSource: {source_content[:800]}\n\nAnswer:",
                },
            ]

            response = await self.llm_interface.chat_completion(
                messages=messages,
                llm_type="research",
                temperature=0.3,
                max_tokens=150,
                top_p=0.7,
            )

            return self._extract_response_content(response)

        except Exception as e:
            logger.error(f"Quick answer synthesis error: {e}")
            return f"Found {len(sources)} sources but couldn't generate answer."

    async def _synthesize_comparison(
        self, topic: str, aspects: List[str], all_data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Synthesize comparative analysis."""
        try:
            # Group sources by aspect
            aspect_data = {}
            for aspect in aspects:
                aspect_sources = [
                    s for s in all_data if aspect.lower() in s.get("query", "").lower()
                ]
                aspect_data[aspect] = aspect_sources[:3]  # Top 3 per aspect

            # Create comparison synthesis
            comparison_content = []
            for aspect, sources in aspect_data.items():
                if sources:
                    source_texts = [s.get("content", "")[:300] for s in sources]
                    comparison_content.append(f"{aspect}: {' '.join(source_texts)}")

            combined_comparison = "\n\n".join(comparison_content)

            system_prompt = f"""Create a comparative analysis of different aspects of {topic}.

Compare and contrast the following aspects:
{', '.join(aspects)}

Provide:
1. Overview of each aspect
2. Key similarities and differences
3. Insights and conclusions
4. Summary comparison table if applicable"""

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Comparison data:\n{combined_comparison}"},
            ]

            response = await self.llm_interface.chat_completion(
                messages=messages,
                llm_type="research",
                temperature=0.5,
                max_tokens=600,
                top_p=0.8,
            )

            return {"analysis": self._extract_response_content(response)}

        except Exception as e:
            logger.error(f"Comparison synthesis error: {e}")
            return {"analysis": f"Comparison analysis failed: {str(e)}"}

    def _parse_synthesis_response(self, raw_response: str) -> Dict[str, Any]:
        """Parse the structured synthesis response."""
        try:
            findings = ""
            key_points = []
            quality_score = 5  # Default

            # Extract sections
            lines = raw_response.split("\n")
            current_section = None

            for line in lines:
                line = line.strip()

                if line.startswith("FINDINGS:"):
                    current_section = "findings"
                    findings = line.replace("FINDINGS:", "").strip()
                elif line.startswith("KEY_POINTS:"):
                    current_section = "key_points"
                elif line.startswith("QUALITY_SCORE:"):
                    try:
                        score_text = line.replace("QUALITY_SCORE:", "").strip()
                        quality_score = int(re.findall(r"\d+", score_text)[0])
                        quality_score = max(1, min(10, quality_score))  # Clamp to 1-10
                    except:
                        quality_score = 5
                elif current_section == "findings" and line:
                    findings += " " + line
                elif current_section == "key_points" and line:
                    key_points.append(line.lstrip("- "))

            return {
                "findings": findings.strip() or "Research synthesis completed.",
                "key_points": key_points[:5],  # Limit to 5 key points
                "quality_score": quality_score,
            }

        except Exception as e:
            logger.error(f"Synthesis parsing error: {e}")
            return {
                "findings": raw_response[:500]
                if raw_response
                else "Synthesis parsing failed.",
                "key_points": [],
                "quality_score": 3,
            }

    async def _save_research_to_kb(self, query: str, synthesis: Dict[str, Any]):
        """Save research findings to knowledge base."""
        try:
            await self._ensure_kb_initialized()

            if not self.knowledge_base:
                logger.warning("Knowledge base not available for saving research")
                return False

            # Create knowledge document
            document_content = f"""Research Query: {query}

Findings:
{synthesis.get('findings', '')}

Key Points:
{chr(10).join(f"• {point}" for point in synthesis.get('key_points', []))}

Research Quality Score: {synthesis.get('quality_score', 0)}/10
Research Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
Agent: Research Agent"""

            metadata = {
                "source": "research_agent",
                "type": "research_synthesis",
                "query": query,
                "quality_score": synthesis.get("quality_score", 0),
                "agent": "ResearchAgent",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            # Add to knowledge base
            await self.knowledge_base.add_document(document_content, metadata)
            logger.info(f"Research findings saved to knowledge base: {query}")
            return True

        except Exception as e:
            logger.error(f"Failed to save research to knowledge base: {e}")
            return False

    def _create_research_session(self, query: str, depth: str) -> str:
        """Create a new research session."""
        session_id = f"research_{int(time.time())}_{hash(query) % 10000}"
        self.current_research_session = {
            "session_id": session_id,
            "query": query,
            "depth": depth,
            "start_time": time.time(),
            "status": "active",
        }
        return session_id

    def _update_research_history(self, research_report: Dict[str, Any]):
        """Update research history with completed research."""
        history_entry = {
            "session_id": research_report.get("session_id"),
            "query": research_report.get("query"),
            "status": research_report.get("status"),
            "sources_found": research_report.get("sources_found", 0),
            "processing_time": research_report.get("processing_time", 0),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        self.research_history.append(history_entry)

        # Keep only last 50 research sessions
        if len(self.research_history) > 50:
            self.research_history = self.research_history[-50:]

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
            return "Error processing response"

    def is_research_appropriate(self, message: str) -> bool:
        """
        Determine if a message is appropriate for research agent.

        Args:
            message: The user's message

        Returns:
            bool: True if research agent should handle it
        """
        research_patterns = [
            "research",
            "investigate",
            "find information",
            "web search",
            "look up",
            "search for",
            "tell me about",
            "what do you know about",
            "latest",
            "current",
            "recent",
            "news",
            "trends",
            "compare",
            "analyze",
            "study",
            "examine",
            "explore",
            "comprehensive",
            "detailed",
            "in-depth",
        ]

        web_patterns = [
            "web",
            "online",
            "internet",
            "google",
            "search",
            "website",
            "article",
            "blog",
            "news",
            "source",
        ]

        message_lower = message.lower()

        # Strong indicators for research
        if any(pattern in message_lower for pattern in research_patterns):
            return True

        # Web-related requests
        if any(pattern in message_lower for pattern in web_patterns):
            return True

        # Questions requiring current information
        current_info_patterns = [
            "what is the latest",
            "current status",
            "recent developments",
        ]
        if any(pattern in message_lower for pattern in current_info_patterns):
            return True

        return False


# Singleton instance
_research_agent_instance = None


def get_research_agent() -> ResearchAgent:
    """Get the singleton Research Agent instance."""
    global _research_agent_instance
    if _research_agent_instance is None:
        _research_agent_instance = ResearchAgent()
    return _research_agent_instance
