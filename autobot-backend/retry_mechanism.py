#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Retry mechanism with exponential backoff for AutoBot

MIGRATION (MVA-1493): Implementation moved to autobot_shared.retry_mechanism.
This module re-exports everything for backward compatibility.
"""

from autobot_shared.retry_mechanism import (  # noqa: F401
    BackoffStrategy,
    RetryConfig,
    RetryExhaustedError,
    RetryMechanism,
    RetryStrategy,
    get_default_retry_mechanism,
    retry_async,
    retry_database_operation,
    retry_file_operation,
    retry_network_operation,
    retry_sync,
    with_retry,
)
