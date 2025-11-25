# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Common Type Definitions for AutoBot

Provides reusable type definitions to replace generic Dict[str, Any] patterns.
"""

from typing import Dict, List, Optional, Union

# Type alias for timestamp strings (ISO 8601 format)
TimestampStr = str

# JSON-compatible types
JSONPrimitive = Union[str, int, float, bool, None]
JSONArray = List["JSONValue"]
JSONObject = Dict[str, "JSONValue"]
JSONValue = Union[JSONPrimitive, JSONArray, JSONObject]

# Metadata type - used for generic key-value metadata storage
# More specific than Dict[str, Any] as values must be JSON-serializable
Metadata = Dict[str, JSONValue]

# Metrics dictionary - numeric values with string keys
MetricsDict = Dict[str, Union[int, float]]

# Configuration types
ConfigValue = Union[str, int, float, bool, List[str], Dict[str, str]]
ConfigDict = Dict[str, ConfigValue]

# Search/Filter types
FilterValue = Union[str, int, float, bool, List[str]]
FilterDict = Dict[str, FilterValue]

# Entity ID types (for documentation/clarity)
EntityId = str
SessionId = str
ChatId = str
UserId = str
WorkflowId = str

# Status types
StatusDict = Dict[str, Union[str, bool, int, float, TimestampStr]]

# Error context type
ErrorContext = Dict[str, Union[str, int, float, bool, List[str]]]

# Document/Content types
DocumentContent = Dict[str, Union[str, int, float, List[str], Metadata]]
SearchResult = Dict[str, Union[str, float, int, Metadata]]
SearchResults = List[SearchResult]

# Optional wrapper types for common patterns
OptionalStr = Optional[str]
OptionalInt = Optional[int]
OptionalFloat = Optional[float]
OptionalBool = Optional[bool]
OptionalMetadata = Optional[Metadata]
