# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Custom exception classes for AutoBot error handling.

Issue #655: Implements Agent Zero's RepairableException pattern that distinguishes
between soft errors (LLM can retry with different approach) and hard errors
(task must fail).
"""

from typing import Optional


class RepairableException(Exception):
    """
    Soft error that LLM can potentially fix by trying a different approach.

    When raised during tool execution, this exception is forwarded to the LLM
    as context rather than failing the task. The LLM can then attempt an
    alternative approach to accomplish the goal.

    Example usage:
        try:
            result = execute_command(cmd)
        except PermissionError:
            raise RepairableException(
                "Permission denied for command",
                suggestion="Try using sudo or a different directory"
            )
        except FileNotFoundError as e:
            raise RepairableException(
                f"File not found: {e}",
                suggestion="Create the file first or check the path"
            )

    Attributes:
        message: The error message describing what went wrong
        suggestion: Optional hint for the LLM on how to fix the issue
        original_exception: The original exception that was caught (if any)
        recoverable: Whether this error is recoverable (always True for this class)
    """

    def __init__(
        self,
        message: str,
        suggestion: Optional[str] = None,
        original_exception: Optional[Exception] = None,
    ):
        """
        Initialize RepairableException.

        Args:
            message: Description of the error
            suggestion: Hint for LLM on how to fix/retry (optional)
            original_exception: The original exception that was caught (optional)
        """
        super().__init__(message)
        self.message = message
        self.suggestion = suggestion or "Try a different approach."
        self.original_exception = original_exception
        self.recoverable = True

    def __str__(self) -> str:
        """Return formatted error message with suggestion."""
        return f"{self.message}\nSuggestion: {self.suggestion}"

    def to_llm_context(self) -> str:
        """
        Format the error as context for LLM retry.

        Returns:
            Formatted string suitable for including in LLM prompt
        """
        context = f"""**Tool Error (Recoverable):**
{self.message}

**Suggestion:** {self.suggestion}

Please try a different approach to accomplish this step."""
        return context


class CriticalException(Exception):
    """
    Hard error that cannot be recovered - task must fail.

    When raised during tool execution, the task will be terminated
    and the error reported to the user. The LLM will not be given
    an opportunity to retry.

    Use this for:
    - Security violations
    - System resource exhaustion
    - Unrecoverable system errors
    - User-requested cancellation

    Example usage:
        if not is_authorized(user, resource):
            raise CriticalException(
                "Unauthorized access attempt",
                error_code="AUTH_DENIED"
            )
    """

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        original_exception: Optional[Exception] = None,
    ):
        """
        Initialize CriticalException.

        Args:
            message: Description of the critical error
            error_code: Optional error code for categorization
            original_exception: The original exception (if wrapping another)
        """
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.original_exception = original_exception
        self.recoverable = False

    def __str__(self) -> str:
        """Return formatted error message."""
        if self.error_code:
            return f"[{self.error_code}] {self.message}"
        return self.message


# Mapping of common exceptions to repairable status and suggestions
REPAIRABLE_EXCEPTIONS = {
    FileNotFoundError: {
        "repairable": True,
        "suggestion": "Create the file first or check the path exists",
    },
    PermissionError: {
        "repairable": True,
        "suggestion": "Try using sudo or execute from a different directory",
    },
    TimeoutError: {
        "repairable": True,
        "suggestion": "Break the operation into smaller steps or increase timeout",
    },
    ConnectionError: {
        "repairable": True,
        "suggestion": "Check network connectivity and retry",
    },
    ValueError: {
        "repairable": True,
        "suggestion": "Check the input format and provide valid values",
    },
    KeyError: {
        "repairable": True,
        "suggestion": "Verify the key exists before accessing it",
    },
    # Hard failures - not repairable
    MemoryError: {
        "repairable": False,
        "suggestion": None,
    },
    SystemExit: {
        "repairable": False,
        "suggestion": None,
    },
    KeyboardInterrupt: {
        "repairable": False,
        "suggestion": None,
    },
}


def wrap_as_repairable(
    exception: Exception,
    context: Optional[str] = None,
) -> RepairableException:
    """
    Wrap a standard exception as RepairableException if appropriate.

    Args:
        exception: The exception to wrap
        context: Additional context about what operation failed

    Returns:
        RepairableException with appropriate suggestion

    Raises:
        The original exception if it's not repairable (hard failure)
    """
    exc_type = type(exception)

    # Check if this exception type is in our mapping
    if exc_type in REPAIRABLE_EXCEPTIONS:
        mapping = REPAIRABLE_EXCEPTIONS[exc_type]
        if mapping["repairable"]:
            message = f"{context}: {exception}" if context else str(exception)
            return RepairableException(
                message=message,
                suggestion=mapping["suggestion"],
                original_exception=exception,
            )
        else:
            # Hard failure - re-raise original
            raise exception

    # Default: wrap as repairable with generic suggestion
    message = f"{context}: {exception}" if context else str(exception)
    return RepairableException(
        message=message,
        suggestion="Try a different approach or check the error details",
        original_exception=exception,
    )


def is_repairable(exception: Exception) -> bool:
    """
    Check if an exception is repairable (LLM can retry).

    Args:
        exception: The exception to check

    Returns:
        True if the exception is repairable, False otherwise
    """
    if isinstance(exception, RepairableException):
        return True
    if isinstance(exception, CriticalException):
        return False

    exc_type = type(exception)
    if exc_type in REPAIRABLE_EXCEPTIONS:
        return REPAIRABLE_EXCEPTIONS[exc_type]["repairable"]

    # Default: consider repairable (let LLM try)
    return True
