# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
"""Unit tests for RunCommandExtractor (MVA-1431)."""

import pytest

from agent_loop.extractors.run_command import RunCommandExtractor


@pytest.fixture
def extractor():
    return RunCommandExtractor()


class TestExitCode:
    def test_exit_code_zero(self, extractor):
        result = extractor.extract({"command": "git status", "exit_code": 0, "stdout": ""})
        assert ("run_command:exit_code/git", 0, 1.0) in result

    def test_exit_code_nonzero(self, extractor):
        result = extractor.extract({"command": "npm install", "exit_code": 1, "stdout": ""})
        assert ("run_command:exit_code/npm", 1, 1.0) in result

    def test_returncode_fallback(self, extractor):
        result = extractor.extract({"command": "python3 app.py", "returncode": 0, "stdout": ""})
        assert ("run_command:exit_code/python", 0, 1.0) in result

    def test_generic_cmd_class(self, extractor):
        result = extractor.extract({"command": "curl http://localhost", "exit_code": 0, "stdout": ""})
        assert ("run_command:exit_code/generic", 0, 1.0) in result


class TestSinglePort:
    def test_single_port_listen(self, extractor):
        stdout = "tcp  0  0  0.0.0.0:8080  0.0.0.0:*  LISTEN"
        result = extractor.extract({"command": "ss -tlnp", "exit_code": 0, "stdout": stdout})
        keys = [r[0] for r in result]
        assert "run_command:port/listen/8080" in keys

    def test_single_port_value_preserved(self, extractor):
        stdout = "server listening on :3000\n"
        result = extractor.extract({"command": "node server.js", "exit_code": 0, "stdout": stdout})
        port_assertions = [r for r in result if r[0].startswith("run_command:port/")]
        assert len(port_assertions) == 1
        assert port_assertions[0][1] == 3000
        assert port_assertions[0][2] == 0.9


class TestMultiPort:
    def test_multi_port_no_key_collision(self, extractor):
        """Multiple ports from one command must produce distinct keys (MVA-1431)."""
        stdout = (
            "COMMAND   PID USER   FD   TYPE\n"
            "node     1234 user   10u  IPv4  *:3000 (LISTEN)\n"
            "node     1234 user   11u  IPv4  *:3001 (LISTEN)\n"
            "python   5678 user   12u  IPv4  *:8080 (LISTEN)\n"
        )
        result = extractor.extract({"command": "lsof -i -P -n", "exit_code": 0, "stdout": stdout})
        port_keys = [r[0] for r in result if r[0].startswith("run_command:port/")]
        # All three ports must produce distinct keys
        assert len(port_keys) == len(set(port_keys)), "Key collision detected — duplicate keys present"
        assert "run_command:port/listen/3000" in port_keys
        assert "run_command:port/listen/3001" in port_keys
        assert "run_command:port/listen/8080" in port_keys

    def test_multi_port_no_duplicate_ports(self, extractor):
        """Same port seen twice in stdout must appear only once."""
        stdout = ":8080 (LISTEN)\n:8080 (LISTEN)\n"
        result = extractor.extract({"command": "lsof -i", "exit_code": 0, "stdout": stdout})
        port_keys = [r[0] for r in result if r[0].startswith("run_command:port/")]
        assert port_keys.count("run_command:port/listen/8080") == 1

    def test_multi_port_confidence(self, extractor):
        stdout = ":3000 \n:4000 \n"
        result = extractor.extract({"command": "ss -tlnp", "exit_code": 0, "stdout": stdout})
        for r in result:
            if r[0].startswith("run_command:port/"):
                assert r[2] == 0.9


class TestEdgeCases:
    def test_non_dict_returns_empty(self, extractor):
        assert extractor.extract("not a dict") == []
        assert extractor.extract(None) == []
        assert extractor.extract([]) == []

    def test_no_stdout_no_ports(self, extractor):
        result = extractor.extract({"command": "git status", "exit_code": 0})
        port_assertions = [r for r in result if r[0].startswith("run_command:port/")]
        assert port_assertions == []

    def test_out_of_range_port_ignored(self, extractor):
        stdout = ":99999 \n"
        result = extractor.extract({"command": "ss", "exit_code": 0, "stdout": stdout})
        port_assertions = [r for r in result if r[0].startswith("run_command:port/")]
        assert port_assertions == []

    def test_stdout_alias(self, extractor):
        result = extractor.extract({"command": "lsof -i", "exit_code": 0, "output": ":5000 \n"})
        keys = [r[0] for r in result]
        assert "run_command:port/listen/5000" in keys

    def test_cmd_alias(self, extractor):
        result = extractor.extract({"cmd": "docker ps", "exit_code": 0, "stdout": ""})
        keys = [r[0] for r in result]
        assert "run_command:exit_code/docker" in keys
