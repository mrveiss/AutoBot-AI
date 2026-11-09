# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Command-line arguments for ``audit_api_wiring.py`` (split out to keep that script under its size ceiling)."""

from __future__ import annotations

import argparse


def _add_dump_args(ap: argparse.ArgumentParser) -> None:
    """The spec dumpers: each writes an openapi.json and exits."""
    ap.add_argument("--dump-openapi", metavar="OUT", help="import app_factory.create_app() and dump spec, then exit")
    ap.add_argument(
        "--no-websocket-paths",
        action="store_true",
        help="with --dump-openapi or --dump-slm-openapi: omit x-websocket-paths (#12363)",
    )
    ap.add_argument(
        "--dump-slm-openapi", metavar="OUT", help="import autobot-slm-backend/main.py's app and dump spec, " "then exit"
    )


def _add_spec_args(ap: argparse.ArgumentParser) -> None:
    """Where the known backend routes come from."""
    ap.add_argument("--openapi", help="openapi.json path or URL (authoritative mode)")
    ap.add_argument(
        "--slm-openapi",
        metavar="FILE",
        help="second openapi.json (SLM control-plane backend, "
        "autobot-slm-backend) whose paths are UNIONed into the known "
        "backend route table (#12381) — produce it with "
        "--dump-slm-openapi first",
    )


def _add_report_args(ap: argparse.ArgumentParser) -> None:
    """What is reported and what gates the exit code."""
    ap.add_argument(
        "--baseline",
        metavar="FILE",
        help="file of known/tracked unwired frontend paths (one per line) "
        "excluded from the --fail-on-unwired exit code (#12381) — "
        "still reported, just not gated",
    )
    ap.add_argument("--dead-surface", action="store_true", help="also report backend paths with no frontend consumer")
    ap.add_argument(
        "--fail-on-unwired", action="store_true", help="exit non-zero if any unwired call or unmounted router found"
    )
    ap.add_argument(
        "--only-prefix",
        metavar="PREFIX",
        help="restrict unwired-call reporting and exit code to frontend "
        "calls under PREFIX (e.g. /api/llc). Lets CI gate one module "
        "while other pre-existing findings are tracked separately.",
    )


def build_parser(description: str | None) -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=description, formatter_class=argparse.RawDescriptionHelpFormatter)
    _add_spec_args(ap)
    _add_dump_args(ap)
    _add_report_args(ap)
    return ap
