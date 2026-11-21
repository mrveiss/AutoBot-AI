// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

import { describe, it, expect } from 'vitest'
import { errorText } from './errorText'

describe('errorText', () => {
  it('returns an Error message', () => expect(errorText(new Error('boom'))).toBe('boom'))
  it('keeps a non-Error value as text', () => expect(errorText('gateway timeout')).toBe('gateway timeout'))
})
