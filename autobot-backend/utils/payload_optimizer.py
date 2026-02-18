#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Request Payload Optimization for Claude API
Prevents 413 errors and reduces API usage by analyzing and optimizing
request payloads through compression, summarization, and intelligent chunking.
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Pattern

logger = logging.getLogger(__name__)

# Issue #380: Pre-compiled regex patterns for text compression
_WHITESPACE_RE = re.compile(r"\s+")
_REDUNDANT_PATTERNS: List[Pattern] = [
    re.compile(r"\b(the|a|an)\s+", re.IGNORECASE),  # Articles
    re.compile(r"\b(very|really|quite|rather)\s+", re.IGNORECASE),  # Intensifiers
    re.compile(r"\s*(,|;)\s*", re.IGNORECASE),  # Punctuation spacing
]

# Issue #380: Module-level tuples for type checking
_SEQUENCE_TYPES = (list, tuple)
_SIMPLE_HASHABLE_TYPES = (str, int, float, bool)

# Issue #328 - extracted complex conditional into named function


def is_empty_value(value: Any) -> bool:
    """Check if a value is considered empty (None, empty string/list/dict)."""
    return value is None or value == "" or value == [] or value == {}


def _compress_value_by_type(optimizer: "PayloadOptimizer", value: Any) -> Optional[Any]:
    """Compress a value based on its type. (Issue #315 - extracted)"""
    if isinstance(value, dict):
        result = optimizer._compress_dict(value)
        return result if result else None
    if isinstance(value, list):
        result = optimizer._compress_list(value)
        return result if result else None
    if isinstance(value, str):
        result = optimizer._compress_text(value)
        return result if result else None
    return value


@dataclass
class OptimizationResult:
    """Result of payload optimization"""

    original_size: int
    optimized_size: int
    chunks: List[Any]
    optimization_type: str
    savings_percent: float
    needs_chunking: bool


class PayloadOptimizer:
    """
    Intelligent payload optimization to prevent Claude API crashes.

    Features:
    - Size analysis and warnings
    - Text compression and summarization
    - Intelligent chunking for large payloads
    - Context preservation across chunks
    - TodoWrite optimization
    """

    def __init__(
        self,
        max_size: int = 30000,
        warning_size: int = 20000,
        chunk_size: int = 15000,
        overlap_size: int = 500,
    ):
        """Initialize payload optimizer with size thresholds."""
        self.max_size = max_size
        self.warning_size = warning_size
        self.chunk_size = chunk_size
        self.overlap_size = overlap_size

        # Lock for thread-safe stats access
        import threading

        self._stats_lock = threading.Lock()

        # Optimization statistics
        self.total_optimizations = 0
        self.total_size_saved = 0
        self.compression_count = 0
        self.chunking_count = 0

        logger.info(
            "PayloadOptimizer initialized: max=%s, chunk=%s", max_size, chunk_size
        )

    def optimize_payload(self, payload: Any, context: str = "") -> OptimizationResult:
        """
        Optimize payload to prevent 413 errors and reduce API usage.

        Args:
            payload: The payload to optimize
            context: Additional context about the payload type

        Returns:
            OptimizationResult with optimized chunks and metadata
        """
        original_size = self._calculate_size(payload)

        # Quick return if payload is already small
        if original_size <= self.warning_size:
            return OptimizationResult(
                original_size=original_size,
                optimized_size=original_size,
                chunks=[payload],
                optimization_type="none",
                savings_percent=0.0,
                needs_chunking=False,
            )

        # Apply appropriate optimization strategy
        if original_size > self.max_size:
            return self._chunk_payload(payload, original_size, context)
        else:
            return self._compress_payload(payload, original_size, context)

    def optimize_todowrite_payload(self, todos: List[Dict]) -> OptimizationResult:
        """
        Specialized optimization for TodoWrite payloads.
        Reduces verbose todo updates by using incremental changes.
        """
        original_size = self._calculate_size(todos)

        if original_size <= self.warning_size:
            return OptimizationResult(
                original_size=original_size,
                optimized_size=original_size,
                chunks=[todos],
                optimization_type="none",
                savings_percent=0.0,
                needs_chunking=False,
            )

        # Optimize todo structure
        optimized_todos = self._optimize_todo_structure(todos)
        optimized_size = self._calculate_size(optimized_todos)

        # If still too large, chunk by priority
        if optimized_size > self.max_size:
            chunks = self._chunk_todos_by_priority(optimized_todos)
            total_chunked_size = sum(self._calculate_size(chunk) for chunk in chunks)

            return OptimizationResult(
                original_size=original_size,
                optimized_size=total_chunked_size,
                chunks=chunks,
                optimization_type="todo_chunking",
                savings_percent=((original_size - total_chunked_size) / original_size)
                * 100,
                needs_chunking=True,
            )

        savings = ((original_size - optimized_size) / original_size) * 100

        # Update stats with lock protection
        with self._stats_lock:
            self.total_optimizations += 1
            self.total_size_saved += original_size - optimized_size

        return OptimizationResult(
            original_size=original_size,
            optimized_size=optimized_size,
            chunks=[optimized_todos],
            optimization_type="todo_optimization",
            savings_percent=savings,
            needs_chunking=False,
        )

    def optimize_file_read_request(
        self, file_paths: List[str], max_files_per_chunk: int = 3
    ) -> List[List[str]]:
        """
        Optimize file reading requests to prevent large payloads.
        Chunks file lists to manageable sizes.
        """
        if len(file_paths) <= max_files_per_chunk:
            return [file_paths]

        chunks = []
        for i in range(0, len(file_paths), max_files_per_chunk):
            chunk = file_paths[i : i + max_files_per_chunk]
            chunks.append(chunk)

        logger.info("Split %s file reads into %s chunks", len(file_paths), len(chunks))
        return chunks

    def _calculate_size(self, payload: Any) -> int:
        """Calculate payload size in bytes"""
        try:
            if isinstance(payload, str):
                return len(payload.encode("utf-8"))
            elif isinstance(payload, dict):
                return len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            elif isinstance(payload, _SEQUENCE_TYPES):  # Issue #380
                return len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            else:
                return len(str(payload).encode("utf-8"))
        except Exception as e:
            logger.warning("Failed to calculate payload size: %s", e)
            return 0

    def _compress_payload(
        self, payload: Any, original_size: int, context: str
    ) -> OptimizationResult:
        """Apply compression techniques to reduce payload size"""
        if isinstance(payload, str):
            compressed = self._compress_text(payload)
        elif isinstance(payload, dict):
            compressed = self._compress_dict(payload)
        elif isinstance(payload, list):
            compressed = self._compress_list(payload)
        else:
            compressed = payload

        compressed_size = self._calculate_size(compressed)
        savings = ((original_size - compressed_size) / original_size) * 100

        # Update stats with lock protection
        with self._stats_lock:
            self.total_optimizations += 1
            self.compression_count += 1
            self.total_size_saved += original_size - compressed_size

        return OptimizationResult(
            original_size=original_size,
            optimized_size=compressed_size,
            chunks=[compressed],
            optimization_type="compression",
            savings_percent=savings,
            needs_chunking=False,
        )

    def _chunk_payload(
        self, payload: Any, original_size: int, context: str
    ) -> OptimizationResult:
        """Split large payload into manageable chunks"""
        if isinstance(payload, str):
            chunks = self._chunk_text(payload)
        elif isinstance(payload, list):
            chunks = self._chunk_list(payload)
        elif isinstance(payload, dict):
            chunks = self._chunk_dict(payload)
        else:
            # Fallback: convert to string and chunk
            chunks = self._chunk_text(str(payload))

        total_chunked_size = sum(self._calculate_size(chunk) for chunk in chunks)
        savings = ((original_size - total_chunked_size) / original_size) * 100

        # Update stats with lock protection
        with self._stats_lock:
            self.total_optimizations += 1
            self.chunking_count += 1

        logger.info(
            f"Split payload into {len(chunks)} chunks, {savings:.1f}% size reduction"
        )

        return OptimizationResult(
            original_size=original_size,
            optimized_size=total_chunked_size,
            chunks=chunks,
            optimization_type="chunking",
            savings_percent=savings,
            needs_chunking=True,
        )

    def _compress_text(self, text: str) -> str:
        """Compress text by removing redundancy and unnecessary whitespace"""
        # Remove excessive whitespace (Issue #380: use pre-compiled pattern)
        compressed = _WHITESPACE_RE.sub(" ", text)

        # Remove redundant phrases (Issue #380: use pre-compiled patterns)
        for compiled_pattern in _REDUNDANT_PATTERNS:
            compressed = compiled_pattern.sub(" ", compressed)

        return compressed.strip()

    def _compress_dict(self, data: dict) -> dict:
        """Compress dictionary by removing empty values and shortening keys (Issue #315)"""
        compressed = {}
        for key, value in data.items():
            if is_empty_value(value):
                continue
            short_key = self._shorten_key(key)
            compressed_value = _compress_value_by_type(self, value)
            if compressed_value is not None:
                compressed[short_key] = compressed_value
        return compressed

    def _compress_list(self, data: list) -> list:
        """Compress list by removing duplicates and empty items (Issue #315)"""
        compressed = []
        seen = set()

        for item in data:
            if is_empty_value(item):
                continue
            # Handle duplicates for simple types (Issue #380: use module-level tuple)
            if isinstance(item, _SIMPLE_HASHABLE_TYPES):
                if item not in seen:
                    seen.add(item)
                    compressed.append(item)
                continue
            # For complex types, compress recursively using helper
            compressed_item = _compress_value_by_type(self, item)
            if compressed_item is not None:
                compressed.append(compressed_item)
        return compressed

    def _shorten_key(self, key: str) -> str:
        """Shorten dictionary keys to reduce payload size"""
        key_mappings = {
            "description": "desc",
            "implementation": "impl",
            "verification": "verify",
            "dependencies": "deps",
            "activeForm": "active",
            "status": "st",
            "content": "cnt",
            "timestamp": "ts",
            "response": "resp",
            "request": "req",
        }

        return key_mappings.get(key, key)

    def _chunk_text(self, text: str) -> List[str]:
        """Split text into chunks with overlap for context preservation"""
        if len(text) <= self.chunk_size:
            return [text]

        chunks = []
        start = 0

        while start < len(text):
            end = min(start + self.chunk_size, len(text))

            # Try to break at sentence boundaries
            if end < len(text):
                sentence_break = text.rfind(".", start, end)
                if sentence_break > start + self.chunk_size // 2:
                    end = sentence_break + 1

            chunk = text[start:end]
            chunks.append(chunk)

            # Add overlap for context
            start = end - self.overlap_size if end < len(text) else end

        return chunks

    def _chunk_list(self, data: list) -> List[List]:
        """Split list into smaller chunks"""
        # Estimate items per chunk based on average item size
        if not data:
            return [data]

        sample_size = self._calculate_size(data[: min(5, len(data))])
        avg_item_size = sample_size / min(5, len(data))
        items_per_chunk = max(1, int(self.chunk_size / avg_item_size))

        chunks = []
        for i in range(0, len(data), items_per_chunk):
            chunk = data[i : i + items_per_chunk]
            chunks.append(chunk)

        return chunks

    def _chunk_dict(self, data: dict) -> List[Dict]:
        """Split dictionary into smaller dictionaries"""
        if len(data) <= 5:  # Small dict, don't chunk
            return [data]

        items = list(data.items())
        chunk_size = max(3, len(items) // 3)  # Aim for 3 chunks

        chunks = []
        for i in range(0, len(items), chunk_size):
            chunk_items = items[i : i + chunk_size]
            chunk_dict = dict(chunk_items)
            chunks.append(chunk_dict)

        return chunks

    def _optimize_todo_structure(self, todos: List[Dict]) -> List[Dict]:
        """Optimize todo list structure to reduce size"""
        optimized = []

        for todo in todos:
            optimized_todo = {}

            # Use shortened keys
            for key, value in todo.items():
                short_key = self._shorten_key(key)

                # Compress text fields
                if isinstance(value, str):
                    optimized_todo[short_key] = self._compress_text(value)
                else:
                    optimized_todo[short_key] = value

            optimized.append(optimized_todo)

        return optimized

    def _group_todos_by_status(self, todos: List[Dict]) -> Dict[str, List[Dict]]:
        """
        Group todos by their status field.

        Args:
            todos: List of todo dictionaries

        Returns:
            Dictionary mapping status to list of todos. Issue #620.
        """
        status_groups: Dict[str, List[Dict]] = {
            "in_progress": [],
            "pending": [],
            "completed": [],
        }
        for todo in todos:
            status = todo.get("status", todo.get("st", "pending"))
            if status in status_groups:
                status_groups[status].append(todo)
            else:
                status_groups["pending"].append(todo)
        return status_groups

    def _add_todos_to_chunks(
        self,
        todo_list: List[Dict],
        chunks: List[List[Dict]],
        current_chunk: List[Dict],
        current_size: int,
    ) -> tuple:
        """
        Add todos to chunks respecting size limits.

        Args:
            todo_list: List of todos to add
            chunks: Accumulated chunks list
            current_chunk: Current chunk being built
            current_size: Current chunk size

        Returns:
            Tuple of (chunks, current_chunk, current_size). Issue #620.
        """
        for todo in todo_list:
            todo_size = self._calculate_size(todo)
            if current_size + todo_size > self.chunk_size and current_chunk:
                chunks.append(current_chunk)
                current_chunk = []
                current_size = 0
            current_chunk.append(todo)
            current_size += todo_size
        return chunks, current_chunk, current_size

    def _chunk_todos_by_priority(self, todos: List[Dict]) -> List[List[Dict]]:
        """Chunk todos by priority: in_progress, pending, completed. Issue #620."""
        chunks: List[List[Dict]] = []
        current_chunk: List[Dict] = []
        current_size = 0

        status_groups = self._group_todos_by_status(todos)

        # Process in priority order: in_progress, pending, completed
        for status in ["in_progress", "pending", "completed"]:
            chunks, current_chunk, current_size = self._add_todos_to_chunks(
                status_groups[status], chunks, current_chunk, current_size
            )

        if current_chunk:
            chunks.append(current_chunk)

        return chunks if chunks else [[]]

    def get_optimization_stats(self) -> Dict[str, Any]:
        """Get optimization statistics (thread-safe)"""
        # Copy stats under lock
        with self._stats_lock:
            total_optimizations = self.total_optimizations
            total_size_saved = self.total_size_saved
            compression_count = self.compression_count
            chunking_count = self.chunking_count

        return {
            "total_optimizations": total_optimizations,
            "total_size_saved": total_size_saved,
            "compression_count": compression_count,
            "chunking_count": chunking_count,
            "average_savings": total_size_saved / max(total_optimizations, 1),
            "settings": {
                "max_size": self.max_size,
                "warning_size": self.warning_size,
                "chunk_size": self.chunk_size,
                "overlap_size": self.overlap_size,
            },
        }

    def reset_stats(self):
        """Reset optimization statistics (thread-safe)"""
        with self._stats_lock:
            self.total_optimizations = 0
            self.total_size_saved = 0
            self.compression_count = 0
            self.chunking_count = 0


# Global instance (thread-safe)
import threading

_global_optimizer: Optional[PayloadOptimizer] = None
_global_optimizer_lock = threading.Lock()


def get_payload_optimizer() -> PayloadOptimizer:
    """Get the global payload optimizer instance (thread-safe)"""
    global _global_optimizer
    if _global_optimizer is None:
        with _global_optimizer_lock:
            # Double-check after acquiring lock
            if _global_optimizer is None:
                _global_optimizer = PayloadOptimizer()
    return _global_optimizer


def optimize_payload(payload: Any, context: str = "") -> OptimizationResult:
    """Convenience function to optimize any payload"""
    optimizer = get_payload_optimizer()
    return optimizer.optimize_payload(payload, context)


def optimize_todowrite(todos: List[Dict]) -> OptimizationResult:
    """Convenience function to optimize TodoWrite payloads"""
    optimizer = get_payload_optimizer()
    return optimizer.optimize_todowrite_payload(todos)


# Example usage
if __name__ == "__main__":
    # Test payload optimization
    optimizer = PayloadOptimizer(max_size=1000, chunk_size=500)

    # Test with large text
    large_text = "This is a very long text. " * 100
    result = optimizer.optimize_payload(large_text, "test_text")

    logger.info("Original size: {result.original_size}")
    logger.info("Optimized size: {result.optimized_size}")
    logger.info("Chunks: {len(result.chunks)}")
    logger.info("Savings: {result.savings_percent:.1f}%")
    logger.info("Optimization type: {result.optimization_type}")
