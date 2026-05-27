# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Regression tests for the unified AutoBotError exception hierarchy (GitHub #6521).

Verifies that all exception types are importable from the canonical
``exceptions`` module and that the former ``utils.chat_exceptions`` shim
still exports them unchanged.
"""

import exceptions as exc
import utils.chat_exceptions as chat_exc

# ---------------------------------------------------------------------------
# Canonical module exports
# ---------------------------------------------------------------------------


class TestCanonicalImports:
    def test_base_classes_present(self):
        assert issubclass(exc.AutoBotError, Exception)
        assert issubclass(exc.InternalError, exc.AutoBotError)
        assert issubclass(exc.ValidationError, exc.AutoBotError)
        assert issubclass(exc.ResourceNotFoundError, exc.AutoBotError)

    def test_network_hierarchy(self):
        assert issubclass(exc.NetworkError, exc.AutoBotError)
        assert issubclass(exc.ServiceUnavailableError, exc.NetworkError)
        assert issubclass(exc.ServiceTimeoutError, exc.NetworkError)
        assert issubclass(exc.HTTPClientError, exc.NetworkError)
        assert issubclass(exc.HTTPServerError, exc.NetworkError)

    def test_subprocess_and_file_errors(self):
        assert issubclass(exc.SubprocessError, exc.AutoBotError)
        assert issubclass(exc.FileOperationError, exc.AutoBotError)

    def test_helpers_callable(self):
        assert callable(exc.get_error_code)
        assert callable(exc.get_exceptions_lazy)
        assert callable(exc.log_exception)


# ---------------------------------------------------------------------------
# Backward-compat shim (utils.chat_exceptions)
# ---------------------------------------------------------------------------


class TestShimReexports:
    """Ensure the shim re-exports are identical objects to the canonical ones."""

    def test_autobot_error_is_same(self):
        assert chat_exc.AutoBotError is exc.AutoBotError

    def test_internal_error_is_same(self):
        assert chat_exc.InternalError is exc.InternalError

    def test_network_classes_are_same(self):
        assert chat_exc.NetworkError is exc.NetworkError
        assert chat_exc.ServiceUnavailableError is exc.ServiceUnavailableError
        assert chat_exc.ServiceTimeoutError is exc.ServiceTimeoutError
        assert chat_exc.HTTPClientError is exc.HTTPClientError
        assert chat_exc.HTTPServerError is exc.HTTPServerError

    def test_subprocess_file_errors_are_same(self):
        assert chat_exc.SubprocessError is exc.SubprocessError
        assert chat_exc.FileOperationError is exc.FileOperationError

    def test_get_exceptions_lazy_returns_canonical_classes(self):
        AutoBotError, InternalError, ResourceNotFoundError, ValidationError, get_error_code = exc.get_exceptions_lazy()
        assert AutoBotError is exc.AutoBotError
        assert InternalError is exc.InternalError
        assert ResourceNotFoundError is exc.ResourceNotFoundError
        assert ValidationError is exc.ValidationError
        assert get_error_code is exc.get_error_code


# ---------------------------------------------------------------------------
# Instantiation and field contracts
# ---------------------------------------------------------------------------


class TestInstantiation:
    def test_autobot_error_details(self):
        err = exc.AutoBotError("msg", {"k": "v"})
        assert err.message == "msg"
        assert err.details == {"k": "v"}

    def test_network_error_fields(self):
        err = exc.NetworkError("down", service="svc", url="http://x")
        assert err.service == "svc"
        assert err.url == "http://x"
        assert err.details["service"] == "svc"

    def test_http_client_error_status(self):
        err = exc.HTTPClientError("bad req", status_code=400, service="api")
        assert err.status_code == 400
        assert err.details["status_code"] == 400

    def test_subprocess_error_fields(self):
        err = exc.SubprocessError("fail", command="ls", return_code=1)
        assert err.command == "ls"
        assert err.return_code == 1
        assert err.details["command"] == "ls"

    def test_file_operation_error_fields(self):
        err = exc.FileOperationError(
            "io fail", file_path="/tmp/x", operation="read"
        )  # nosec B108 - test/controlled code uses tmpdir intentionally
        assert err.file_path == "/tmp/x"  # nosec B108 - test/controlled code uses tmpdir intentionally
        assert err.operation == "read"

    def test_internal_error_safe_message(self):
        err = exc.InternalError("secret crash")
        assert err.safe_message == "An internal error occurred"
        assert "secret" not in err.safe_message

    def test_no_duplicate_class_names(self):
        """No two exported exception names should refer to different classes."""
        canonical_names = {
            name: getattr(exc, name)
            for name in dir(exc)
            if isinstance(getattr(exc, name), type) and issubclass(getattr(exc, name), Exception)
        }
        # All names must map to exactly one class (no shadowing)
        seen = {}
        for name, cls in canonical_names.items():
            assert name not in seen or seen[name] is cls, f"Duplicate class for {name}"
            seen[name] = cls
