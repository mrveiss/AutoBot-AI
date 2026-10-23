#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Fix search by using simple text storage in Redis facts that can be searched.

Entry point kept for ``python scripts/fix_search.py``; the implementation lives in
``search_index_utility.py`` (#18964), which uploads the documents and runs the test
queries concurrently.
"""

from search_index_utility import upload_docs_as_searchable_facts

if __name__ == "__main__":
    upload_docs_as_searchable_facts()
