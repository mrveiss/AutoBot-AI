// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// A flag that hides a control must also stop its handler (#21796): the handler would otherwise hit
// a route no backend serves if anything reached it. Each handler carries the flag check of the
// control that calls it, as its first statement.

import { describe, it, expect } from 'vitest'
import view from '../BrowserAutomationView.vue?raw'

const HANDLER_FLAGS: Array<[string, string]> = [
  ['handleLaunchSession', 'LAUNCH_ENABLED'],
  ['handleType', 'SESSION_INPUT_ENABLED'],
  ['handleExecuteScript', 'SESSION_INPUT_ENABLED'],
  ['handleRunAutomation', 'AUTOMATION_SCRIPT_ENABLED'],
]

/** The first statement of `async function <name>() {`, or null when the handler is absent. */
function firstStatement(source: string, name: string): string | null {
  const found = new RegExp(`async function ${name}\\(\\) \\{\\n\\s*([^\\n]+)`).exec(source)
  return found ? found[1] : null
}

describe('BrowserAutomationView flag-gated handlers', () => {
  it.each(HANDLER_FLAGS)('%s returns first when %s is off', (handler, flag) => {
    expect(firstStatement(view, handler)).toBe(`if (!${flag}) return`)
  })

  it('finds the first statement of a handler (detector control)', () => {
    expect(firstStatement('async function handleX() {\n  if (!A) return\n  go()\n}', 'handleX')).toBe(
      'if (!A) return',
    )
    expect(firstStatement('async function handleX() {\n  go()\n}', 'handleX')).not.toBe('if (!A) return')
    expect(firstStatement('', 'handleX')).toBeNull()
  })

  it('names every handler a flag-gated button calls', () => {
    for (const [handler] of HANDLER_FLAGS) {
      expect(view).toContain(`@click="${handler}"`)
    }
  })
})
