# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for TaskResult dataclass and builder functions (#3545)."""

from autobot_shared.models.task_result import (
    TaskResult,
    task_error,
    task_pending,
    task_pending_approval,
    task_success,
)

# ---------------------------------------------------------------------------
# TaskResult.to_dict
# ---------------------------------------------------------------------------


def test_to_dict_omits_none_fields() -> None:
    """Keys whose value is None must not appear in the serialised dict."""
    result = TaskResult(status="success", message="ok")
    d = result.to_dict()
    assert "data" not in d
    assert "error" not in d


def test_to_dict_includes_data_when_set() -> None:
    result = TaskResult(status="success", message="ok", data={"key": "val"})
    d = result.to_dict()
    assert d["data"] == {"key": "val"}


def test_to_dict_includes_error_when_set() -> None:
    result = TaskResult(status="error", message="fail", error="stderr output")
    d = result.to_dict()
    assert d["error"] == "stderr output"


def test_to_dict_preserves_falsy_data_zero() -> None:
    """data=0 is falsy but not None — must be kept."""
    result = TaskResult(status="success", message="ok", data=0)
    d = result.to_dict()
    assert "data" in d
    assert d["data"] == 0


def test_to_dict_preserves_falsy_data_empty_string() -> None:
    result = TaskResult(status="success", message="ok", data="")
    d = result.to_dict()
    assert "data" in d
    assert d["data"] == ""


# ---------------------------------------------------------------------------
# task_success
# ---------------------------------------------------------------------------


def test_task_success_status() -> None:
    d = task_success("All good.")
    assert d["status"] == "success"


def test_task_success_message() -> None:
    d = task_success("All good.")
    assert d["message"] == "All good."


def test_task_success_no_data_by_default() -> None:
    d = task_success("ok")
    assert "data" not in d
    assert "error" not in d


def test_task_success_with_data() -> None:
    d = task_success("ok", data={"count": 3})
    assert d["data"] == {"count": 3}


def test_task_success_returns_plain_dict() -> None:
    d = task_success("ok")
    assert isinstance(d, dict)


# ---------------------------------------------------------------------------
# task_error
# ---------------------------------------------------------------------------


def test_task_error_status() -> None:
    d = task_error("Something broke.")
    assert d["status"] == "error"


def test_task_error_message() -> None:
    d = task_error("Something broke.")
    assert d["message"] == "Something broke."


def test_task_error_no_error_field_by_default() -> None:
    d = task_error("Something broke.")
    assert "error" not in d


def test_task_error_with_error_detail() -> None:
    d = task_error("Command failed.", error="permission denied")
    assert d["error"] == "permission denied"


def test_task_error_returns_plain_dict() -> None:
    d = task_error("oops")
    assert isinstance(d, dict)


# ---------------------------------------------------------------------------
# task_pending
# ---------------------------------------------------------------------------


def test_task_pending_status() -> None:
    d = task_pending()
    assert d["status"] == "pending"


def test_task_pending_default_message() -> None:
    d = task_pending()
    assert d["message"] == "Task pending approval"


def test_task_pending_custom_message() -> None:
    d = task_pending("Awaiting review")
    assert d["message"] == "Awaiting review"


def test_task_pending_no_extra_fields() -> None:
    d = task_pending()
    assert "data" not in d
    assert "error" not in d


# ---------------------------------------------------------------------------
# task_pending_approval
# ---------------------------------------------------------------------------


def test_task_pending_approval_status() -> None:
    d = task_pending_approval()
    assert d["status"] == "pending_approval"


def test_task_pending_approval_default_message() -> None:
    d = task_pending_approval()
    assert d["message"] == "Task pending approval"


def test_task_pending_approval_custom_message() -> None:
    d = task_pending_approval("Awaiting user confirmation for: rm -rf /")
    assert "rm -rf /" in d["message"]


def test_task_pending_approval_no_extra_fields() -> None:
    d = task_pending_approval()
    assert "data" not in d
    assert "error" not in d


# ---------------------------------------------------------------------------
# Mutability — callers can extend the returned dict without affecting builders
# ---------------------------------------------------------------------------


def test_returned_dict_is_mutable() -> None:
    d = task_error("Command failed.", error="stderr")
    d["output"] = "some output"
    d["returncode"] = 1
    assert d["output"] == "some output"
    assert d["returncode"] == 1
    # Second call is independent
    d2 = task_error("Command failed.", error="stderr")
    assert "output" not in d2


# ---------------------------------------------------------------------------
# extra field — issue #3564
# ---------------------------------------------------------------------------


def test_to_dict_merges_extra_keys() -> None:
    """extra keys must appear as top-level entries in the serialised dict."""
    result = TaskResult(
        status="error",
        message="fail",
        error="stderr",
        extra={"output": "stdout text", "returncode": 1},
    )
    d = result.to_dict()
    assert d["output"] == "stdout text"
    assert d["returncode"] == 1


def test_to_dict_extra_key_does_not_appear() -> None:
    """The 'extra' key itself must never be present in the output dict."""
    result = TaskResult(status="success", message="ok", extra={"foo": "bar"})
    d = result.to_dict()
    assert "extra" not in d


def test_to_dict_none_fixed_field_still_omitted_with_extra() -> None:
    """None-omission for fixed fields must still apply when extra is provided."""
    result = TaskResult(
        status="error",
        message="fail",
        extra={"returncode": 2},
    )
    d = result.to_dict()
    assert "error" not in d
    assert "data" not in d
    assert d["returncode"] == 2


def test_to_dict_empty_extra_has_no_effect() -> None:
    result = TaskResult(status="success", message="ok", extra={})
    d = result.to_dict()
    assert set(d.keys()) == {"status", "message"}


def test_task_error_with_extra() -> None:
    """task_error builder must pass extra through to the serialised dict."""
    d = task_error(
        "Command failed.",
        error="stderr",
        extra={"output": "stdout", "returncode": 1},
    )
    assert d["status"] == "error"
    assert d["error"] == "stderr"
    assert d["output"] == "stdout"
    assert d["returncode"] == 1
    assert "extra" not in d


def test_task_success_with_extra() -> None:
    d = task_success("ok", data={"count": 1}, extra={"elapsed_ms": 42})
    assert d["status"] == "success"
    assert d["data"] == {"count": 1}
    assert d["elapsed_ms"] == 42
    assert "extra" not in d


def test_task_pending_with_extra() -> None:
    d = task_pending("waiting", extra={"queue_position": 3})
    assert d["status"] == "pending"
    assert d["queue_position"] == 3
    assert "extra" not in d


def test_task_pending_approval_with_extra() -> None:
    d = task_pending_approval(extra={"approval_id": "abc"})
    assert d["status"] == "pending_approval"
    assert d["approval_id"] == "abc"
    assert "extra" not in d


def test_extra_none_is_treated_as_empty() -> None:
    """Passing extra=None must produce the same result as omitting extra."""
    d1 = task_error("fail", extra=None)
    d2 = task_error("fail")
    assert d1 == d2


def test_extra_keys_independent_across_calls() -> None:
    """extra dicts from separate calls must not share state."""
    d1 = task_error("fail", extra={"output": "a"})
    d2 = task_error("fail", extra={"output": "b"})
    assert d1["output"] == "a"
    assert d2["output"] == "b"
