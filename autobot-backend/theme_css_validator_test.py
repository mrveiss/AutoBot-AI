# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi import HTTPException

from theme_css_validator import validate_theme_css

OK = '[data-theme-variant="x"] { --bg-primary: #fff; }'


def test_accepts_scoped_rule():
    validate_theme_css(OK, "x")  # no raise


def test_rejects_unscoped_rule():
    with pytest.raises(HTTPException):
        validate_theme_css("body { color: red; }", "x")


def test_rejects_wrong_variant_id():
    with pytest.raises(HTTPException):
        validate_theme_css('[data-theme-variant="other"] { --x: 1; }', "x")


def test_rejects_at_import():
    with pytest.raises(HTTPException):
        validate_theme_css('@import url("http://evil/x.css");', "x")


def test_rejects_external_url():
    with pytest.raises(HTTPException):
        validate_theme_css('[data-theme-variant="x"] { background: url(http://evil/p.png); }', "x")


def test_accepts_data_uri_and_relative_url():
    validate_theme_css('[data-theme-variant="x"] { src: url(data:font/woff2;base64,AA); }', "x")
    validate_theme_css('[data-theme-variant="x"] { src: url(./fonts/a.woff2); }', "x")


def test_rejects_expression_and_oversize():
    with pytest.raises(HTTPException):
        validate_theme_css('[data-theme-variant="x"] { width: expression(alert(1)); }', "x")
    with pytest.raises(HTTPException):
        validate_theme_css('[data-theme-variant="x"] { /* a */ }' + "a" * (512 * 1024), "x")
