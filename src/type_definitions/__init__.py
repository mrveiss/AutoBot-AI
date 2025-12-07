# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Centralized Type Definitions
Consolidates commonly used typing imports to reduce duplication across the codebase
"""

import datetime
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum, IntEnum
from pathlib import Path
from typing import (
    Any,
    AsyncGenerator,
    Awaitable,
    Callable,
    ClassVar,
    Coroutine,
    Dict,
    Final,
    FrozenSet,
    Generator,
    Generic,
    Iterable,
    Iterator,
    List,
    Literal,
    Mapping,
    NamedTuple,
    Optional,
    Protocol,
    Sequence,
    Set,
    Tuple,
    TypeVar,
    Union,
)

from typing_extensions import NotRequired, TypedDict

# Common type aliases
StrDict = Dict[str, Any]
StrList = List[str]
OptionalStr = Optional[str]
OptionalInt = Optional[int]
OptionalFloat = Optional[float]
OptionalBool = Optional[bool]
OptionalDict = Optional[Dict[str, Any]]
OptionalList = Optional[List[Any]]

# Configuration types
ConfigDict = Dict[str, Any]
ConfigMapping = Mapping[str, Any]
EnvironmentDict = Dict[str, str]

# API response types
APIResponse = Dict[str, Any]
JSONDict = Dict[str, Any]
ResponseData = Dict[str, Any]
ErrorDict = Dict[str, str]

# Data structure types
ResultList = List[Dict[str, Any]]
KeyValuePairs = Dict[str, str]
MetadataDict = Dict[str, Any]
StatsDict = Dict[str, Union[int, float, str]]

# File and path types
FilePath = Union[str, Path]
DirectoryPath = Union[str, Path]
PathLike = Union[str, Path]

# Numeric types
NumericValue = Union[int, float, Decimal]
PositiveInt = int  # Should be > 0
NonNegativeInt = int  # Should be >= 0
Percentage = float  # Should be 0.0 - 100.0

# Time and date types
TimeStamp = Union[datetime.datetime, str, float]
DateTimeStr = str
ISOTimestamp = str

# Async types
AsyncCallable = Callable[..., Awaitable[Any]]
AsyncGenerator = AsyncGenerator[Any, None]
SyncOrAsyncCallable = Union[Callable[..., Any], AsyncCallable]

# Agent and AI types
AgentID = str
TaskID = str
WorkflowID = str
SessionID = str
UserID = str
RequestID = str

# LLM and model types
ModelName = str
PromptText = str
ResponseText = str
TokenCount = int
Temperature = float  # 0.0 - 2.0
MaxTokens = int

# Database and storage types
DatabaseRow = Dict[str, Any]
QueryResult = List[DatabaseRow]
QueryParameters = Union[List[Any], Dict[str, Any]]
ConnectionString = str

# Network and communication types
URL = str
IPAddress = str
Port = int
Headers = Dict[str, str]
StatusCode = int

# Cache and Redis types
CacheKey = str
CacheValue = Any
TTL = int  # Time to live in seconds
RedisValue = Union[str, bytes, int, float]

# Validation and error types
ValidationError = Dict[str, str]
ErrorCode = str
ErrorMessage = str
WarningMessage = str

# WebSocket and communication types
WebSocketMessage = Dict[str, Any]
EventData = Dict[str, Any]
NotificationData = Dict[str, Any]

# Security and authentication types
Token = str
ApiKey = str
SecretKey = str
Hash = str
Salt = str

# Hardware and system types
GPUInfo = Dict[str, Any]
SystemStats = Dict[str, Any]
ResourceUsage = Dict[str, Union[int, float]]


# Common TypedDict definitions for structured data
class TaskConfig(TypedDict):
    """Configuration for task execution"""

    task_id: str
    agent_type: str
    parameters: Dict[str, Any]
    timeout: NotRequired[int]
    priority: NotRequired[int]


class CacheEntry(TypedDict):
    """Cache entry structure"""

    data: Any
    timestamp: float
    ttl: int
    data_type: str


class APIEndpointInfo(TypedDict):
    """API endpoint information"""

    path: str
    method: str
    description: str
    cached: NotRequired[bool]
    cache_ttl: NotRequired[int]


class SystemHealth(TypedDict):
    """System health status"""

    status: str
    components: Dict[str, str]
    timestamp: str
    uptime: NotRequired[float]


class PerformanceMetrics(TypedDict):
    """Performance metrics structure"""

    response_time: float
    memory_usage: int
    cpu_usage: float
    cache_hit_rate: NotRequired[float]


# Generic type variables for common patterns
T = TypeVar("T")
K = TypeVar("K")  # Key type
V = TypeVar("V")  # Value type
R = TypeVar("R")  # Return type
E = TypeVar("E", bound=Exception)  # Exception type


# Protocol definitions for common interfaces
class Cacheable(Protocol):
    """Protocol for objects that can be cached"""

    def cache_key(self) -> str:
        """Return unique cache key for this object."""
        ...

    def cache_ttl(self) -> int:
        """Return cache TTL in seconds for this object."""
        ...


class Serializable(Protocol):
    """Protocol for objects that can be serialized"""

    def to_dict(self) -> Dict[str, Any]:
        """Convert object to dictionary representation."""
        ...

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Serializable":
        """Create instance from dictionary data."""
        ...


class Configurable(Protocol):
    """Protocol for configurable objects"""

    def configure(self, config: ConfigDict) -> None:
        """Apply configuration settings to this object."""
        ...

    def get_config(self) -> ConfigDict:
        """Return current configuration settings."""
        ...


class Monitorable(Protocol):
    """Protocol for objects that can be monitored"""

    def get_status(self) -> Dict[str, Any]:
        """Return current status information."""
        ...

    def get_metrics(self) -> PerformanceMetrics:
        """Return performance metrics for this object."""
        ...


# Commonly used literals
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
HTTPMethod = Literal["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]
CacheStrategy = Literal["static", "dynamic", "user_scoped", "computed", "temporary"]
AgentType = Literal["chat", "research", "development", "analysis", "automation"]
TaskStatus = Literal["pending", "running", "completed", "failed", "cancelled"]

# Final constants for configuration
DEFAULT_CACHE_TTL: Final[int] = 300  # 5 minutes
MAX_RETRY_ATTEMPTS: Final[int] = 3
DEFAULT_TIMEOUT: Final[int] = 30  # seconds
MAX_CONTENT_LENGTH: Final[int] = 10 * 1024 * 1024  # 10MB

__all__ = [
    # Basic types
    "Any",
    "Dict",
    "List",
    "Optional",
    "Union",
    "Tuple",
    "Callable",
    "TypeVar",
    "Generic",
    "Protocol",
    "Literal",
    "Final",
    "Set",
    "FrozenSet",
    "Sequence",
    "Mapping",
    "MutableMapping",
    "Iterator",
    "Iterable",
    "Generator",
    "AsyncGenerator",
    "Awaitable",
    "Coroutine",
    "ClassVar",
    "NamedTuple",
    "TypedDict",
    "NotRequired",
    "dataclass",
    "Enum",
    "IntEnum",
    "Path",
    "datetime",
    "Decimal",
    # Type aliases
    "StrDict",
    "StrList",
    "OptionalStr",
    "OptionalInt",
    "OptionalFloat",
    "OptionalBool",
    "OptionalDict",
    "OptionalList",
    "ConfigDict",
    "ConfigMapping",
    "EnvironmentDict",
    "APIResponse",
    "JSONDict",
    "ResponseData",
    "ErrorDict",
    "ResultList",
    "KeyValuePairs",
    "MetadataDict",
    "StatsDict",
    "FilePath",
    "DirectoryPath",
    "PathLike",
    "NumericValue",
    "PositiveInt",
    "NonNegativeInt",
    "Percentage",
    "TimeStamp",
    "DateTimeStr",
    "ISOTimestamp",
    "AsyncCallable",
    "SyncOrAsyncCallable",
    "AgentID",
    "TaskID",
    "WorkflowID",
    "SessionID",
    "UserID",
    "RequestID",
    "ModelName",
    "PromptText",
    "ResponseText",
    "TokenCount",
    "Temperature",
    "MaxTokens",
    "DatabaseRow",
    "QueryResult",
    "QueryParameters",
    "ConnectionString",
    "URL",
    "IPAddress",
    "Port",
    "Headers",
    "StatusCode",
    "CacheKey",
    "CacheValue",
    "TTL",
    "RedisValue",
    "ValidationError",
    "ErrorCode",
    "ErrorMessage",
    "WarningMessage",
    "WebSocketMessage",
    "EventData",
    "NotificationData",
    "Token",
    "ApiKey",
    "SecretKey",
    "Hash",
    "Salt",
    "GPUInfo",
    "SystemStats",
    "ResourceUsage",
    # TypedDict classes
    "TaskConfig",
    "CacheEntry",
    "APIEndpointInfo",
    "SystemHealth",
    "PerformanceMetrics",
    # Type variables
    "T",
    "K",
    "V",
    "R",
    "E",
    # Protocols
    "Cacheable",
    "Serializable",
    "Configurable",
    "Monitorable",
    # Literals
    "LogLevel",
    "HTTPMethod",
    "CacheStrategy",
    "AgentType",
    "TaskStatus",
    # Constants
    "DEFAULT_CACHE_TTL",
    "MAX_RETRY_ATTEMPTS",
    "DEFAULT_TIMEOUT",
    "MAX_CONTENT_LENGTH",
]
