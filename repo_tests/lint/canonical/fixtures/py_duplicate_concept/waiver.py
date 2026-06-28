# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Waiver fixture: EnhancedFoo/Foo pair suppressed via inline waiver."""


class Foo:
    pass


class EnhancedFoo(Foo):  # canonical: ignore py-duplicate-concept — legacy compat (#10577)
    pass
