# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
"""#17855: `CommonUtils.load_config` delegates to the shared loader without changing its output.

`_old_load_config` is the pre-delegation body verbatim; every input below must give the same
result through both. The one recorded exception is a JSON file that is valid but not an object.
"""

import json
from pathlib import Path

import pytest

from autobot_shared.config_file_loading import format_key_value, parse_key_value
from utils.common import CommonUtils


def _old_load_config(config_path, default=None):
    if default is None:
        default = {}
    config_path = Path(config_path)
    if not config_path.exists():
        return default.copy()
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            if config_path.suffix.lower() == ".json":
                return json.load(f)
            config = {}
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                config[key.strip()] = value.strip()
            return config
    except Exception:
        return default.copy()


_CASES = [
    ("a.json", '{"a": 1, "b": {"c": [1, 2]}}'),
    ("empty.json", "{}"),
    ("broken.json", "{not json"),
    ("a.cfg", "# comment\nKEY = value\n\nURL=http://x/?a=b\nno equals here\n  spaced  =  v  \n"),
    ("empty.cfg", ""),
    ("only_comments.env", "# a\n# b\n"),
    ("upper.JSON", '{"k": "v"}'),
]


@pytest.mark.parametrize(("name", "body"), _CASES)
@pytest.mark.parametrize("default", [None, {"d": 1}])
def test_output_is_identical_to_the_pre_delegation_loader(tmp_path, name, body, default):
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    assert CommonUtils.load_config(path, default) == _old_load_config(path, default)


@pytest.mark.parametrize("default", [None, {"d": 1}])
def test_a_missing_file_returns_a_copy_of_the_default(tmp_path, default):
    got = CommonUtils.load_config(tmp_path / "gone.json", default)
    assert got == _old_load_config(tmp_path / "gone.json", default)
    if default is not None:
        assert got == default and got is not default


def test_a_directory_falls_back_to_the_default(tmp_path):
    assert CommonUtils.load_config(tmp_path, {"d": 1}) == _old_load_config(tmp_path, {"d": 1}) == {"d": 1}


def test_a_non_object_json_file_now_yields_the_default_not_a_list(tmp_path):
    """Recorded delta: the old loader returned the raw list, which every caller then `.get()`s."""
    path = tmp_path / "list.json"
    path.write_text("[1, 2]", encoding="utf-8")
    assert _old_load_config(path, {"d": 1}) == [1, 2]
    assert CommonUtils.load_config(path, {"d": 1}) == {"d": 1}


def test_save_then_load_round_trips_key_value_through_one_format_definition(tmp_path):
    values = {"A": "1", "B": "two words"}
    assert parse_key_value(format_key_value(values).splitlines()) == values
    path = tmp_path / "out.cfg"
    assert CommonUtils.save_config(values, path) is True
    assert path.read_text(encoding="utf-8") == format_key_value(values)
    assert CommonUtils.load_config(path) == values
