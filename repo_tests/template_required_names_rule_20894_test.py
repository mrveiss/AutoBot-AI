# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The rule that decides which template variables are required, with a contrast pair per shape (#20894)."""

from __future__ import annotations

import pytest
from repo_tests._template_required_names import required_names


@pytest.mark.parametrize(
    ("text", "required"),
    [
        ("{{ x }}", {"x"}),
        ("{{ x | default('a') }}", set()),
        ("{% if x is defined %}{{ x }}{% endif %}", set()),
        ("{% if x | default('') | length > 0 %}A={{ x }}{% endif %}", set()),
        ("{{ x.stat.exists | default(false) }}", set()),
        ("{{ x['k'] | default(1) }}", set()),
        ("{% if x is defined %}{% else %}{{ x }}{% endif %}", {"x"}),  # the else branch is not established
        ("{% if x is defined %}{{ x }}{% endif %}{{ x }}", {"x"}),  # one guarded read, one unguarded read
        ("{{ x | default(1) }}{{ x }}", {"x"}),
        ("{% if y %}{{ x }}{% endif %}", {"x", "y"}),  # an if on another name establishes nothing
        ("{% if x is defined %}{{ x }}{% elif y | default('') %}{{ y }}{% endif %}", set()),
        ("{% for i in items %}{{ i }}{% endfor %}", {"items"}),
        # polarity: the body of `is not defined` reads the name exactly when it is undefined
        ("{% if x is not defined %}{{ x }}{% endif %}", {"x"}),
        ("{% if x is not defined %}{% else %}{{ x }}{% endif %}", set()),  # near miss: the else branch is the safe one
        ("{% if not x is defined %}{{ x }}{% endif %}", {"x"}),
        ("{% if x is defined or y %}{{ x }}{% endif %}", {"x", "y"}),  # `or`: the right side alone can hold
        ("{% if x is defined and y %}{{ x }}{% endif %}", {"y"}),  # near miss: `and` needs one side only
        ("{% if x | default('') != '' %}{{ x }}{% endif %}", set()),
        ("{% if x | default('a') | length > 0 %}{{ x }}{% endif %}", {"x"}),  # a truthy fallback proves nothing
        # order and scope of template-local assignments
        ("{{ x }}{% set x = 1 %}{{ x }}", {"x"}),  # the earlier read still needs an external value
        ("{% set x = 1 %}{{ x }}", set()),  # near miss: assigned first
        ("{% set x = x %}", {"x"}),  # the right-hand side is read before the target is bound
        ("{% for i in a %}{{ i }}{% endfor %}{{ i }}", {"a", "i"}),  # a loop target ends with its loop
        ("{% for i, j in a %}{{ i }}{{ j }}{% endfor %}", {"a"}),
        ("{% for i in a %}{% set k = i %}{{ k }}{% endfor %}{{ k }}", {"a", "k"}),  # a set inside a loop is local
    ],
)
def test_the_required_rule_is_decided_per_read(text: str, required: set[str]) -> None:
    assert required_names(text) == required
