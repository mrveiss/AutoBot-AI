# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Several unparsable history records yield ONE warning with the count and agent id (#21381)."""

import json
from unittest.mock import patch

from services import agent_history_records


def test_several_unparsable_records_log_exactly_one_warning_with_count_and_agent_id():
    raw = [json.dumps({"ok": 1}), "{secret-not-json", None, b"\xff\xfe", json.dumps({"ok": 2})]
    with patch.object(agent_history_records, "logger") as log:
        records = agent_history_records.parse_history_records("agent-7", raw)
    assert records == [{"ok": 1}, {"ok": 2}]
    log.warning.assert_called_once()
    template, count, agent = log.warning.call_args.args
    assert (count, agent) == (3, "agent-7")
    assert "secret" not in template % (count, agent)


def test_no_warning_when_every_record_parses():
    with patch.object(agent_history_records, "logger") as log:
        assert agent_history_records.parse_history_records("a", ["1"]) == [1]
    log.warning.assert_not_called()
