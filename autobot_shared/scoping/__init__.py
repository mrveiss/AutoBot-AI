# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Canonical scoping primitives: ScopeLevel + visibility rule (#11277, #11290)."""

from autobot_shared.scoping.scope_level import ScopeLevel
from autobot_shared.scoping.visibility import Principal, ResourceDescriptor, is_visible

__all__ = ["Principal", "ResourceDescriptor", "ScopeLevel", "is_visible"]
