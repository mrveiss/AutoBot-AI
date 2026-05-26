# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Task Complexity Scorer - Rule-based classifier for request complexity.

Issue #748: Tiered Model Distribution Implementation.

Scores incoming requests on a 0-10 scale to determine which model tier
should handle the request. Uses lightweight heuristics for fast scoring (~5ms).
"""

import re
from typing import Callable, Dict, List, Optional, Set

from autobot_shared.logging_manager import get_logger

from .tier_config import ComplexityResult, TierConfig

logger = get_logger(__name__)


class TaskComplexityScorer:
    """
    Rule-based complexity scorer for LLM requests.

    Analyzes messages using weighted heuristic factors:
    - Message length (0.13 weight)
    - Code detection (0.23 weight)
    - Technical terms (0.18 weight)
    - Multi-step indicators (0.18 weight)
    - Question complexity (0.18 weight)
    - Output length (0.10 weight)

    Score is normalized to 0-10 scale.
    """

    # Factor weights (must sum to 1.0)
    WEIGHT_LENGTH = 0.13
    WEIGHT_CODE = 0.23
    WEIGHT_TECHNICAL = 0.18
    WEIGHT_MULTISTEP = 0.18
    WEIGHT_QUESTION = 0.18
    WEIGHT_OUTPUT_TOKENS = 0.10

    # Code detection patterns
    CODE_PATTERNS = [
        r"```",  # Markdown code blocks
        r"def\s+\w+\s*\(",  # Python function
        r"class\s+\w+",  # Class definition
        r"function\s+\w+",  # JavaScript function
        r"import\s+\w+",  # Import statement
        r"from\s+\w+\s+import",  # Python from import
        r"const\s+\w+\s*=",  # JavaScript const
        r"let\s+\w+\s*=",  # JavaScript let
        r"var\s+\w+\s*=",  # JavaScript var
        r"async\s+(def|function)",  # Async definitions
        r"@\w+\s*(\(|$)",  # Decorators
        r"<\w+[^>]*>",  # HTML/XML tags
        r"\{\s*\n",  # Code block start
        r"if\s*\(.*\)\s*\{",  # If statement with braces
        r"for\s*\(.*\)\s*\{",  # For loop
        r"while\s*\(.*\)\s*\{",  # While loop
    ]

    # Technical terms that indicate complexity
    TECHNICAL_TERMS: Set[str] = {
        "api",
        "database",
        "sql",
        "regex",
        "async",
        "await",
        "thread",
        "process",
        "memory",
        "cache",
        "queue",
        "redis",
        "docker",
        "kubernetes",
        "microservice",
        "authentication",
        "authorization",
        "encryption",
        "hash",
        "algorithm",
        "recursion",
        "optimization",
        "performance",
        "scalability",
        "architecture",
        "design pattern",
        "dependency injection",
        "middleware",
        "websocket",
        "graphql",
        "rest",
        "oauth",
        "jwt",
        "ssl",
        "tls",
        "cors",
        "csrf",
        "xss",
        "injection",
        "validation",
        "serialization",
        "deserialization",
        "orm",
        "migration",
        "transaction",
        "concurrency",
        "parallelism",
        "mutex",
        "semaphore",
        "deadlock",
        "race condition",
        "callback",
        "promise",
        "observable",
        "reactive",
        "functional",
        "immutable",
        "polymorphism",
        "inheritance",
        "abstraction",
        "encapsulation",
        "interface",
        "protocol",
        "generic",
        "template",
        "macro",
        "compiler",
        "interpreter",
        "bytecode",
        "jit",
        "garbage collection",
        "reference",
        "pointer",
        "heap",
        "stack",
        "buffer",
        "stream",
        "iterator",
        "generator",
        "coroutine",
        "context manager",
        "decorator",
        "metaclass",
        "reflection",
        "introspection",
    }

    # Multi-step indicators
    MULTISTEP_PATTERNS = [
        r"first[\s,]+.*then",
        r"step\s*\d+",
        r"^\s*\d+\.",  # Numbered lists
        r"after\s+that",
        r"next[\s,]+",
        r"finally[\s,]+",
        r"if.*then.*else",
        r"when.*and.*then",
        r"create.*and.*then",
        r"implement.*that.*and",
    ]

    # Question complexity indicators
    COMPLEX_QUESTION_PATTERNS = [
        r"why\s+(does|is|do|are|should|would|could)",
        r"explain\s+(how|why|the)",
        r"compare\s+(and|between)",
        r"difference\s+between",
        r"pros\s+and\s+cons",
        r"trade[\-\s]?offs?",
        r"best\s+(practice|approach|way)",
        r"how\s+would\s+you",
        r"design\s+(a|an|the)",
        r"architect",
        r"implement\s+(a|an)",
        r"optimize",
        r"refactor",
        r"debug",
        r"troubleshoot",
        r"analyze",
    ]

    SIMPLE_QUESTION_PATTERNS = [
        r"^what\s+is\s+",
        r"^how\s+do\s+i\s+",
        r"^can\s+you\s+",
        r"^please\s+",
        r"^show\s+me\s+",
        r"^list\s+",
        r"^give\s+me\s+",
        r"^tell\s+me\s+",
    ]

    # Output-length heuristic patterns
    OUTPUT_LENGTH_PATTERNS = [
        r"summarize|summarise",
        r"list\s+(all|every|each)",
        r"step[\s\-]by[\s\-]step",
        r"enumerate\s+all",
        r"write\s+a\s+(full|complete|detailed|comprehensive)",
        r"generate\s+a\s+(complete|full|detailed)",
    ]

    def __init__(self, config: TierConfig, tokenizer: Optional[Callable[[str], int]] = None):
        """
        Initialize complexity scorer.

        Args:
            config: Tier configuration with threshold settings
            tokenizer: Optional callable that returns the token count for a string.
                       When provided, _score_length uses it for accurate token counting.
                       When None, falls back to len(content) // 4 (char/4 estimate).
        """
        self.config = config
        # tokenizer callable for token-accurate length scoring; falls back to char/4
        self._tokenizer = tokenizer
        self._compiled_code_patterns = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in self.CODE_PATTERNS]
        self._compiled_multistep_patterns = [
            re.compile(p, re.IGNORECASE | re.MULTILINE) for p in self.MULTISTEP_PATTERNS
        ]
        self._compiled_complex_question_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.COMPLEX_QUESTION_PATTERNS
        ]
        self._compiled_simple_question_patterns = [re.compile(p, re.IGNORECASE) for p in self.SIMPLE_QUESTION_PATTERNS]
        self._compiled_output_length_patterns = [re.compile(p, re.IGNORECASE) for p in self.OUTPUT_LENGTH_PATTERNS]

    def estimate_input_tokens(self, messages: List[Dict]) -> int:
        """Estimate the total input token count across all messages.

        Uses self._tokenizer if provided; falls back to char/4 estimate.
        Counts content from every role (system, user, assistant).
        """
        all_content = " ".join(
            msg.get("content", "") for msg in messages if msg.get("content")
        )
        if self._tokenizer is not None:
            return self._tokenizer(all_content)
        return len(all_content) // 4

    def score(self, messages: List[Dict], expected_output_tokens: Optional[int] = None) -> ComplexityResult:
        """
        Score the complexity of a request.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
            expected_output_tokens: Optional hint for the expected number of output
                tokens. When provided, the output_length factor is derived directly
                from this value instead of content heuristics.

        Returns:
            ComplexityResult with score, factors, tier, reasoning, and input_tokens
        """
        # Estimate total input tokens across all messages for long_context routing
        input_tokens = self.estimate_input_tokens(messages)

        # Extract user messages for analysis
        user_content = self._extract_user_content(messages)

        if not user_content:
            return ComplexityResult(
                score=0.0,
                factors={},
                tier="simple",
                reasoning="No user content to analyze",
                input_tokens=input_tokens,
            )

        # Extract max_tokens hint from any message that carries it
        max_tokens: Optional[int] = None
        for msg in messages:
            mt = msg.get("max_tokens")
            if mt is not None and int(mt) > 0:
                max_tokens = int(mt)
                break

        # Calculate individual factor scores (0-3 scale)
        factors = {
            "length": self._score_length(user_content),
            "code": self._score_code(user_content),
            "technical": self._score_technical(user_content),
            "multistep": self._score_multistep(user_content),
            "question": self._score_question(user_content),
            "output_length": self._score_output_length(user_content, expected_output_tokens, max_tokens),
        }

        # Calculate weighted score and build result
        normalized_score = self._calculate_weighted_score(factors)
        return self._build_complexity_result(normalized_score, factors, input_tokens)

    def _extract_user_content(self, messages: List[Dict]) -> str:
        """Extract and combine user message content."""
        user_messages = [msg.get("content", "") for msg in messages if msg.get("role") == "user" and msg.get("content")]
        return " ".join(user_messages)

    def _score_length(self, content: str) -> float:
        """Score based on message length in tokens (0-3).

        Uses self._tokenizer if provided; falls back to char/4 estimate.
        Thresholds are in tokens: 25, 125, 250.
        """
        if self._tokenizer is not None:
            length = self._tokenizer(content)
        else:
            length = len(content) // 4
        if length < 25:
            return 0.0
        elif length < 125:
            return 1.0
        elif length < 250:
            return 2.0
        else:
            return 3.0

    def _score_code(self, content: str) -> float:
        """Score based on code detection (0-3)."""
        matches = 0
        for pattern in self._compiled_code_patterns:
            if pattern.search(content):
                matches += 1
                if matches >= 3:
                    break

        return min(3.0, float(matches))

    def _score_technical(self, content: str) -> float:
        """Score based on technical term density (0-3)."""
        content_lower = content.lower()
        words = set(re.findall(r"\b\w+\b", content_lower))

        # Check for multi-word terms
        term_count = 0
        for term in self.TECHNICAL_TERMS:
            if " " in term:
                if term in content_lower:
                    term_count += 1
            elif term in words:
                term_count += 1

        # Scale: 0 terms = 0, 1-2 = 1, 3-5 = 2, 6+ = 3
        if term_count == 0:
            return 0.0
        elif term_count <= 2:
            return 1.0
        elif term_count <= 5:
            return 2.0
        else:
            return 3.0

    def _score_multistep(self, content: str) -> float:
        """Score based on multi-step indicators (0-3)."""
        matches = 0
        for pattern in self._compiled_multistep_patterns:
            if pattern.search(content):
                matches += 1
                if matches >= 3:
                    break

        return min(3.0, float(matches))

    def _score_question(self, content: str) -> float:
        """Score based on question complexity (0-3)."""
        # Check for simple patterns (reduces score)
        simple_matches = sum(1 for p in self._compiled_simple_question_patterns if p.search(content))

        # Check for complex patterns (increases score)
        complex_matches = sum(1 for p in self._compiled_complex_question_patterns if p.search(content))

        # Net score: complex matches - (simple matches * 0.5)
        net_score = complex_matches - (simple_matches * 0.5)

        # Clamp to 0-3
        return max(0.0, min(3.0, net_score))

    def _score_output_length(
        self,
        content: str,
        expected_output_tokens: Optional[int],
        max_tokens: Optional[int] = None,
    ) -> float:
        """Score based on expected output length (0-3).

        Priority:
        1. explicit expected_output_tokens hint
        2. max_tokens from the message payload
        3. heuristic pattern count from content

        Thresholds (tokens): <100 -> 0.0, <500 -> 1.0, <2000 -> 2.0, >=2000 -> 3.0
        """
        if expected_output_tokens is not None:
            tokens = expected_output_tokens
            if tokens < 100:
                return 0.0
            elif tokens < 500:
                return 1.0
            elif tokens < 2000:
                return 2.0
            else:
                return 3.0

        if max_tokens is not None and max_tokens > 0:
            tokens = max_tokens
            if tokens < 100:
                return 0.0
            elif tokens < 500:
                return 1.0
            elif tokens < 2000:
                return 2.0
            else:
                return 3.0

        # Heuristic fallback: count matching patterns, cap at 3.0
        matches = sum(1 for p in self._compiled_output_length_patterns if p.search(content))
        return min(3.0, float(matches))

    def _calculate_weighted_score(self, factors: Dict[str, float]) -> float:
        """
        Calculate and normalize the weighted complexity score.

        Issue #620.

        Args:
            factors: Dictionary of factor scores (0-3 scale each)

        Returns:
            Normalized score on 0-10 scale
        """
        weighted_score = (
            factors["length"] * self.WEIGHT_LENGTH
            + factors["code"] * self.WEIGHT_CODE
            + factors["technical"] * self.WEIGHT_TECHNICAL
            + factors["multistep"] * self.WEIGHT_MULTISTEP
            + factors["question"] * self.WEIGHT_QUESTION
            + factors["output_length"] * self.WEIGHT_OUTPUT_TOKENS
        )
        # Normalize to 0-10 scale (factors are 0-3, max weighted is 3)
        normalized_score = (weighted_score / 3.0) * 10.0
        return min(10.0, max(0.0, normalized_score))

    def _build_complexity_result(
        self,
        normalized_score: float,
        factors: Dict[str, float],
        input_tokens: int = 0,
    ) -> ComplexityResult:
        """
        Build the final ComplexityResult with tier and reasoning.

        Issue #620.

        Args:
            normalized_score: The normalized 0-10 complexity score
            factors: Dictionary of factor scores
            input_tokens: Estimated total input token count

        Returns:
            ComplexityResult with all fields populated
        """
        tier = "simple" if normalized_score < self.config.complexity_threshold else "complex"
        reasoning = self._generate_reasoning(factors, normalized_score, tier)

        if self.config.logging.log_scores:
            logger.debug(
                "Complexity score: %.1f (%s) - factors: %s",
                normalized_score,
                tier,
                factors,
            )

        return ComplexityResult(
            score=round(normalized_score, 2),
            factors={k: round(v, 2) for k, v in factors.items()},
            tier=tier,
            reasoning=reasoning,
            input_tokens=input_tokens,
        )

    def _generate_reasoning(self, factors: Dict[str, float], score: float, tier: str) -> str:
        """Generate human-readable reasoning for the score."""
        # Find dominant factors (score > 1.5)
        dominant = [k for k, v in factors.items() if v > 1.5]

        if not dominant:
            if score < 1:
                return "Simple request with no complexity indicators"
            return "Low complexity request with minimal indicators"

        factor_names = {
            "length": "message length",
            "code": "code patterns",
            "technical": "technical terminology",
            "multistep": "multi-step requirements",
            "question": "question complexity",
            "output_length": "output length",
        }

        dominant_names = [factor_names.get(f, f) for f in dominant]

        if tier == "simple":
            return f"Low complexity despite {', '.join(dominant_names)}"
        else:
            return f"High complexity due to {', '.join(dominant_names)}"


__all__ = ["TaskComplexityScorer"]
