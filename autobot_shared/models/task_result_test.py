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


def test_to_dict_omits_none_fields():
    """Keys whose value is None must not appear in the serialised dict."""
    result = TaskResult(status="success", message="ok")
    d = result.to_dict()
    assert "data" not in d
    assert "error" not in d


def test_to_dict_includes_data_when_set():
    result = TaskResult(status="success", message="ok", data={"key": "val"})
    d = result.to_dict()
    assert d["data"] == {"key": "val"}


def test_to_dict_includes_error_when_set():
    result = TaskResult(status="error", message="fail", error="stderr output")
    d = result.to_dict()
    assert d["error"] == "stderr output"


def test_to_dict_preserves_falsy_data_zero():
    """data=0 is falsy but not None — must be kept."""
    result = TaskResult(status="success", message="ok", data=0)
    d = result.to_dict()
    assert "data" in d
    assert d["data"] == 0


def test_to_dict_preserves_falsy_data_empty_string():
    result = TaskResult(status="success", message="ok", data="")
    d = result.to_dict()
    assert "data" in d
    assert d["data"] == ""


# ---------------------------------------------------------------------------
# task_success
# ---------------------------------------------------------------------------


def test_task_success_status():
    d = task_success("All good.")
    assert d["status"] == "success"


def test_task_success_message():
    d = task_success("All good.")
    assert d["message"] == "All good."


def test_task_success_no_data_by_default():
    d = task_success("ok")
    assert "data" not in d
    assert "error" not in d


def test_task_success_with_data():
    d = task_success("ok", data={"count": 3})
    assert d["data"] == {"count": 3}


def test_task_success_returns_plain_dict():
    d = task_success("ok")
    assert isinstance(d, dict)


# ---------------------------------------------------------------------------
# task_error
# ---------------------------------------------------------------------------


def test_task_error_status():
    d = task_error("Something broke.")
    assert d["status"] == "error"


def test_task_error_message():
    d = task_error("Something broke.")
    assert d["message"] == "Something broke."


def test_task_error_no_error_field_by_default():
    d = task_error("Something broke.")
    assert "error" not in d


def test_task_error_with_error_detail():
    d = task_error("Command failed.", error="permission denied")
    assert d["error"] == "permission denied"


def test_task_error_returns_plain_dict():
    d = task_error("oops")
    assert isinstance(d, dict)


# ---------------------------------------------------------------------------
# task_pending
# ---------------------------------------------------------------------------


def test_task_pending_status():
    d = task_pending()
    assert d["status"] == "pending"


def test_task_pending_default_message():
    d = task_pending()
    assert d["message"] == "Task pending approval"


def test_task_pending_custom_message():
    d = task_pending("Awaiting review")
    assert d["message"] == "Awaiting review"


def test_task_pending_no_extra_fields():
    d = task_pending()
    assert "data" not in d
    assert "error" not in d


# ---------------------------------------------------------------------------
# task_pending_approval
# ---------------------------------------------------------------------------


def test_task_pending_approval_status():
    d = task_pending_approval()
    assert d["status"] == "pending_approval"


def test_task_pending_approval_default_message():
    d = task_pending_approval()
    assert d["message"] == "Task pending approval"


def test_task_pending_approval_custom_message():
    d = task_pending_approval("Awaiting user confirmation for: rm -rf /")
    assert "rm -rf /" in d["message"]


def test_task_pending_approval_no_extra_fields():
    d = task_pending_approval()
    assert "data" not in d
    assert "error" not in d


# ---------------------------------------------------------------------------
# Mutability — callers can extend the returned dict without affecting builders
# ---------------------------------------------------------------------------


def test_returned_dict_is_mutable():
    d = task_error("Command failed.", error="stderr")
    d["output"] = "some output"
    d["returncode"] = 1
    assert d["output"] == "some output"
    assert d["returncode"] == 1
    # Second call is independent
    d2 = task_error("Command failed.", error="stderr")
    assert "output" not in d2
