# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Centralized Logging Manager for AutoBot
Standardizes logging configuration across all components
"""

import logging
import logging.handlers
import os
import sys
import threading
import time
from collections import OrderedDict
from pathlib import Path, PurePath
from typing import TYPE_CHECKING, Any, Dict

from autobot_shared.env_utils import env_flag, env_float, env_int_clamped
from autobot_shared.stream_logging import build_stderr_handler, build_stdout_handler

if TYPE_CHECKING:
    from config.manager import ConfigManager

# Module-level logger for logging_manager itself
_logger = logging.getLogger(__name__)

# Issue #380: Module-level tuple for log types
_LOG_TYPES = ("backend", "frontend", "llm", "debug", "audit")

# Documented defaults for every config value the get_logger path reads. A value of the wrong type
# falls back to these instead of raising at import time (#19288).
_DEFAULT_MAX_BYTES = 10485760  # 10MB
_DEFAULT_BACKUP_COUNT = 5
_DEFAULT_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
_DEFAULT_LOG_LEVEL = "INFO"

# Log-flood suppression (#15774). A hot failure path -- a retry loop against a
# dependency that is down -- logs once per attempt with no ceiling, so a
# recoverable outage fills the disk and takes every other service on the node
# with it. Bound how much one repeating call site can emit per window.
# ssot-config-exempt: pre-init logging -- this module must not import config
# (see _get_config_manager), so the knobs are env-var-backed module constants.
_FLOOD_ENABLED = env_flag("AUTOBOT_LOG_FLOOD_ENABLED", default=True)
_FLOOD_THRESHOLD = env_int_clamped("AUTOBOT_LOG_FLOOD_THRESHOLD", 5, min_v=1)
_FLOOD_WINDOW_SECONDS = env_float("AUTOBOT_LOG_FLOOD_WINDOW_SECONDS", 60.0)
_FLOOD_MAX_KEYS = env_int_clamped("AUTOBOT_LOG_FLOOD_MAX_KEYS", 2048, min_v=1)


class LogFloodSuppressionFilter(logging.Filter):
    """Cap the records one repeating log site emits per window (#15774).

    Applied to WARNING and ERROR only: DEBUG/INFO are already rate-limited by
    the level itself, and CRITICAL is never suppressed -- losing the one line
    that explains an outage is worse than the disk cost of printing it.

    A record carrying ``extra={"flood_exempt": True}`` is never suppressed
    either. That escape hatch exists because of a defect found in review of
    #15777: an audit line for a destructive operation is emitted from ONE call
    site with ONE template, so every delete -- different path, different actor
    -- collapsed to a single key and the sixth in a window was dropped. The
    alternative fix, keying on the interpolated message, was rejected: a retry
    loop logging ``"redis down: attempt %s"`` is the exact shape this guard
    exists to collapse, and keying on the formatted string would mint a fresh
    key per attempt and suppress nothing. The distinction that matters is not
    how varied the text is, it is whether losing a line is acceptable -- and
    for an audit record it never is.

    The suppression key is the message *template* plus the call site, never the
    formatted message, so ``logger.error("redis down: %s", attempt)`` collapses
    to one key instead of minting a new one per attempt.
    """

    def __init__(
        self,
        threshold: int = _FLOOD_THRESHOLD,
        window_seconds: float = _FLOOD_WINDOW_SECONDS,
        max_keys: int = _FLOOD_MAX_KEYS,
    ) -> None:
        super().__init__()
        self._threshold = max(1, threshold)
        self._window = window_seconds
        self._max_keys = max(1, max_keys)
        # key -> [window_start, seen_in_window, emitted_in_window]
        self._state: "OrderedDict[tuple[object, ...], list[Any]]" = OrderedDict()
        self._lock = threading.Lock()

    @staticmethod
    def _key(record: logging.LogRecord) -> tuple[object, ...]:
        return (record.name, record.levelno, str(record.msg), record.pathname, record.lineno)

    def _evict(self) -> None:
        """Bound the state map so the guard cannot itself leak memory."""
        while len(self._state) > self._max_keys:
            self._state.popitem(last=False)

    @staticmethod
    def _annotate(record: logging.LogRecord, suppressed: int) -> None:
        """Carry the suppressed count on the first record of the next window."""
        record.flood_suppressed = suppressed
        if isinstance(record.msg, str):
            record.msg = f"{record.msg} [log-flood guard: {suppressed} identical records suppressed]"

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno >= logging.CRITICAL or record.levelno < logging.WARNING:
            return True
        if getattr(record, "flood_exempt", False):
            return True

        now = time.monotonic()
        key = self._key(record)
        with self._lock:
            entry = self._state.get(key)
            if entry is None or (now - entry[0]) >= self._window:
                suppressed = 0 if entry is None else entry[1] - entry[2]
                self._state[key] = [now, 1, 1]
                self._state.move_to_end(key)
                self._evict()
                if suppressed > 0:
                    self._annotate(record, suppressed)
                return True

            entry[1] += 1
            # Refresh recency, or _evict is insertion-order rather than
            # least-recent: an actively noisy key would be evicted ahead of an
            # idle one and immediately granted a fresh threshold allowance,
            # which is the flood the guard exists to stop.
            self._state.move_to_end(key)
            if entry[2] < self._threshold:
                entry[2] += 1
                return True
            return False


_flood_filter: LogFloodSuppressionFilter | None = LogFloodSuppressionFilter() if _FLOOD_ENABLED else None


def get_flood_filter() -> LogFloodSuppressionFilter | None:
    """The process-wide flood guard, or ``None`` when disabled by env."""
    return _flood_filter


def _get_config_manager() -> "ConfigManager":
    """Return the config_manager singleton via a lazy import.

    Imported here (not at module level) to break the circular import chain:
    logging_manager -> config -> manager -> loader -> model_constants -> (back).
    Ref: issue #1862.
    """
    try:
        from config import (  # type: ignore[attr-defined]  # GH#7105: local backend import  # noqa: PLC0415
            config_manager as _cm,
        )
    except ImportError:
        # Some backends (e.g. autobot-slm-backend) don't expose `config_manager`
        # on their local `config` module. Logging is foundational infra imported
        # at startup — it must NOT crash the app. Fall back to a stub whose
        # .get(key, default) returns the caller's default, so file-handler/format
        # setup uses the built-in defaults instead of raising ImportError (#11283).
        return _ConfigManagerFallback()

    return _cm


class _ConfigManagerFallback:
    """Config-manager stub for backends whose `config` module has no config_manager.

    Every logging call site passes a default (or handles ``None``), so returning
    the default keeps logging working without the real config manager (#11283).
    """

    @staticmethod
    def get(key: str, default: object = None) -> object:
        return default

    @staticmethod
    def get_nested(path: str, default: object = None) -> object:
        """Dotted-path reads fall back too (#15575).

        Every read in this module moved from ``get`` to ``get_nested`` because
        the real ConfigManager's ``get`` is a FLAT lookup and silently missed
        every dotted key. This stub must grow the same accessor or the backends
        that rely on it -- autobot-slm-backend among them -- raise AttributeError
        at import, which is precisely the "logging must not crash the app"
        failure #11283 added this class to prevent.
        """
        return default


_warned_config_keys: set[str] = set()


def _warn_config_fallback(key: str, value: object, default: object) -> None:
    """Say once per key, on stderr, that *key* held an unusable value (#19288).

    Written straight to stderr, never through a logger: this runs while a logger is being built,
    so logging here would re-enter get_logger. Only the value's type is shown, never the value.
    """
    if key in _warned_config_keys:
        return
    _warned_config_keys.add(key)
    sys.stderr.write(
        f"autobot logging: config {key!r} is a {type(value).__name__}, not usable; using default {default!r}\n"
    )


def _warn_file_logging_off(path: Path, exc: OSError) -> None:
    """Say once per path, on stderr, that file logging to *path* is off and why (#19628).

    Straight to stderr for the same reason as ``_warn_config_fallback``: a logger is being built.
    """
    key = f"file:{path}"
    if key in _warned_config_keys:
        return
    _warned_config_keys.add(key)
    sys.stderr.write(f"autobot logging: cannot write logs at {str(path)!r} ({exc.strerror}); logging to console only\n")


def _config_non_negative_int(key: str, default: int) -> int:
    """Read *key* as a non-negative int; bool, MagicMock or anything else yields *default*."""
    value = _get_config_manager().get_nested(key, default)
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    _warn_config_fallback(key, value, default)
    return default


def _as_str_path(value: object) -> str | None:
    """*value* as a str path when it is a str or a ``PurePath``, else None.

    Not the general ``os.PathLike`` protocol: a MagicMock implements ``__fspath__`` and returns a
    str built from its own name, so a protocol check accepts it and the handler then creates a
    ``MagicMock/...`` directory in the working tree. A config manager yields a str (YAML, env) or a
    ``Path`` (Python defaults), which is everything this accepts.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, PurePath):
        return str(value)
    return None


def _configured_log_file(log_type: str) -> str | None:
    """The configured log file for *log_type*, or None when unset or unusable (warned once)."""
    key = f"logging.file_handlers.{log_type}"
    value = _get_config_manager().get_nested(key)
    if value is None or (isinstance(value, str) and not value):
        return None
    path = _as_str_path(value)
    if path is None or "\x00" in path:
        # A NUL byte makes every filesystem call on the path raise ValueError (#19288).
        _warn_config_fallback(key, value, None)
        return None
    return path


def _log_file_path(log_type: str) -> str:
    """The configured log file for *log_type*, else ``$AUTOBOT_LOGS_DIR/<log_type>.log``."""
    configured = _configured_log_file(log_type)
    if configured is not None:
        return configured
    logs_dir = os.getenv("AUTOBOT_LOGS_DIR", "logs")
    return f"{logs_dir}/{log_type}.log"


def _known_level(value: object) -> int | None:
    """*value* as a level number when ``logging`` knows it: a name ("debug", "WARNING") or a number (10, 30).

    ``getLevelName`` maps a known name to its number, a known number to its name, and anything else
    to a "Level ..." str, which is what tells known from unknown here. Not getLevelNamesMapping():
    it is 3.11+, and the pre-commit hooks import this module on older Pythons. bool is refused.
    """
    if isinstance(value, str):
        level = logging.getLevelName(value.upper())
        return level if isinstance(level, int) else None
    if isinstance(value, int) and not isinstance(value, bool):
        name = logging.getLevelName(value)
        return value if not name.startswith("Level ") else None
    return None


def _config_log_level() -> int:
    """The configured ``logging.log_level`` as a level number; anything ``logging`` does not know yields INFO.

    Issue #15575: the config tree publishes "logging.log_level" (config/defaults.py, validated by
    config/validation.py, mapped from AUTOBOT_LOG_LEVEL); there has never been a "logging.level" key.
    """
    key = "logging.log_level"
    value = _get_config_manager().get_nested(key, _DEFAULT_LOG_LEVEL)
    level = _known_level(value)
    if level is not None:
        return level
    _warn_config_fallback(key, value, _DEFAULT_LOG_LEVEL)
    return logging.INFO


class LoggingManager:
    """
    Centralized logging manager that standardizes logging across all components
    """

    _initialized = False
    # Set when the logs directory cannot be created (#19628): loggers get console handlers only.
    _file_logging_disabled = False
    _loggers: Dict[str, logging.Logger] = {}
    # One rotating handler per log file per process (#20139), keyed by absolute path. Handlers on one
    # file that do not share a lock each see the file over the cap after another has renamed it, and
    # rotate again: one rotation shifts the backups once per handler. Guarded by ``_lock``.
    _file_handlers: Dict[str, logging.Handler] = {}
    # Set by set_level(): wins over the configured level for every logger, existing and future.
    _level_override: int | None = None
    # Re-entrant: get_logger() holds this lock while the lazy config-manager
    # import chain it triggers (config -> network_constants -> redis -> metrics
    # -> monitoring) calls get_logger() again on the same thread. A plain Lock
    # self-deadlocks there (#10632); RLock lets the same thread re-acquire.
    _lock = threading.RLock()

    @classmethod
    def get_logger(cls, name: str, log_type: str = "backend") -> logging.Logger:
        """
        Get a configured logger instance (thread-safe)

        Args:
            name: Logger name (usually __name__)
            log_type: Type of log (backend, frontend, llm, debug, audit)

        Returns:
            Configured logger instance
        """
        logger_key = f"{log_type}:{name}"

        # Fast path: check cache without lock
        with cls._lock:
            if logger_key in cls._loggers:
                return cls._loggers[logger_key]

            # Initialize if needed
            if not cls._initialized:
                cls._setup_logging_internal()

        # Create and configure logger under lock
        with cls._lock:
            # Double-check after acquiring lock
            if logger_key in cls._loggers:
                return cls._loggers[logger_key]

            logger = logging.getLogger(name)

            # Don't add handlers if already configured
            if not logger.handlers:
                handler = cls._get_file_handler(log_type)
                if handler:
                    logger.addHandler(handler)

                # Console handler is intentionally unconditional (#12506).
                # This used to be gated on `_get_config_manager().get_nested(
                # "deployment.mode", "local") == "local"`, i.e. "console
                # handler = local dev only". That gate was a no-op in every
                # environment: `ConfigManager.get()` does a flat dict lookup
                # (no dotted-key traversal), no config source ever sets a
                # literal top-level `"deployment.mode"` key, and the real
                # env var (`AUTOBOT_DEPLOYMENT_MODE`, see
                # `autobot_shared.ssot_config.config.deployment_mode`) was
                # never wired into it — so the lookup always fell through to
                # the `"local"` default and the console handler was already
                # unconditional before this change.
                # Per #12488, that's the behavior we want everywhere: systemd
                # captures each service's stdout/stderr into its log files
                # (StandardOutput=append:/StandardError=append:), so the
                # console handler is production infra, not a dev-only extra.
                # `build_stdout_handler`/`build_stderr_handler` split by
                # level (DEBUG/INFO->stdout, WARNING+->stderr) instead of a
                # single bare stderr StreamHandler().
                formatter = cls._get_formatter()
                logger.addHandler(build_stdout_handler(formatter))
                logger.addHandler(build_stderr_handler(formatter))

            log_level = _config_log_level()
            logger.setLevel(cls._level_override if cls._level_override is not None else log_level)

            # Flood guard (#15774): attached to the logger, not the handlers,
            # so one filter covers the file, stdout and stderr handlers at once.
            if _flood_filter is not None and not getattr(logger, "_autobot_flood_guarded", False):
                logger.addFilter(_flood_filter)
                logger._autobot_flood_guarded = True  # type: ignore[attr-defined]

            cls._loggers[logger_key] = logger
            return logger

    @classmethod
    def set_level(cls, level: int) -> None:
        """Run every logger this manager has made, and every one it makes later, at *level* (e.g. a CLI --verbose)."""
        with cls._lock:
            cls._level_override = level
            for logger in cls._loggers.values():
                logger.setLevel(level)

    @classmethod
    def _setup_logging_internal(cls) -> None:
        """Setup basic logging configuration (internal, called under lock).

        A logs directory that cannot be created (a ``ProtectSystem=strict`` unit whose working
        directory is read-only, #19628) turns file logging off with one stderr warning: every logger
        still gets its console handlers, which journald captures, instead of the import that asked
        for a logger raising.
        """
        logs_dir = Path(os.getenv("AUTOBOT_LOGS_DIR", "logs"))
        backup_dir_name = os.getenv("AUTOBOT_LOGS_BACKUP_DIR", "backup")  # ssot-config-exempt: pre-init logging
        try:
            logs_dir.mkdir(exist_ok=True)
            (logs_dir / backup_dir_name).mkdir(exist_ok=True)
        except OSError as exc:
            cls._file_logging_disabled = True
            _warn_file_logging_off(logs_dir, exc)

        cls._initialized = True

    @classmethod
    def _setup_logging(cls) -> None:
        """Setup basic logging configuration (thread-safe public method)"""
        with cls._lock:
            if not cls._initialized:
                cls._setup_logging_internal()

    @classmethod
    def _get_file_handler(cls, log_type: str) -> logging.Handler | None:
        """Get the rotating file handler for *log_type*; loggers writing to one file share it (#20139).

        Every config value is validated first (#19288): a wrong-typed value -- a malformed config,
        or the MagicMock a config-mocking test harness returns -- falls back to its default with one
        stderr warning instead of raising here, at the import of whichever module asked for a logger.
        """
        # No _file_logging_disabled short-cut here: a log file configured outside the logs dir may
        # still be writable, and a failing one is caught per file below (#19628 review).
        log_file = _log_file_path(log_type)

        # Use rotating file handler to prevent large log files
        max_bytes = _config_non_negative_int("logging.rotation.max_bytes", _DEFAULT_MAX_BYTES)
        backup_count = _config_non_negative_int("logging.rotation.backup_count", _DEFAULT_BACKUP_COUNT)

        key = os.path.abspath(log_file)
        if key in cls._file_handlers:
            return cls._file_handlers[key]
        try:
            Path(log_file).parent.mkdir(parents=True, exist_ok=True)
            handler = logging.handlers.RotatingFileHandler(log_file, maxBytes=max_bytes, backupCount=backup_count)
        except OSError as exc:
            _warn_file_logging_off(Path(log_file), exc)
            return None
        handler.setFormatter(cls._get_formatter())
        cls._file_handlers[key] = handler
        return handler

    @classmethod
    def _get_formatter(cls) -> logging.Formatter:
        """Get the log formatter; a non-str or invalid ``logging.format`` yields the default (#19288)."""
        key = "logging.format"
        log_format = _get_config_manager().get_nested(key, _DEFAULT_FORMAT)
        if isinstance(log_format, str):
            try:
                formatter = logging.Formatter(log_format)
                # Probe one record: a template naming a field a LogRecord lacks constructs fine
                # and then fails on every record it formats (#19288).
                formatter.format(logging.makeLogRecord({"msg": "probe"}))
                return formatter
            except (ValueError, KeyError, TypeError):
                pass  # an unusable %-style template; reported below and replaced by the default
        _warn_config_fallback(key, log_format, _DEFAULT_FORMAT)
        return logging.Formatter(_DEFAULT_FORMAT)

    @classmethod
    def setup_component_logging(cls, component_name: str, log_type: str = "backend") -> logging.Logger:
        """
        Setup logging for a specific component

        Args:
            component_name: Name of the component
            log_type: Type of logging (backend, frontend, llm, etc.)

        Returns:
            Configured logger
        """
        return cls.get_logger(component_name, log_type)

    @classmethod
    def rotate_logs(cls, log_type: str | None = None) -> None:
        """
        Manually rotate log files

        Args:
            log_type: Specific log type to rotate, or None for all
        """
        if cls._file_logging_disabled:
            return  # no logs dir and no backup dir to rotate into (#19628)
        # Issue #380: Use module-level constant
        log_types_to_rotate = list(_LOG_TYPES) if not log_type else [log_type]

        for lt in log_types_to_rotate:
            log_file = _configured_log_file(lt)
            if log_file and os.path.exists(log_file):
                # Create backup using environment-configurable paths
                logs_dir = os.getenv("AUTOBOT_LOGS_DIR", "logs")
                backup_dir = os.getenv("AUTOBOT_LOGS_BACKUP_DIR", "backup")
                backup_path = f"{logs_dir}/{backup_dir}/{lt}_{int(__import__('time').time())}.log"
                try:
                    os.rename(log_file, backup_path)
                    _logger.info("Rotated %s to %s", log_file, backup_path)
                except OSError as e:
                    _logger.error("Failed to rotate %s: %s", log_file, e)


# Convenience functions for common logging patterns
def get_logger(name: str, category: str = "backend") -> logging.Logger:
    """
    Get a logger instance - REUSABLE general-purpose logger function.

    This is the canonical way to get loggers across the codebase.
    Use specific functions below for clarity, or call this directly.

    Args:
        name: Logger name (usually __name__)
        category: Logger category (backend, frontend, llm, debug, audit)

    Returns:
        Configured logger instance

    Examples:
        >>> logger = get_logger(__name__)  # Default: backend
        >>> logger = get_logger(__name__, "llm")  # LLM logger
        >>> logger = get_logger(__name__, "debug")  # Debug logger
    """
    return LoggingManager.get_logger(name, category)


def get_backend_logger(name: str) -> logging.Logger:
    """Get backend logger"""
    return get_logger(name, "backend")


def get_frontend_logger(name: str) -> logging.Logger:
    """Get frontend logger"""
    return get_logger(name, "frontend")


def get_llm_logger(name: str) -> logging.Logger:
    """Get LLM logger"""
    return get_logger(name, "llm")


def get_debug_logger(name: str) -> logging.Logger:
    """Get debug logger"""
    return get_logger(name, "debug")


def get_audit_channel_logger(name: str) -> logging.Logger:
    """Get the stdlib logger of the ``audit`` log channel.

    This is a log channel only: it writes no audit record. Audit records go
    through ``services.audit.audit.record`` (#17312).
    """
    return get_logger(name, "audit")


# Maintain backward compatibility with existing logging setup
def setup_logging() -> None:
    """Setup logging - backward compatibility function"""
    LoggingManager._setup_logging()
