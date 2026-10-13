# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
"""Pins ``load_config_file`` behaviour that per-caller copies lacked (#17855)."""

import json

from autobot_shared.config_file_loading import SOURCE_BUILTIN_DEFAULTS, SOURCE_FILE, load_config_file


def test_a_miss_never_writes_and_says_so(tmp_path):
    target = tmp_path / "sub" / "cfg.yaml"
    loaded = load_config_file(target, lambda: {"a": 1}, "Test")
    assert loaded.source == SOURCE_BUILTIN_DEFAULTS and not loaded.loaded_from_file
    assert not target.parent.exists()


def test_a_loaded_file_is_distinguishable_from_defaults(tmp_path):
    f = tmp_path / "cfg.yaml"
    f.write_text("a: 2\n", encoding="utf-8")
    loaded = load_config_file(f, lambda: {"a": 1}, "Test")
    assert (loaded.source, loaded.values) == (SOURCE_FILE, {"a": 2})


def test_an_empty_or_non_mapping_file_is_defaults_not_an_empty_policy(tmp_path):
    f = tmp_path / "cfg.yaml"
    for body in ("", "# only a comment\n", "- a\n- b\n"):
        f.write_text(body, encoding="utf-8")
        assert load_config_file(f, lambda: {"a": 1}, "Test").values == {"a": 1}


def test_json_parser_reads_json_and_falls_back_on_a_syntax_error(tmp_path):
    f = tmp_path / "cfg.json"
    f.write_text(json.dumps({"k": 1}), encoding="utf-8")
    assert load_config_file(f, dict, "Test", parser=json.load).values == {"k": 1}
    f.write_text("{not json", encoding="utf-8")
    loaded = load_config_file(f, lambda: {"safe": True}, "Test", parser=json.load)
    assert (loaded.source, loaded.values) == (SOURCE_BUILTIN_DEFAULTS, {"safe": True})


def test_key_value_parser_skips_comments_and_non_assignments_and_splits_once():
    from autobot_shared.config_file_loading import format_key_value, parse_key_value

    lines = ["# c\n", "\n", "A = 1\n", "junk\n", "U=x=y\n"]
    assert parse_key_value(lines) == {"A": "1", "U": "x=y"}
    assert format_key_value({"A": "1", "U": "x=y"}) == "A=1\nU=x=y\n"
