# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Chat Metrics Recorder

Phase 4 (#7590): SSOT observability metrics for the chat subsystem.

Exposes:
- autobot_chat_messages_sent_total: counter, event_type label
- autobot_chat_recent_cardinality: gauge (ZCARD chat:recent)
- autobot_chat_disk_file_count: gauge (nightly, pushed by check_chat_disk_files.sh)

The key invariant: every chat_send event must reference exactly one session_id.
"""

from prometheus_client import Counter, Gauge

from .base import BaseMetricsRecorder


class ChatMetricsRecorder(BaseMetricsRecorder):
    """Recorder for chat SSOT observability metrics."""

    def _init_metrics(self) -> None:
        # Counts every message persisted, broken out by event type.
        # event_type: "chat_send" (user message) | "chat_response_stored" (AI response)
        # No session_id label — would be unbounded cardinality.
        self.messages_sent_total = Counter(
            "autobot_chat_messages_sent_total",
            "Total chat messages persisted, by event type",
            ["event_type"],
            registry=self.registry,
        )

        # Current number of sessions in the chat:recent sorted set.
        # Alert when this exceeds expected_session_count * 2 (see alerts-chat-ssot.yml).
        self.recent_cardinality = Gauge(
            "autobot_chat_recent_cardinality",
            "Number of sessions in the chat:recent sorted set (ZCARD chat:recent)",
            registry=self.registry,
        )

        # Populated externally by scripts/check_chat_disk_files.sh via Pushgateway.
        # Declared here so the metric appears in /api/metrics/prometheus even before
        # the nightly job runs (value 0 until first push).
        self.disk_file_count = Gauge(
            "autobot_chat_disk_file_count",
            "Number of files in data/chats/ (sampled nightly by check_chat_disk_files.sh)",
            registry=self.registry,
        )

    def record_message_sent(self, event_type: str) -> None:
        """Increment the message counter for the given event type."""
        self.messages_sent_total.labels(event_type=event_type).inc()

    def set_recent_cardinality(self, count: int) -> None:
        """Update the chat:recent cardinality gauge."""
        self.recent_cardinality.set(count)

    def set_disk_file_count(self, count: int) -> None:
        """Update the disk file count gauge (called by Pushgateway push)."""
        self.disk_file_count.set(count)


__all__ = ["ChatMetricsRecorder"]
