# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Errors of the Company OS model services (#18390), mapped to HTTP by the router."""

from typing import List


class CompanyOsError(ValueError):
    """The request makes no sense (400)."""


class CompanyOsNotFound(CompanyOsError):
    """Missing in THIS company (404). Another company's row is indistinguishable."""


class CompanyOsConflict(CompanyOsError):
    """Duplicate, or still referenced (409)."""


class GraphInvalid(CompanyOsError):
    """The graph is not well-formed (422); carries every error found."""

    def __init__(self, errors: List[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors
