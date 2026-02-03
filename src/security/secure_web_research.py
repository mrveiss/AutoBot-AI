# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Secure Web Research Wrapper for AutoBot

Provides secure web research functionality with comprehensive safety checks,
input validation, domain security, and content filtering.
"""

import logging
import time
from datetime import datetime
from typing import Any, Dict, FrozenSet, Optional


from ..agents.web_research_integration import ResearchType, WebResearchIntegration
from .domain_security import DomainSecurityConfig, DomainSecurityManager
from .input_validator import WebResearchInputValidator

logger = logging.getLogger(__name__)

# Issue #380: Module-level frozenset for risk levels requiring confirmation
_CONFIRMATION_REQUIRED_RISK_LEVELS: FrozenSet[str] = frozenset({"medium", "high"})


class SecureWebResearch:
    """
    Secure wrapper for web research operations with comprehensive safety checks
    """

    def __init__(
        self,
        domain_config: Optional[DomainSecurityConfig] = None,
        enable_content_filtering: bool = True,
        enable_query_validation: bool = True,
        enable_domain_validation: bool = True,
    ):
        """Initialize secure web research with security components and filtering."""
        # Initialize security components
        self.domain_security = DomainSecurityManager(domain_config)
        self.input_validator = WebResearchInputValidator()
        self.research_integration = WebResearchIntegration()

        # Security settings
        self.enable_content_filtering = enable_content_filtering
        self.enable_query_validation = enable_query_validation
        self.enable_domain_validation = enable_domain_validation

        # Security statistics
        self.security_stats = {
            "queries_validated": 0,
            "queries_blocked": 0,
            "domains_checked": 0,
            "domains_blocked": 0,
            "content_filtered": 0,
            "threats_detected": 0,
            "last_reset": time.time(),
        }

        logger.info("SecureWebResearch initialized with security features enabled")

    async def __aenter__(self):
        """Async context manager entry"""
        await self.domain_security.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.domain_security.__aexit__(exc_type, exc_val, exc_tb)

    async def _validate_result_security(
        self, result: Dict[str, Any], research_result: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Validate security of a single research result (Issue #298 - extracted helper).

        Returns the result with security metadata if safe, None if blocked.
        """
        result_url = result.get("url", "")

        # Domain validation
        if result_url and self.enable_domain_validation:
            domain_validation = await self.domain_security.validate_domain_safety(result_url)

            self.security_stats["domains_checked"] += 1
            research_result["security"]["domain_checks"].append({
                "url": result_url,
                "safe": domain_validation["safe"],
                "reason": domain_validation["reason"],
                "reputation_score": domain_validation["reputation_score"],
            })

            if not domain_validation["safe"]:
                logger.warning("Domain blocked: %s - %s", result_url, domain_validation['reason'])
                self.security_stats["domains_blocked"] += 1
                self.security_stats["threats_detected"] += len(domain_validation["threats_detected"])
                return None

        # Content filtering
        if self.enable_content_filtering and result.get("content"):
            content_validation = self.input_validator.sanitize_web_content(
                result["content"], result.get("content_type", "text/html")
            )

            if content_validation["threats_detected"]:
                self.security_stats["content_filtered"] += 1
                research_result["security"]["content_filtered"] = True
                result["content"] = content_validation["sanitized_content"]
                result["security_warnings"] = content_validation["warnings"]
                result["threats_removed"] = content_validation["threats_detected"]

        # Add security metadata
        result["security"] = {
            "domain_validated": self.enable_domain_validation,
            "content_filtered": self.enable_content_filtering,
            "safe": True,
        }
        return result

    def _create_research_result(self, query: str) -> Dict[str, Any]:
        """Create initial research result structure."""
        return {
            "status": "blocked",
            "query": query,
            "results": [],
            "security": {
                "threats_detected": [],
                "warnings": [],
                "domain_checks": [],
                "content_filtered": False,
                "risk_level": "unknown",
            },
            "timestamp": datetime.now().isoformat(),
            "from_cache": False,
        }

    def _validate_query(
        self, query: str, research_result: Dict[str, Any], require_user_confirmation: bool
    ) -> tuple:
        """Validate query and return (sanitized_query, early_return_result or None)."""
        if not self.enable_query_validation:
            return query, None

        logger.info("Validating research query for security threats")
        query_validation = self.input_validator.validate_research_query(query)

        self.security_stats["queries_validated"] += 1
        research_result["security"]["query_validation"] = query_validation

        if not query_validation["safe"]:
            logger.warning("Query blocked due to security concerns: %s", query_validation['threats_detected'])
            self.security_stats["queries_blocked"] += 1
            self.security_stats["threats_detected"] += len(query_validation["threats_detected"])

            research_result.update({
                "status": "blocked_unsafe_query",
                "message": f"Query blocked for security: {', '.join(query_validation['threats_detected'])}",
                "security": {
                    **research_result["security"],
                    "threats_detected": query_validation["threats_detected"],
                    "risk_level": query_validation["risk_level"],
                },
            })
            return None, research_result

        research_result["security"]["warnings"] = query_validation["warnings"]
        research_result["security"]["risk_level"] = query_validation["risk_level"]

        if require_user_confirmation and query_validation["risk_level"] in _CONFIRMATION_REQUIRED_RISK_LEVELS:
            research_result.update({
                "status": "requires_confirmation",
                "message": f"Query requires user confirmation due to {query_validation['risk_level']} risk level",
                "confirmation_required": True,
                "risk_factors": query_validation.get("warnings", []),
            })
            return None, research_result

        return query_validation["sanitized_query"], None

    async def _process_raw_results(
        self, raw_results: Dict[str, Any], research_result: Dict[str, Any]
    ) -> None:
        """Process raw results with security validation."""
        if raw_results.get("status") != "success" or not raw_results.get("results"):
            research_result.update({
                "status": raw_results.get("status", "failed"),
                "message": raw_results.get("message", "Research failed"),
                "results": [],
            })
            return

        secure_results = []
        for idx, result in enumerate(raw_results["results"]):
            try:
                validated = await self._validate_result_security(result, research_result)
                if validated:
                    secure_results.append(validated)
            except Exception as e:
                logger.error("Error validating result %s: %s", idx, e)
                continue

        research_result.update({
            "status": "success",
            "message": f"Secure research completed with {len(secure_results)} validated results",
            "results": secure_results,
            "total_results_found": len(raw_results["results"]),
            "results_filtered": len(raw_results["results"]) - len(secure_results),
        })

    def _add_performance_metrics(
        self, research_result: Dict[str, Any], processing_time: float
    ) -> None:
        """Add performance metrics to research result."""
        research_result["performance"] = {
            "processing_time_seconds": round(processing_time, 2),
            "security_checks_performed": sum([
                1 if self.enable_query_validation else 0,
                self.security_stats["domains_checked"]
                - (research_result.get("total_results_found", 0) or 0)
                + len(research_result["results"]),
                1 if self.enable_content_filtering else 0,
            ]),
            "results_per_second": (
                round(len(research_result["results"]) / processing_time, 2)
                if processing_time > 0
                else 0
            ),
        }

    def _create_error_result(self, query: str, error: Exception) -> Dict[str, Any]:
        """Create error result for failed research."""
        return {
            "status": "error",
            "message": f"Secure research failed: {str(error)}",
            "query": query,
            "results": [],
            "security": {
                "threats_detected": ["RESEARCH_ERROR"],
                "warnings": [f"Research error: {str(error)}"],
                "domain_checks": [],
                "content_filtered": False,
                "risk_level": "high",
            },
            "timestamp": datetime.now().isoformat(),
        }

    async def conduct_secure_research(
        self,
        query: str,
        research_type: Optional[ResearchType] = None,
        max_results: Optional[int] = None,
        timeout: Optional[int] = None,
        require_user_confirmation: bool = True,
    ) -> Dict[str, Any]:
        """Conduct secure web research with comprehensive safety checks."""
        research_result = self._create_research_result(query)

        try:
            start_time = time.time()

            # Step 1: Query Validation
            sanitized_query, early_return = self._validate_query(
                query, research_result, require_user_confirmation
            )
            if early_return:
                return early_return

            # Step 2: Execute Research
            logger.info("Executing secure research for query: %s...", sanitized_query[:50])
            raw_results = await self.research_integration.conduct_research(
                query=sanitized_query,
                research_type=research_type,
                max_results=max_results,
                timeout=timeout,
            )

            # Step 3: Process results with security validation
            await self._process_raw_results(raw_results, research_result)

            # Step 4: Add performance metrics
            processing_time = time.time() - start_time
            self._add_performance_metrics(research_result, processing_time)

            logger.info("Secure research completed: %s results, %.2fs", len(research_result['results']), processing_time)
            return research_result

        except Exception as e:
            logger.error("Error during secure research: %s", e)
            return self._create_error_result(query, e)

    async def validate_research_query(self, query: str) -> Dict[str, Any]:
        """Validate a research query without executing research"""
        if self.enable_query_validation:
            return self.input_validator.validate_research_query(query)
        else:
            return {
                "safe": True,
                "sanitized_query": query,
                "threats_detected": [],
                "risk_level": "low",
                "warnings": [],
                "metadata": {},
            }

    async def check_domain_safety(self, url: str) -> Dict[str, Any]:
        """Check domain safety without conducting research"""
        if self.enable_domain_validation:
            return await self.domain_security.validate_domain_safety(url)
        else:
            return {
                "safe": True,
                "reason": "Domain validation disabled",
                "reputation_score": 1.0,
                "threats_detected": [],
                "metadata": {},
            }

    def get_security_statistics(self) -> Dict[str, Any]:
        """Get comprehensive security statistics"""
        uptime_seconds = time.time() - self.security_stats["last_reset"]

        return {
            "uptime_seconds": round(uptime_seconds, 2),
            "security_stats": self.security_stats.copy(),
            "domain_security_stats": self.domain_security.get_security_stats(),
            "input_validator_stats": self.input_validator.get_validation_stats(),
            "security_features": {
                "query_validation": self.enable_query_validation,
                "domain_validation": self.enable_domain_validation,
                "content_filtering": self.enable_content_filtering,
            },
            "rates": {
                "queries_per_hour": round(
                    (self.security_stats["queries_validated"] / uptime_seconds) * 3600,
                    2,
                ),
                "block_rate": round(
                    (
                        self.security_stats["queries_blocked"]
                        / max(self.security_stats["queries_validated"], 1)
                    )
                    * 100,
                    1,
                ),
                "domain_block_rate": round(
                    (
                        self.security_stats["domains_blocked"]
                        / max(self.security_stats["domains_checked"], 1)
                    )
                    * 100,
                    1,
                ),
            },
        }

    def reset_security_statistics(self):
        """Reset security statistics"""
        self.security_stats = {
            "queries_validated": 0,
            "queries_blocked": 0,
            "domains_checked": 0,
            "domains_blocked": 0,
            "content_filtered": 0,
            "threats_detected": 0,
            "last_reset": time.time(),
        }
        logger.info("Security statistics reset")

    async def test_security_components(self) -> Dict[str, Any]:
        """Test all security components"""
        test_results = {
            "overall_status": "passed",
            "components": {},
            "timestamp": datetime.now().isoformat(),
        }

        try:
            # Test input validator
            test_query = "How to secure a Python application?"
            query_result = await self.validate_research_query(test_query)
            test_results["components"]["input_validator"] = {
                "status": "passed" if query_result["safe"] else "failed",
                "details": query_result,
            }

            # Test domain security
            test_url = "https://github.com/example/repo"
            domain_result = await self.check_domain_safety(test_url)
            test_results["components"]["domain_security"] = {
                "status": "passed" if domain_result["safe"] else "failed",
                "details": domain_result,
            }

            # Test malicious input detection
            malicious_query = "<script>alert('xss')</script>"
            malicious_result = await self.validate_research_query(malicious_query)
            test_results["components"]["malicious_detection"] = {
                "status": "passed" if not malicious_result["safe"] else "failed",
                "details": malicious_result,
            }

            # Overall status
            component_statuses = [
                comp["status"] for comp in test_results["components"].values()
            ]
            if any(status == "failed" for status in component_statuses):
                test_results["overall_status"] = "failed"

            return test_results

        except Exception as e:
            logger.error("Error testing security components: %s", e)
            return {
                "overall_status": "error",
                "error": str(e),
                "components": test_results.get("components", {}),
                "timestamp": datetime.now().isoformat(),
            }


# Convenience functions
async def conduct_secure_research(
    query: str,
    research_type: Optional[ResearchType] = None,
    max_results: Optional[int] = None,
    timeout: Optional[int] = None,
    require_user_confirmation: bool = True,
) -> Dict[str, Any]:
    """Standalone function for secure research"""
    async with SecureWebResearch() as secure_research:
        return await secure_research.conduct_secure_research(
            query=query,
            research_type=research_type,
            max_results=max_results,
            timeout=timeout,
            require_user_confirmation=require_user_confirmation,
        )


async def validate_research_safety(
    query: str, url: Optional[str] = None
) -> Dict[str, Any]:
    """Validate research query and optional URL for safety"""
    async with SecureWebResearch() as secure_research:
        results = {
            "query_validation": await secure_research.validate_research_query(query)
        }

        if url:
            results["domain_validation"] = await secure_research.check_domain_safety(
                url
            )

        results["overall_safe"] = results["query_validation"]["safe"] and (
            not url or results.get("domain_validation", {}).get("safe", True)
        )

        return results
