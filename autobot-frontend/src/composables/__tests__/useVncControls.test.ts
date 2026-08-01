/**
 * `useVncControls` must exist once (#12653).
 *
 * It existed three times — here, in autobot-slm-frontend, and in the shared
 * `@autobot/vnc` plugin. This asserts the local paths now resolve to the SAME
 * function object as the package, not a same-named twin: two equivalent-but-
 * distinct implementations is the fork this issue exists to remove.
 */
import { describe, expect, it } from 'vitest'

import { useVncControls as canonical } from '@autobot/vnc'
import { useVncControls as local } from '../useVncControls'

describe('useVncControls single implementation', () => {
  it('re-exports the canonical function, not a copy', () => {
    expect(local).toBe(canonical)
  })

  it('exposes a callable composable', () => {
    expect(typeof local).toBe('function')
  })
})
