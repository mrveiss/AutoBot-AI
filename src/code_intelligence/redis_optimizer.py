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
from typing import Any, Dict, FrozenSet, List, Optional, Set

logger = logging.getLogger(__name__)

# Issue #380: Module-level frozensets for Redis operation type checking
_GET_OPERATIONS: FrozenSet[str] = frozenset({"get", "hget", "mget"})
_SET_OPERATIONS: FrozenSet[str] = frozenset({"set", "hset"})
_READ_OPERATIONS: FrozenSet[str] = frozenset({"get", "hget"})
_WRITE_OPERATIONS: FrozenSet[str] = frozenset({"set", "hset"})
_STRING_KEY_OPERATIONS: FrozenSet[str] = frozenset({"get", "set"})

# Issue #380: Pre-compiled regex patterns for async function blocking detection
_ASYNC_DEF_PATTERN_RE = re.compile(r"async\s+def\s+\w+.*?(?=async\s+def|\Z)", re.DOTALL)
_SYNC_REDIS_CALL_RE = re.compile(r"(?<!await\s)redis\.(get|set|hget|hset)\(")


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
        """Initialize visitor with source lines and operation tracking state."""
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

    def _check_self_redis_attr(self, func_value: ast.Attribute) -> bool:
        """Check if attribute is self.redis-like (Issue #335 - extracted helper)."""
        if not isinstance(func_value.value, ast.Name):
            return False
        if func_value.value.id != "self":
            return False
        return "redis" in func_value.attr.lower()

    def _is_redis_call(self, node: ast.Call) -> bool:
        """Check if this call is on a Redis client."""
        if not isinstance(node.func, ast.Attribute):
            return False

        # Check the base object
        if isinstance(node.func.value, ast.Name):
            name = node.func.value.id.lower()
            return "redis" in name or node.func.value.id in self.redis_var_names

        if isinstance(node.func.value, ast.Attribute):
            return self._check_self_redis_attr(node.func.value)

        return False

    def _extract_fstring_pattern(self, fstring: ast.JoinedStr) -> str:
        """Extract pattern from f-string (Issue #335 - extracted helper)."""
        parts = []
        for value in fstring.values:
            if isinstance(value, ast.Constant):
                parts.append(str(value.value))
            else:
                parts.append("{...}")
        return "".join(parts)

    def _extract_key_pattern(self, node: ast.Call) -> Optional[str]:
        """Extract the key pattern from a Redis call."""
        if not node.args:
            return None

        first_arg = node.args[0]
        if isinstance(first_arg, ast.Constant):
            return str(first_arg.value)

        if isinstance(first_arg, ast.JoinedStr):
            return self._extract_fstring_pattern(first_arg)

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
        self.total_files_scanned: int = 0  # Issue #686: Track total files analyzed

    def _run_all_detectors(
        self,
        file_path: str,
        operations: List[RedisOperation],
        source: str,
        source_lines: List[str],
    ) -> List[OptimizationResult]:
        """Run all optimization detectors on the parsed file."""
        results: List[OptimizationResult] = []
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
        results.extend(self._detect_cache_patterns(file_path, operations, source_lines))
        return results

    def analyze_file(self, file_path: str) -> List[OptimizationResult]:
        """
        Analyze a single Python file for Redis optimizations.

        Args:
            file_path: Path to the Python file

        Returns:
            List of optimization results found in the file
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()
                source_lines = source.split("\n")

            tree = ast.parse(source)
            visitor = RedisASTVisitor(source_lines)
            visitor.visit(tree)

            if not visitor.operations:
                return []

            return self._run_all_detectors(
                file_path, visitor.operations, source, source_lines
            )

        except SyntaxError as e:
            logger.warning("Syntax error parsing %s: %s", file_path, e)
        except Exception as e:
            logger.error("Error analyzing %s: %s", file_path, e)

        return []

    def _get_default_exclude_patterns(self) -> List[str]:
        """Return default patterns to exclude from analysis."""
        return [
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

    def _is_path_excluded(self, rel_path: str, exclude_patterns: List[str]) -> bool:
        """Check if a relative path matches any exclusion pattern."""
        for pattern in exclude_patterns:
            if Path(rel_path).match(pattern.replace("**/", "")):
                return True
        return False

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
        self.total_files_scanned = 0  # Issue #686: Reset counter
        target_dir = Path(directory) if directory else self.project_root
        exclude_patterns = exclude_patterns or self._get_default_exclude_patterns()
        python_files = list(target_dir.rglob("*.py"))

        for file_path in python_files:
            rel_path = str(file_path.relative_to(target_dir))
            if not self._is_path_excluded(rel_path, exclude_patterns):
                self.total_files_scanned += 1  # Issue #686: Count all files scanned
                self.results.extend(self.analyze_file(str(file_path)))

        logger.info(
            "Analyzed %d files, found %d optimizations",
            self.total_files_scanned,
            len(self.results),
        )
        return self.results

    def _group_consecutive_operations(
        self, operations: List[RedisOperation]
    ) -> List[List[RedisOperation]]:
        """Group consecutive Redis operations within 5 lines of each other."""
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
        return groups

    def _create_sequential_ops_result(
        self,
        file_path: str,
        ops: List[RedisOperation],
        source_lines: List[str],
        op_type: str,
        opt_type: OptimizationType,
    ) -> OptimizationResult:
        """Create optimization result for sequential operations."""
        op_label = "GET" if op_type == "get" else "SET"
        return OptimizationResult(
            optimization_type=opt_type,
            severity=OptimizationSeverity.MEDIUM,
            file_path=file_path,
            line_start=ops[0].line_number,
            line_end=ops[-1].line_number,
            description=f"Found {len(ops)} sequential {op_label} operations that can be pipelined",
            suggestion=f"Use Redis pipeline or M{op_label} for batching these {'reads' if op_type == 'get' else 'writes'}",
            estimated_improvement=f"~{len(ops) - 1} fewer network round-trips",
            current_code=self._get_code_range(
                source_lines, ops[0].line_number, ops[-1].line_number
            ),
            optimized_code=self._generate_pipeline_code(ops, op_type),
            operations_affected=ops,
            metrics={
                "operation_count": len(ops),
                "potential_latency_reduction_ms": (len(ops) - 1) * 2,
            },
        )

    def _detect_pipeline_opportunities(
        self,
        file_path: str,
        operations: List[RedisOperation],
        source_lines: List[str],
    ) -> List[OptimizationResult]:
        """Detect sequential Redis operations that can be pipelined."""
        results = []
        groups = self._group_consecutive_operations(operations)

        for group in groups:
            if any(op.in_loop for op in group):
                continue

            gets = [op for op in group if op.operation in _GET_OPERATIONS]
            if len(gets) >= 2:
                results.append(
                    self._create_sequential_ops_result(
                        file_path,
                        gets,
                        source_lines,
                        "get",
                        OptimizationType.SEQUENTIAL_GETS,
                    )
                )

            sets = [op for op in group if op.operation in _SET_OPERATIONS]
            if len(sets) >= 2:
                results.append(
                    self._create_sequential_ops_result(
                        file_path,
                        sets,
                        source_lines,
                        "set",
                        OptimizationType.SEQUENTIAL_SETS,
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

    def _find_following_write_op(
        self, operations: List[RedisOperation], start_idx: int, read_op: RedisOperation
    ) -> Optional[RedisOperation]:
        """Find a write operation following a read (Issue #335 - extracted helper)."""
        for j in range(start_idx + 1, min(start_idx + 5, len(operations))):
            next_op = operations[j]
            if next_op.operation not in _WRITE_OPERATIONS:
                continue
            if next_op.line_number - read_op.line_number <= 10:
                return next_op
        return None

    def _create_lua_candidate_result(
        self,
        file_path: str,
        read_op: RedisOperation,
        write_op: RedisOperation,
        source_lines: List[str],
    ) -> OptimizationResult:
        """Create optimization result for Lua candidate (Issue #335 - extracted helper)."""
        return OptimizationResult(
            optimization_type=OptimizationType.READ_MODIFY_WRITE,
            severity=OptimizationSeverity.MEDIUM,
            file_path=file_path,
            line_start=read_op.line_number,
            line_end=write_op.line_number,
            description="Read-modify-write pattern detected (GET followed by SET)",
            suggestion=(
                "Consider using Lua script for atomic operation, or "
                "WATCH/MULTI/EXEC transaction, or built-in atomic commands "
                "like INCR, GETSET"
            ),
            estimated_improvement="Eliminates race condition window, atomic operation",
            current_code=self._get_code_range(
                source_lines,
                read_op.line_number,
                write_op.line_number,
            ),
            optimized_code=self._generate_lua_example(read_op, write_op),
            operations_affected=[read_op, write_op],
            metrics={"race_window_lines": write_op.line_number - read_op.line_number},
        )

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
            if op.operation not in _READ_OPERATIONS:
                continue

            write_op = self._find_following_write_op(operations, i, op)
            if write_op:
                results.append(
                    self._create_lua_candidate_result(
                        file_path, op, write_op, source_lines
                    )
                )

        return results

    def _detect_string_to_hash_opportunities(
        self, file_path: str, operations: List[RedisOperation]
    ) -> List[OptimizationResult]:
        """Detect string keys that could be consolidated into hashes."""
        results = []
        key_prefixes: Dict[str, List[RedisOperation]] = {}
        for op in operations:
            if op.key_pattern and op.operation in _STRING_KEY_OPERATIONS:
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
                        suggestion=f"Consider using HSET/HGET with key '{prefix}' instead. Reduces memory overhead.",
                        estimated_improvement="~30-50% memory reduction for related keys",
                        operations_affected=ops,
                        metrics={"related_keys": len(ops), "prefix": prefix},
                    )
                )
        return results

    def _detect_inefficient_keys_usage(
        self, file_path: str, operations: List[RedisOperation]
    ) -> List[OptimizationResult]:
        """Detect KEYS command usage that should use SCAN instead."""
        results = []
        for op in operations:
            if op.operation == "keys":
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
        return results

    def _detect_missing_expiry(
        self, file_path: str, operations: List[RedisOperation]
    ) -> List[OptimizationResult]:
        """Detect SET operations without TTL/expiry."""
        results = []
        for op in operations:
            if op.operation != "set":
                continue
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

    def _detect_data_structure_improvements(
        self,
        file_path: str,
        operations: List[RedisOperation],
        source_lines: List[str],
    ) -> List[OptimizationResult]:
        """Detect suboptimal data structure usage."""
        results = []
        results.extend(self._detect_string_to_hash_opportunities(file_path, operations))
        results.extend(self._detect_inefficient_keys_usage(file_path, operations))
        results.extend(self._detect_missing_expiry(file_path, operations))
        return results

    def _detect_direct_redis_instantiation(
        self, file_path: str, source: str, source_lines: List[str]
    ) -> List[OptimizationResult]:
        """Detect direct redis.Redis() instantiation that violates canonical pattern."""
        if "redis_client.py" in file_path:
            return []

        results = []
        pattern = r"redis\.Redis\s*\("
        for match in re.finditer(pattern, source):
            line_number = source[: match.start()].count("\n") + 1
            results.append(
                OptimizationResult(
                    optimization_type=OptimizationType.CONNECTION_PER_REQUEST,
                    severity=OptimizationSeverity.HIGH,
                    file_path=file_path,
                    line_start=line_number,
                    line_end=line_number,
                    description="Direct redis.Redis() instantiation - violates canonical pattern",
                    suggestion="Use get_redis_client() from src.utils.redis_client. Provides pooling and monitoring.",
                    estimated_improvement="Connection reuse, automatic retry, health monitoring",
                    current_code=self._get_code_range(
                        source_lines, line_number, line_number + 2
                    ),
                    optimized_code="from src.utils.redis_client import get_redis_client\nredis = get_redis_client(database='main')",
                    metrics={"violates_canonical_pattern": True},
                )
            )
        return results

    def _detect_blocking_in_async(
        self, file_path: str, source: str
    ) -> List[OptimizationResult]:
        """Detect blocking Redis calls in async functions."""
        results = []
        # Issue #380: Use pre-compiled patterns for async blocking detection
        for async_match in _ASYNC_DEF_PATTERN_RE.finditer(source):
            block = async_match.group()
            block_start = source[: async_match.start()].count("\n") + 1
            sync_calls = _SYNC_REDIS_CALL_RE.findall(block)
            if sync_calls:
                results.append(
                    OptimizationResult(
                        optimization_type=OptimizationType.BLOCKING_IN_ASYNC,
                        severity=OptimizationSeverity.HIGH,
                        file_path=file_path,
                        line_start=block_start,
                        line_end=block_start + block.count("\n"),
                        description="Potentially blocking Redis call in async function",
                        suggestion="Use async Redis client: redis = await get_redis_client(async_client=True)",
                        estimated_improvement="Non-blocking async I/O, better concurrency",
                        metrics={"blocking_calls": len(sync_calls)},
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
        results.extend(
            self._detect_direct_redis_instantiation(file_path, source, source_lines)
        )
        results.extend(self._detect_blocking_in_async(file_path, source))
        return results

    def _is_stampede_risk(self, context: str) -> bool:
        """Check if context shows cache stampede risk (Issue #335 - extracted helper)."""
        context_lower = context.lower()
        # Has lock protection
        if "lock" in context_lower or "mutex" in context_lower:
            return False
        # Has cache miss pattern
        return "none" in context_lower or "if not" in context_lower

    def _check_get_set_stampede(
        self,
        file_path: str,
        get_op: RedisOperation,
        set_op: RedisOperation,
        source_lines: List[str],
    ) -> Optional[OptimizationResult]:
        """Check GET/SET pair for stampede risk (Issue #335 - extracted helper)."""
        line_diff = set_op.line_number - get_op.line_number
        if not (0 < line_diff <= 20):
            return None

        context = self._get_code_range(
            source_lines, get_op.line_number, set_op.line_number
        )
        if not self._is_stampede_risk(context):
            return None

        return OptimizationResult(
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
            optimized_code=self._generate_stampede_protection(get_op),
            operations_affected=[get_op, set_op],
            metrics={"risk_type": "cache_stampede"},
        )

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
                result = self._check_get_set_stampede(
                    file_path, get_op, set_op, source_lines
                )
                if result:
                    results.append(result)
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
        """
        Get summary of optimization findings.

        Issue #686: Uses exponential decay scoring to prevent score overflow.
        Scores now degrade gracefully instead of immediately hitting 0.
        """
        # Import scoring utilities
        from src.code_intelligence.shared.scoring import (
            calculate_score_from_severity_counts,
            get_grade_from_score,
        )

        if not self.results:
            return {
                "total_optimizations": 0,
                "by_severity": {},
                "by_type": {},
                "estimated_improvements": [],
                "redis_health_score": 100.0,
                "grade": "A",
                "files_analyzed": self.total_files_scanned,
                "files_with_issues": 0,
            }

        by_severity: Dict[str, int] = {}
        by_type: Dict[str, int] = {}

        for result in self.results:
            sev = result.severity.value
            opt_type = result.optimization_type.value

            by_severity[sev] = by_severity.get(sev, 0) + 1
            by_type[opt_type] = by_type.get(opt_type, 0) + 1

        # Issue #686: Use exponential decay scoring instead of linear deduction
        # This prevents scores from immediately collapsing to 0 with many issues
        redis_health_score = calculate_score_from_severity_counts(by_severity)

        # Issue #686: Use total_files_scanned instead of files with issues
        files_analyzed = (
            self.total_files_scanned
            if self.total_files_scanned > 0
            else len(set(r.file_path for r in self.results))
        )

        return {
            "total_optimizations": len(self.results),
            "by_severity": by_severity,
            "by_type": by_type,
            "redis_health_score": redis_health_score,
            "grade": get_grade_from_score(redis_health_score),
            "files_analyzed": files_analyzed,
            "files_with_issues": len(set(r.file_path for r in self.results)),
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
