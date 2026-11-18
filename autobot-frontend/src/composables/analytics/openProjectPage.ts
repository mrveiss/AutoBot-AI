// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * The codebase project page's open sequence (#21474).
 *
 * A source switch remounts the page, so the previous page can still be awaiting its own open
 * when it is unmounted. Its sequence then resumed anyway: it re-read results, started job polling
 * nothing owned any more, and saved its source's path over the next page's. Every step after an
 * `await` is taken only while `pageOpen()` holds -- the ONE liveness check of this sequence.
 */

export interface ProjectPageOpenSteps {
  /** The `:sourceId` route param; none means there is no project to open. */
  sourceId: string | undefined
  /** True while the page that started this sequence is mounted. */
  pageOpen: () => boolean
  /** Return to the landing page (no source, or the source cannot be read). */
  leave: () => void
  /** Started before the source is read, whether or not it loads (GH#11129). */
  beforeSourceLoad: () => void
  /** Read and select the source; false when it cannot be read (or the page was left meanwhile). */
  loadSourceById: (sourceId: string, pageOpen: () => boolean) => Promise<boolean>
  checkCurrentIndexingJob: () => Promise<void>
  /** Read the stored results for the source -- reads only, never a scan (#20491). */
  loadPageResults: () => void
}

export async function openProjectPage(steps: ProjectPageOpenSteps): Promise<void> {
  if (!steps.sourceId) {
    steps.leave()
    return
  }
  steps.beforeSourceLoad()
  const loaded = await steps.loadSourceById(steps.sourceId, steps.pageOpen)
  if (!steps.pageOpen()) return
  if (!loaded) {
    steps.leave()
    return
  }
  await steps.checkCurrentIndexingJob()
  if (!steps.pageOpen()) return
  steps.loadPageResults()
}
