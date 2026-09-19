# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Test for log_aggregator's generated rotation script (#15585 sweep finding).

``setup_centralized_logging`` built ``rotate_logs.sh`` from a triple-quoted
string containing ``{self.logs_dir}`` / ``{self.archive_dir}`` with no ``f``
prefix, so the generated script declared ``LOGS_DIR="{self.logs_dir}"``
literally -- a bash script that could never resolve either directory. The
literal ``{}``/``\\;`` already double-braced elsewhere in the same string
(for the `find -exec` clause) is evidence an ``f`` prefix was always the
intent. This asserts the written script contains the real paths and no
leftover ``{identifier`` placeholder shape.
"""

import re
import sys
from pathlib import Path

# Lives here, not beside the script it tests -- see microservice_architecture_evaluator_test.py
# in this same directory for the ci.yml path-list reasoning (#14563, #14518).
_SCRIPTS_ROOT = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from log_aggregator import LogAggregator  # noqa: E402

_LEFTOVER_PLACEHOLDER_RE = re.compile(r"\{[A-Za-z_]")


def test_rotation_script_renders_real_paths_not_placeholders(tmp_path: Path):
    (tmp_path / "scripts").mkdir()  # setup_centralized_logging assumes it, same as the real repo layout

    aggregator = object.__new__(LogAggregator)
    aggregator.project_root = tmp_path
    aggregator.logs_dir = tmp_path / "logs"
    aggregator.archive_dir = tmp_path / "logs" / "archive"

    aggregator.setup_centralized_logging()

    rotation_script = tmp_path / "scripts" / "rotate_logs.sh"
    content = rotation_script.read_text(encoding="utf-8")

    assert not _LEFTOVER_PLACEHOLDER_RE.search(content), (
        "rotate_logs.sh contains an un-substituted {identifier} placeholder -- "
        "a triple-quoted string is missing its f prefix"
    )
    assert f'LOGS_DIR="{tmp_path / "logs"}"' in content
    assert f'ARCHIVE_DIR="{tmp_path / "logs" / "archive"}"' in content
    # The find -exec clause's literal {} must survive as literal bash, not be
    # swallowed as an (empty, invalid) f-string expression.
    assert 'find "$LOGS_DIR" -name "*.log" -size +10M -exec gzip {} \\;' in content
