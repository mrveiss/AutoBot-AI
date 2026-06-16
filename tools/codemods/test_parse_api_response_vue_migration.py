# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for parse_api_response_vue_migration.py codemod.

Each test is a before/after string pair exercising one of the real patterns
we migrated in PR #5177. If this codemod is ever rerun on a new batch of
files, these tests catch regressions in the transform logic.
"""

import textwrap

from parse_api_response_vue_migration import transform


def _dedent(s: str) -> str:
    return textwrap.dedent(s).lstrip("\n")


def test_single_line_apiclient_get() -> None:
    before = _dedent("""
        const response = await apiClient.get(`${url}/x`)
        const data = await parseApiResponse<Record<string, any>>(response)
        use(data)
        """)
    expected = _dedent("""
        const data = await apiClient.get<Record<string, any>>(`${url}/x`)
        use(data)
        """)
    got, count = transform(before)
    assert got == expected
    assert count == 1


def test_single_line_apiclient_post_with_body() -> None:
    before = _dedent("""
        const response = await apiClient.post(`${url}/x`, { q: query })
        const data = await parseApiResponse<Record<string, any>>(response)
        use(data)
        """)
    expected = _dedent("""
        const data = await apiClient.post<Record<string, any>>(`${url}/x`, { q: query })
        use(data)
        """)
    got, count = transform(before)
    assert got == expected
    assert count == 1


def test_multiline_body_patches_opener_only() -> None:
    # This was the tricky case in the 5033 Vue migration — my first script
    # iteration missed these because its RESPONSE_LINE regex required the
    # closing `)` on the same line.
    before = _dedent("""
        const response = await apiClient.post(`${url}/extract`, {
          conversation_id: conversationId.value.trim(),
          messages
        })

        const parsedResponse = await parseApiResponse<Record<string, any>>(response)
        use(parsedResponse)
        """)
    expected = _dedent("""
        const parsedResponse = await apiClient.post<Record<string, any>>(`${url}/extract`, {
          conversation_id: conversationId.value.trim(),
          messages
        })

        use(parsedResponse)
        """)
    got, count = transform(before)
    assert got == expected
    assert count == 1


def test_uppercase_ApiClient_also_matched() -> None:
    # Some Vue files use the `ApiClient` (PascalCase) singleton import.
    before = _dedent("""
        const apiResponse = await ApiClient.post(`${url}/op`, {})
        const response = await parseApiResponse<Record<string, any>>(apiResponse)
        use(response)
        """)
    expected = _dedent("""
        const response = await ApiClient.post<Record<string, any>>(`${url}/op`, {})
        use(response)
        """)
    got, count = transform(before)
    assert got == expected
    assert count == 1


def test_drops_parseApiResponse_import_when_last_use_removed() -> None:
    before = _dedent("""
        import apiClient from '@/utils/ApiClient'
        import { parseApiResponse } from '@/utils/apiResponseHelpers'
        import { useI18n } from 'vue-i18n'

        async function run() {
          const response = await apiClient.get(`${url}`)
          const data = await parseApiResponse<Record<string, any>>(response)
          return data
        }
        """)
    got, count = transform(before)
    assert count == 1
    assert "import { parseApiResponse }" not in got
    # Other imports preserved
    assert "import apiClient" in got
    assert "import { useI18n }" in got


def test_keeps_parseApiResponse_import_if_uses_remain() -> None:
    # If the codemod can't migrate every site (pattern variant, etc.) the
    # import must stay in place for the remaining uses.
    before = _dedent("""
        import { parseApiResponse } from '@/utils/apiResponseHelpers'

        async function a() {
          const response = await apiClient.get(`${url}`)
          const data = await parseApiResponse<Record<string, any>>(response)
          return data
        }

        async function b() {
          // Pattern the codemod doesn't handle (no matching opener)
          const data = await parseApiResponse<SomeType>(externalResponse)
          return data
        }
        """)
    got, count = transform(before)
    assert count == 1
    assert "import { parseApiResponse }" in got


def test_multiple_sites_in_one_file() -> None:
    # Real files often have many call sites. Each must be migrated once;
    # count reflects total.
    before = _dedent("""
        async function a() {
          const response = await apiClient.get(`${url}/a`)
          const data = await parseApiResponse<TypeA>(response)
          return data
        }

        async function b() {
          const response = await apiClient.post(`${url}/b`, {})
          const data = await parseApiResponse<TypeB>(response)
          return data
        }
        """)
    got, count = transform(before)
    assert count == 2
    assert "apiClient.get<TypeA>" in got
    assert "apiClient.post<TypeB>" in got
    assert "parseApiResponse" not in got


def test_skips_parseApiResponse_without_matching_opener() -> None:
    # If we can't find the `const X = await apiClient.METHOD(` opener, leave
    # the site alone (rather than mangle). The import also stays.
    before = _dedent("""
        import { parseApiResponse } from '@/utils/apiResponseHelpers'

        async function weird() {
          // Opener might be named differently, come from a different binding,
          // or use fetchWithAuth. Codemod leaves this alone.
          const raw = someOtherFetch()
          const data = await parseApiResponse<SomeType>(raw)
          return data
        }
        """)
    got, count = transform(before)
    assert count == 0
    assert "await parseApiResponse" in got


def test_empty_file_is_unchanged() -> None:
    before = ""
    got, count = transform(before)
    assert got == ""
    assert count == 0


def test_file_without_parseApiResponse_is_unchanged() -> None:
    before = _dedent("""
        const x = await apiClient.get(`${url}`)
        return x
        """)
    got, count = transform(before)
    assert got == before
    assert count == 0
