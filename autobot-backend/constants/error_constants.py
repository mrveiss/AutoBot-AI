# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Shared error message string constants for HTTP responses and logging."""

# Generic resource errors (use as: ERR_NOT_FOUND.format(resource='Workflow')}")
ERR_NOT_FOUND = "{resource} not found"

# Specific resource errors (pre-formatted for common cases)
ERR_ASSESSMENT_NOT_FOUND = "Assessment not found"
ERR_SESSION_NOT_FOUND = "Session not found"
ERR_FILE_NOT_FOUND = "File not found"
ERR_DIRECTORY_NOT_FOUND = "Directory not found"
ERR_FILE_OR_DIR_NOT_FOUND = "File or directory not found"
ERR_PATH_NOT_FOUND = "Path not found"
ERR_CONNECTOR_NOT_FOUND = "Connector not found"
ERR_JOB_NOT_FOUND = "Job not found"
ERR_TEMPLATE_NOT_FOUND = "Template not found"
ERR_WORKFLOW_NOT_FOUND = "Workflow not found"

# Auth errors
ERR_INVALID_CREDENTIALS = "Invalid username or password"
ERR_INVALID_TOKEN = "Invalid token"

# Operation errors — use as f-string prefix at call site
ERR_FAILED_TO = "Failed to {operation}"
