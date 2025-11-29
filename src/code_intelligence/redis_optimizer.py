# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Redis Operation Optimizer

Identifies optimization opportunities in Redis usage patterns including:
- Pipeline opportunities (sequential operations that can be batched)
- Lua script candidates (complex atomic operations)
- Data structure optimizations (using more efficient Redis types)
- Connection pooling analysis (connection management patterns)
- Cache invalidation strategies

Part of Issue #220 - Redis Operation Optimizer
Parent Epic: #217 - Advanced Code Intelligence
"""

import ast
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class OptimizationSeverity(Enum):
    """Severity levels for optimization suggestions."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class OptimizationType(Enum):
    """Types of Redis optimizations detected."""

    # Pipeline opportunities
    SEQUENTIAL_GETS = "sequential_gets"
    SEQUENTIAL_SETS = "sequential_sets"
    LOOP_OPERATIONS = "loop_operations"
    MULTI_KEY_FETCH = "multi_key_fetch"

    # Lua script candidates
    READ_MODIFY_WRITE = "read_modify_write"
    CONDITIONAL_SET = "conditional_set"
    ATOMIC_INCREMENT = "atomic_increment"
    COMPLEX_TRANSACTION = "complex_transaction"

    # Data structure optimizations
    STRING_TO_HASH = "string_to_hash"
    LIST_TO_SORTED_SET = "list_to_sorted_set"
    INEFFICIENT_SCAN = "inefficient_scan"
    MISSING_EXPIRY = "missing_expiry"

    # Connection patterns
    CONNECTION_PER_REQUEST = "connection_per_request"
    MISSING_POOL = "missing_pool"
    BLOCKING_IN_ASYNC = "blocking_in_async"

    # Cache patterns
    NO_CACHE_INVALIDATION = "no_cache_invalidation"
    STALE_CACHE_RISK = "stale_cache_risk"
    CACHE_STAMPEDE_RISK = "cache_stampede_risk"


@dataclass
class RedisOperation:
    """Represents a single Redis operation in code."""

    operation: str  # get, set, hget, etc.
    line_number: int
    key_pattern: Optional[str] = None
    is_async: bool = False
    in_loop: bool = False
    context: str = ""  # surrounding code context


@dataclass
class OptimizationResult:
    """Result of Redis optimization analysis for a single finding."""

    optimization_type: OptimizationType
    severity: OptimizationSeverity
    file_path: str
    line_start: int
    line_end: int
    description: str
    suggestion: str
    estimated_improvement: str
    current_code: str = ""
    optimized_code: str = ""
    operations_affected: List[RedisOperation] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "optimization_type": self.optimization_type.value,
            "severity": self.severity.value,
            "file_path": self.file_path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "description": self.description,
            "suggestion": self.suggestion,
            "estimated_improvement": self.estimated_improvement,
            "current_code": self.current_code,
            "optimized_code": self.optimized_code,
            "operations_count": len(self.operations_affected),
            "metrics": self.metrics,
        }


class RedisASTVisitor(ast.NodeVisitor):
    """AST visitor to extract Redis operations from Python code."""

    # Redis operation patterns
    REDIS_OPERATIONS = {
        # String operations
        "get",
        "set",
        "mget",
        "mset",
        "getset",
        "setnx",
        "setex",
        "psetex",
        "incr",
        "incrby",
        "incrbyfloat",
        "decr",
        "decrby",
        "append",
        # Hash operations
        "hget",
        "hset",
        "hmget",
        "hmset",
        "hgetall",
        "hdel",
        "hexists",
        "hincrby",
        "hincrbyfloat",
        "hkeys",
        "hvals",
        "hlen",
        "hsetnx",
        # List operations
        "lpush",
        "rpush",
        "lpop",
        "rpop",
        "lrange",
        "llen",
        "lindex",
        "lset",
        "lrem",
        "ltrim",
        "blpop",
        "brpop",
        # Set operations
        "sadd",
        "srem",
        "smembers",
        "sismember",
        "scard",
        "sunion",
        "sinter",
        "sdiff",
        "spop",
        "srandmember",
        # Sorted set operations
        "zadd",
        "zrem",
        "zscore",
        "zrank",
        "zrange",
        "zrevrange",
        "zrangebyscore",
        "zcard",
        "zincrby",
        "zcount",
        # Key operations
        "exists",
        "delete",
        "expire",
        "expireat",
        "ttl",
        "pttl",
        "keys",
        "scan",
        "type",
        "rename",
        # Other
        "ping",
        "pipeline",
        "execute",
        "watch",
        "multi",
        "exec",
    }

    def __init__(self, source_lines: List[str]):
        self.operations: List[RedisOperation] = []
        self.source_lines = source_lines
        self.current_loop_depth = 0
        self.current_async_context = False
        self.redis_var_names: Set[str] = set()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        """Track async function context."""
        old_async = self.current_async_context
        self.current_async_context = True
        self.generic_visit(node)
        self.current_async_context = old_async

    def visit_For(self, node: ast.For):
        """Track for loop context."""
        self.current_loop_depth += 1
        self.generic_visit(node)
        self.current_loop_depth -= 1

    def visit_While(self, node: ast.While):
        """Track while loop context."""
        self.current_loop_depth += 1
        self.generic_visit(node)
        self.current_loop_depth -= 1

    def visit_Assign(self, node: ast.Assign):
        """Track Redis variable assignments."""
        # Look for redis client assignments
        if isinstance(node.value, ast.Call):
            call_name = self._get_call_name(node.value)
            if call_name and "redis" in call_name.lower():
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self.redis_var_names.add(target.id)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        """Extract Redis operation calls."""
        call_name = self._get_call_name(node)

        # Check if this is a Redis operation
        if call_name:
            parts = call_name.split(".")
            operation = parts[-1] if parts else ""

            # Check if it's a known Redis operation
            if operation.lower() in self.REDIS_OPERATIONS:
                # Check if called on redis variable
                is_redis_call = self._is_redis_call(node)
                if is_redis_call:
                    key_pattern = self._extract_key_pattern(node)
                    context = self._get_context(node.lineno)

                    self.operations.append(
                        RedisOperation(
                            operation=operation.lower(),
                            line_number=node.lineno,
                            key_pattern=key_pattern,
                            is_async=self.current_async_context,
                            in_loop=self.current_loop_depth > 0,
                            context=context,
                        )
                    )

        self.generic_visit(node)

    def _get_call_name(self, node: ast.Call) -> Optional[str]:
        """Get the full name of a function call."""
        if isinstance(node.func, ast.Name):
            return node.func.id
        elif isinstance(node.func, ast.Attribute):
            parts = []
            current = node.func
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
            return ".".join(reversed(parts))
        return None

    def _is_redis_call(self, node: ast.Call) -> bool:
        """Check if this call is on a Redis client."""
        if isinstance(node.func, ast.Attribute):
            # Check the base object
            if isinstance(node.func.value, ast.Name):
                name = node.func.value.id.lower()
                return "redis" in name or node.func.value.id in self.redis_var_names
            elif isinstance(node.func.value, ast.Attribute):
                # Check for self.redis, etc.
                if isinstance(node.func.value.value, ast.Name):
                    if node.func.value.value.id == "self":
                        return "redis" in node.func.value.attr.lower()
        return False

    def _extract_key_pattern(self, node: ast.Call) -> Optional[str]:
        """Extract the key pattern from a Redis call."""
        if node.args:
            first_arg = node.args[0]
            if isinstance(first_arg, ast.Constant):
                return str(first_arg.value)
            elif isinstance(first_arg, ast.JoinedStr):
                # f-string - extract pattern
                parts = []
                for value in first_arg.values:
                    if isinstance(value, ast.Constant):
                        parts.append(str(value.value))
                    else:
                        parts.append("{...}")
                return "".join(parts)
        return None

    def _get_context(self, line_number: int, context_lines: int = 2) -> str:
        """Get surrounding code context."""
        start = max(0, line_number - context_lines - 1)
        end = min(len(self.source_lines), line_number + context_lines)
        return "\n".join(self.source_lines[start:end])


class RedisOptimizer:
    """
    Redis Operation Optimizer for AutoBot codebase.

    Analyzes Python files for Redis usage patterns and identifies
    optimization opportunities including:
    - Pipeline opportunities for batching
    - Lua script candidates for atomicity
    - Data structure improvements
    - Connection management patterns
    """

    def __init__(self, project_root: Optional[str] = None):
        """
        Initialize the Redis optimizer.

        Args:
            project_root: Root directory of the project to analyze
        """
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self.results: List[OptimizationResult] = []

    def analyze_file(self, file_path: str) -> List[OptimizationResult]:
        """
        Analyze a single Python file for Redis optimizations.

        Args:
            file_path: Path to the Python file

        Returns:
            List of optimization results found in the file
        """
        results = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()
                source_lines = source.split("\n")

            # Parse AST
            tree = ast.parse(source)

            # Extract Redis operations
            visitor = RedisASTVisitor(source_lines)
            visitor.visit(tree)

            operations = visitor.operations
            if not operations:
                return results

            # Detect various optimization opportunities
            results.extend(
                self._detect_pipeline_opportunities(file_path, operations, source_lines)
            )
            results.extend(
                self._detect_lua_script_candidates(file_path, operations, source_lines)
            )
            results.extend(
                self._detect_loop_operations(file_path, operations, source_lines)
            )
            results.extend(
                self._detect_data_structure_improvements(
                    file_path, operations, source_lines
                )
            )
            results.extend(
                self._detect_connection_patterns(file_path, source, source_lines)
            )
            results.extend(
                self._detect_cache_patterns(file_path, operations, source_lines)
            )

        except SyntaxError as e:
            logger.warning(f"Syntax error parsing {file_path}: {e}")
        except Exception as e:
            logger.error(f"Error analyzing {file_path}: {e}")

        return results

    def analyze_directory(
        self,
        directory: Optional[str] = None,
        exclude_patterns: Optional[List[str]] = None,
    ) -> List[OptimizationResult]:
        """
        Analyze all Python files in a directory.

        Args:
            directory: Directory to analyze (defaults to project root)
            exclude_patterns: Glob patterns to exclude

        Returns:
            List of all optimization results
        """
        self.results = []
        target_dir = Path(directory) if directory else self.project_root

        exclude_patterns = exclude_patterns or [
            "**/test_*.py",
            "**/*_test.py",
            "**/tests/**",
            "**/archive/**",
            "**/archives/**",
            "**/.git/**",
            "**/node_modules/**",
            "**/__pycache__/**",
            "**/venv/**",
            "**/.venv/**",
        ]

        # Find all Python files
        python_files = list(target_dir.rglob("*.py"))

        for file_path in python_files:
            # Check exclusions
            rel_path = str(file_path.relative_to(target_dir))
            excluded = False
            for pattern in exclude_patterns:
                if Path(rel_path).match(pattern.replace("**/", "")):
                    excluded = True
                    break

            if excluded:
                continue

            file_results = self.analyze_file(str(file_path))
            self.results.extend(file_results)

        logger.info(
            f"Analyzed {len(python_files)} files, found {len(self.results)} optimizations"
        )
        return self.results

    def _detect_pipeline_opportunities(
        self,
        file_path: str,
        operations: List[RedisOperation],
        source_lines: List[str],
    ) -> List[OptimizationResult]:
        """Detect sequential Redis operations that can be pipelined."""
        results = []

        # Group consecutive operations (within 5 lines of each other)
        groups: List[List[RedisOperation]] = []
        current_group: List[RedisOperation] = []

        for op in sorted(operations, key=lambda x: x.line_number):
            if not current_group:
                current_group.append(op)
            elif op.line_number - current_group[-1].line_number <= 5:
                current_group.append(op)
            else:
                if len(current_group) >= 2:
                    groups.append(current_group)
                current_group = [op]

        if len(current_group) >= 2:
            groups.append(current_group)

        # Analyze groups for pipeline opportunities
        for group in groups:
            # Skip if already in a loop (different optimization)
            if any(op.in_loop for op in group):
                continue

            # Check for sequential gets
            gets = [op for op in group if op.operation in ("get", "hget", "mget")]
            if len(gets) >= 2:
                results.append(
                    OptimizationResult(
                        optimization_type=OptimizationType.SEQUENTIAL_GETS,
                        severity=OptimizationSeverity.MEDIUM,
                        file_path=file_path,
                        line_start=gets[0].line_number,
                        line_end=gets[-1].line_number,
                        description=f"Found {len(gets)} sequential GET operations that can be pipelined",
                        suggestion="Use Redis pipeline or MGET for batching these reads",
                        estimated_improvement=f"~{len(gets) - 1} fewer network round-trips",
                        current_code=self._get_code_range(
                            source_lines, gets[0].line_number, gets[-1].line_number
                        ),
                        optimized_code=self._generate_pipeline_code(gets, "get"),
                        operations_affected=gets,
                        metrics={
                            "operation_count": len(gets),
                            "potential_latency_reduction_ms": (len(gets) - 1) * 2,
                        },
                    )
                )

            # Check for sequential sets
            sets = [op for op in group if op.operation in ("set", "hset")]
            if len(sets) >= 2:
                results.append(
                    OptimizationResult(
                        optimization_type=OptimizationType.SEQUENTIAL_SETS,
                        severity=OptimizationSeverity.MEDIUM,
                        file_path=file_path,
                        line_start=sets[0].line_number,
                        line_end=sets[-1].line_number,
                        description=f"Found {len(sets)} sequential SET operations that can be pipelined",
                        suggestion="Use Redis pipeline or MSET for batching these writes",
                        estimated_improvement=f"~{len(sets) - 1} fewer network round-trips",
                        current_code=self._get_code_range(
                            source_lines, sets[0].line_number, sets[-1].line_number
                        ),
                        optimized_code=self._generate_pipeline_code(sets, "set"),
                        operations_affected=sets,
                        metrics={
                            "operation_count": len(sets),
                            "potential_latency_reduction_ms": (len(sets) - 1) * 2,
                        },
                    )
                )

        return results

    def _detect_loop_operations(
        self,
        file_path: str,
        operations: List[RedisOperation],
        source_lines: List[str],
    ) -> List[OptimizationResult]:
        """Detect Redis operations inside loops that should use pipeline."""
        results = []

        loop_ops = [op for op in operations if op.in_loop]
        if not loop_ops:
            return results

        # Group by operation type
        by_type: Dict[str, List[RedisOperation]] = {}
        for op in loop_ops:
            if op.operation not in by_type:
                by_type[op.operation] = []
            by_type[op.operation].append(op)

        for op_type, ops in by_type.items():
            if len(ops) >= 1:  # Even single operation in loop is worth optimizing
                results.append(
                    OptimizationResult(
                        optimization_type=OptimizationType.LOOP_OPERATIONS,
                        severity=OptimizationSeverity.HIGH,
                        file_path=file_path,
                        line_start=ops[0].line_number,
                        line_end=ops[-1].line_number,
                        description=f"Redis '{op_type}' operation inside loop - causes N network round-trips",
                        suggestion=(
                            "Collect keys outside loop, use pipeline() or MGET/MSET batch operations. "
                            "Example: Use 'async with redis.pipeline() as pipe:' before loop"
                        ),
                        estimated_improvement="O(N) -> O(1) network round-trips",
                        current_code=ops[0].context,
                        optimized_code=self._generate_loop_optimization(
                            op_type, ops[0]
                        ),
                        operations_affected=ops,
                        metrics={
                            "operation_count": len(ops),
                            "severity_multiplier": "N (loop iterations)",
                        },
                    )
                )

        return results

    def _detect_lua_script_candidates(
        self,
        file_path: str,
        operations: List[RedisOperation],
        source_lines: List[str],
    ) -> List[OptimizationResult]:
        """Detect patterns that would benefit from Lua scripting."""
        results = []

        # Look for read-modify-write patterns
        for i, op in enumerate(operations):
            if op.operation in ("get", "hget"):
                # Check if followed by set within 10 lines
                for j in range(i + 1, min(i + 5, len(operations))):
                    next_op = operations[j]
                    if next_op.operation in ("set", "hset"):
                        if next_op.line_number - op.line_number <= 10:
                            results.append(
                                OptimizationResult(
                                    optimization_type=OptimizationType.READ_MODIFY_WRITE,
                                    severity=OptimizationSeverity.MEDIUM,
                                    file_path=file_path,
                                    line_start=op.line_number,
                                    line_end=next_op.line_number,
                                    description="Read-modify-write pattern detected (GET followed by SET)",
                                    suggestion=(
                                        "Consider using Lua script for atomic operation, or "
                                        "WATCH/MULTI/EXEC transaction, or built-in atomic commands "
                                        "like INCR, GETSET"
                                    ),
                                    estimated_improvement="Eliminates race condition window, atomic operation",
                                    current_code=self._get_code_range(
                                        source_lines,
                                        op.line_number,
                                        next_op.line_number,
                                    ),
                                    optimized_code=self._generate_lua_example(
                                        op, next_op
                                    ),
                                    operations_affected=[op, next_op],
                                    metrics={
                                        "race_window_lines": next_op.line_number
                                        - op.line_number
                                    },
                                )
                            )
                            break

        return results

    def _detect_data_structure_improvements(
        self,
        file_path: str,
        operations: List[RedisOperation],
        source_lines: List[str],
    ) -> List[OptimizationResult]:
        """Detect suboptimal data structure usage."""
        results = []

        # Detect multiple string keys with same prefix (should be hash)
        key_prefixes: Dict[str, List[RedisOperation]] = {}
        for op in operations:
            if op.key_pattern and op.operation in ("get", "set"):
                # Extract prefix (before first : or {)
                prefix = op.key_pattern.split(":")[0].split("{")[0]
                if prefix not in key_prefixes:
                    key_prefixes[prefix] = []
                key_prefixes[prefix].append(op)

        for prefix, ops in key_prefixes.items():
            if len(ops) >= 3:
                results.append(
                    OptimizationResult(
                        optimization_type=OptimizationType.STRING_TO_HASH,
                        severity=OptimizationSeverity.LOW,
                        file_path=file_path,
                        line_start=ops[0].line_number,
                        line_end=ops[-1].line_number,
                        description=f"Multiple string keys with prefix '{prefix}:' could be a Hash",
                        suggestion=(
                            f"Consider using HSET/HGET with key '{prefix}' instead of "
                            f"multiple string keys. Reduces memory overhead and enables HGETALL."
                        ),
                        estimated_improvement="~30-50% memory reduction for related keys",
                        operations_affected=ops,
                        metrics={"related_keys": len(ops), "prefix": prefix},
                    )
                )

        # Detect KEYS usage (should use SCAN)
        keys_ops = [op for op in operations if op.operation == "keys"]
        for op in keys_ops:
            results.append(
                OptimizationResult(
                    optimization_type=OptimizationType.INEFFICIENT_SCAN,
                    severity=OptimizationSeverity.HIGH,
                    file_path=file_path,
                    line_start=op.line_number,
                    line_end=op.line_number,
                    description="KEYS command used - blocks Redis server during execution",
                    suggestion="Use SCAN for non-blocking iteration over keys",
                    estimated_improvement="Non-blocking operation, prevents Redis stalls",
                    current_code=op.context,
                    optimized_code="async for key in redis.scan_iter(match='pattern*'):",
                    operations_affected=[op],
                    metrics={"blocking_command": True},
                )
            )

        # Detect SET without expiry
        set_ops = [op for op in operations if op.operation == "set"]
        for op in set_ops:
            # Check if ex/px/ttl is mentioned in context
            if "ex=" not in op.context.lower() and "expire" not in op.context.lower():
                results.append(
                    OptimizationResult(
                        optimization_type=OptimizationType.MISSING_EXPIRY,
                        severity=OptimizationSeverity.INFO,
                        file_path=file_path,
                        line_start=op.line_number,
                        line_end=op.line_number,
                        description="SET operation without explicit TTL/expiry",
                        suggestion="Consider adding ex=<seconds> to prevent unbounded memory growth",
                        estimated_improvement="Prevents memory leaks from orphaned keys",
                        current_code=op.context,
                        operations_affected=[op],
                        metrics={"has_expiry": False},
                    )
                )

        return results

    def _detect_connection_patterns(
        self,
        file_path: str,
        source: str,
        source_lines: List[str],
    ) -> List[OptimizationResult]:
        """Detect connection management anti-patterns."""
        results = []

        # Detect direct redis.Redis() instantiation (should use get_redis_client)
        pattern = r"redis\.Redis\s*\("
        for match in re.finditer(pattern, source):
            line_number = source[: match.start()].count("\n") + 1

            # Check if this is the canonical redis_client.py file
            if "redis_client.py" not in file_path:
                results.append(
                    OptimizationResult(
                        optimization_type=OptimizationType.CONNECTION_PER_REQUEST,
                        severity=OptimizationSeverity.HIGH,
                        file_path=file_path,
                        line_start=line_number,
                        line_end=line_number,
                        description="Direct redis.Redis() instantiation - violates canonical pattern",
                        suggestion=(
                            "Use get_redis_client() from src.utils.redis_client. "
                            "This provides connection pooling, circuit breaker, and monitoring."
                        ),
                        estimated_improvement="Connection reuse, automatic retry, health monitoring",
                        current_code=self._get_code_range(
                            source_lines, line_number, line_number + 2
                        ),
                        optimized_code=(
                            "from src.utils.redis_client import get_redis_client\n"
                            "redis = get_redis_client(database='main')"
                        ),
                        metrics={"violates_canonical_pattern": True},
                    )
                )

        # Detect blocking Redis in async context
        async_pattern = r"async\s+def\s+\w+.*?(?=async\s+def|\Z)"
        for async_match in re.finditer(async_pattern, source, re.DOTALL):
            block = async_match.group()
            block_start = source[: async_match.start()].count("\n") + 1

            # Check for sync redis calls without await
            sync_calls = re.findall(r"(?<!await\s)redis\.(get|set|hget|hset)\(", block)
            if sync_calls:
                results.append(
                    OptimizationResult(
                        optimization_type=OptimizationType.BLOCKING_IN_ASYNC,
                        severity=OptimizationSeverity.HIGH,
                        file_path=file_path,
                        line_start=block_start,
                        line_end=block_start + block.count("\n"),
                        description="Potentially blocking Redis call in async function",
                        suggestion=(
                            "Use async Redis client with await: "
                            "redis = await get_redis_client(async_client=True)"
                        ),
                        estimated_improvement="Non-blocking async I/O, better concurrency",
                        metrics={"blocking_calls": len(sync_calls)},
                    )
                )

        return results

    def _detect_cache_patterns(
        self,
        file_path: str,
        operations: List[RedisOperation],
        source_lines: List[str],
    ) -> List[OptimizationResult]:
        """Detect cache-related optimization opportunities."""
        results = []

        # Detect potential cache stampede (GET + SET without lock)
        gets = [op for op in operations if op.operation == "get"]
        sets = [op for op in operations if op.operation == "set"]

        for get_op in gets:
            for set_op in sets:
                if 0 < set_op.line_number - get_op.line_number <= 20:
                    # Check for lock/mutex in between
                    context = self._get_code_range(
                        source_lines, get_op.line_number, set_op.line_number
                    )
                    if "lock" not in context.lower() and "mutex" not in context.lower():
                        # Check for None check pattern (cache miss)
                        if "none" in context.lower() or "if not" in context.lower():
                            results.append(
                                OptimizationResult(
                                    optimization_type=OptimizationType.CACHE_STAMPEDE_RISK,
                                    severity=OptimizationSeverity.MEDIUM,
                                    file_path=file_path,
                                    line_start=get_op.line_number,
                                    line_end=set_op.line_number,
                                    description=(
                                        "Potential cache stampede pattern: "
                                        "GET miss -> compute -> SET without lock"
                                    ),
                                    suggestion=(
                                        "Use distributed lock (SETNX) or probabilistic early expiration. "
                                        "Consider redis-py's lock() context manager."
                                    ),
                                    estimated_improvement="Prevents thundering herd on cache miss",
                                    current_code=context,
                                    optimized_code=self._generate_stampede_protection(
                                        get_op
                                    ),
                                    operations_affected=[get_op, set_op],
                                    metrics={"risk_type": "cache_stampede"},
                                )
                            )
                            break

        return results

    def _get_code_range(self, source_lines: List[str], start: int, end: int) -> str:
        """Get code range from source lines."""
        start_idx = max(0, start - 1)
        end_idx = min(len(source_lines), end)
        return "\n".join(source_lines[start_idx:end_idx])

    def _generate_pipeline_code(
        self, operations: List[RedisOperation], op_type: str
    ) -> str:
        """Generate optimized pipeline code."""
        if op_type == "get":
            return """# Optimized with pipeline
async with redis.pipeline() as pipe:
    for key in keys:
        pipe.get(key)
    results = await pipe.execute()

# Or use MGET for simple gets:
# results = await redis.mget(keys)"""
        else:
            return """# Optimized with pipeline
async with redis.pipeline() as pipe:
    for key, value in items:
        pipe.set(key, value)
    await pipe.execute()

# Or use MSET for simple sets:
# await redis.mset(mapping)"""

    def _generate_loop_optimization(
        self, op_type: str, sample_op: RedisOperation
    ) -> str:
        """Generate optimized code for loop operations."""
        return f"""# Before (O(N) network calls):
# for item in items:
#     result = await redis.{op_type}(...)

# After (O(1) network calls):
async with redis.pipeline() as pipe:
    for item in items:
        pipe.{op_type}(...)
    results = await pipe.execute()"""

    def _generate_lua_example(
        self, get_op: RedisOperation, set_op: RedisOperation
    ) -> str:
        """Generate Lua script example for read-modify-write."""
        return '''# Lua script for atomic read-modify-write
LUA_SCRIPT = """
local current = redis.call('GET', KEYS[1])
-- Modify value here
local new_value = current .. '_modified'
redis.call('SET', KEYS[1], new_value)
return new_value
"""

# Execute atomically
result = await redis.eval(LUA_SCRIPT, 1, key)'''

    def _generate_stampede_protection(self, get_op: RedisOperation) -> str:
        """Generate cache stampede protection code."""
        return """# Protected cache access with lock
async def get_with_lock(redis, key, compute_fn, ttl=300):
    value = await redis.get(key)
    if value is not None:
        return value

    lock_key = f"lock:{key}"
    async with redis.lock(lock_key, timeout=10):
        # Double-check after acquiring lock
        value = await redis.get(key)
        if value is not None:
            return value

        # Compute and cache
        value = await compute_fn()
        await redis.set(key, value, ex=ttl)
        return value"""

    def get_summary(self) -> Dict[str, Any]:
        """Get summary of optimization findings."""
        if not self.results:
            return {
                "total_optimizations": 0,
                "by_severity": {},
                "by_type": {},
                "estimated_improvements": [],
            }

        by_severity: Dict[str, int] = {}
        by_type: Dict[str, int] = {}

        for result in self.results:
            sev = result.severity.value
            opt_type = result.optimization_type.value

            by_severity[sev] = by_severity.get(sev, 0) + 1
            by_type[opt_type] = by_type.get(opt_type, 0) + 1

        return {
            "total_optimizations": len(self.results),
            "by_severity": by_severity,
            "by_type": by_type,
            "files_analyzed": len(set(r.file_path for r in self.results)),
            "critical_findings": [
                r.to_dict()
                for r in self.results
                if r.severity == OptimizationSeverity.CRITICAL
            ],
            "high_priority": [
                r.to_dict()
                for r in self.results
                if r.severity == OptimizationSeverity.HIGH
            ],
        }


# Convenience function for quick analysis
def analyze_redis_usage(
    path: str,
    exclude_patterns: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Analyze Redis usage in a file or directory.

    Args:
        path: File or directory path to analyze
        exclude_patterns: Patterns to exclude

    Returns:
        Analysis results with optimization suggestions
    """
    optimizer = RedisOptimizer()
    path_obj = Path(path)

    if path_obj.is_file():
        results = optimizer.analyze_file(str(path_obj))
    else:
        results = optimizer.analyze_directory(str(path_obj), exclude_patterns)

    return {
        "results": [r.to_dict() for r in results],
        "summary": optimizer.get_summary(),
    }
