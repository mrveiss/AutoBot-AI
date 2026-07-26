// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Regression test for #12342: the SSH terminal (which statically pulls in
 * xterm + its addons, ~336KB) must be lazy-loaded from ChatTabContent so
 * xterm's JS is fetched only when a host is selected and the terminal
 * actually renders — not at /chat first paint.
 *
 * This guards the code-splitting at the source level: a future refactor that
 * reverts SSHTerminal to a static top-level import would put xterm back into
 * the /chat initial chunk and regress FCP.
 */

import { describe, it, expect } from 'vitest'
// Vite `?raw` import returns the component source as a string.
import source from '../ChatTabContent.vue?raw'

describe('ChatTabContent SSH terminal code-splitting (#12342)', () => {
  it('loads SSHTerminal via a dynamic import (defineAsyncComponent)', () => {
    expect(source).toMatch(
      /defineAsyncComponent\(\s*\(\)\s*=>\s*import\(\s*['"`][^'"`]*terminal\/SSHTerminal\.vue['"`]\s*\)\s*\)/,
    )
  })

  it('does NOT statically import SSHTerminal at the top level', () => {
    // A static `import SSHTerminal from '.../SSHTerminal.vue'` would bundle
    // xterm into the eager chat chunk again.
    expect(source).not.toMatch(/^\s*import\s+SSHTerminal\s+from/m)
  })
})
