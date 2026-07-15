# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Positive fixture: EnhancedFoo coexists with Foo — one violation."""


class Foo:
    pass


class EnhancedFoo(Foo):
    pass
