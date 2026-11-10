// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Which source a pattern-analysis call is for (#20513).
 *
 * The `/patterns/*` routes require `source_id` and answer 422 without it, and
 * `withSourceId` adds nothing when no source is selected. So a call asks here
 * first: with no source it makes no request instead of sending one that is
 * certain to fail.
 *
 * Author: mrveiss
 */

import { createLogger } from '@/utils/debugUtils'
import { hasSourceIdInUrl, sourceIdInUrl } from '@/utils/sourceIdInUrl'

const logger = createLogger('usePatternSourceScope')

export function usePatternSourceScope(withSourceId: (url: string) => string) {
  /** The selected source's id, or null when none is selected. */
  const selectedSourceId = (): string | null => sourceIdInUrl(withSourceId('/'))

  /** True when `url` carries a source; logs the skip when it does not. */
  const hasSource = (url: string, what: string): boolean => {
    if (hasSourceIdInUrl(url)) return true
    logger.debug(`No source selected; skipping ${what}`)
    return false
  }

  return { selectedSourceId, hasSource }
}
