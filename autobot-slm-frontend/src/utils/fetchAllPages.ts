// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Read every page of a paged list endpoint (#21584).
 *
 * `list_nodes` answers one page of `per_page` (default 20, at most 100) with a `total`; a caller that
 * reads only the first response silently drops the rest of the fleet. This is the one fetch every
 * caller of the node list goes through.
 */

/** The backend's per-page ceiling for node listing (`le=100`): the largest single request allowed. */
export const MAX_PAGE_SIZE = 100

export type PageParams = { page: number; per_page: number }

export interface Page<T> {
  items: T[]
  total: number
}

/**
 * A page after the first could not be read. `items` is what was read, `total` what the server reports,
 * so a caller can show the partial list and say it is partial instead of showing a shorter list as whole.
 */
export class PartialListError<T> extends Error {
  readonly items: T[]
  readonly total: number
  /** Why the page could not be read, as text. */
  readonly reason: string

  constructor(items: T[], total: number, cause: unknown) {
    const reason = cause instanceof Error ? cause.message : String(cause)
    super(`Loaded ${items.length} of ${total}: ${reason}`)
    this.name = 'PartialListError'
    this.items = items
    this.total = total
    this.reason = reason
  }
}

/**
 * Collect all pages, one request each, never above `perPage` items. A failure on the first page is
 * rethrown as is (nothing was read); a failure on a later page throws `PartialListError`.
 */
export async function fetchAllPages<T>(
  getPage: (params: PageParams) => Promise<Page<T>>,
  perPage: number = MAX_PAGE_SIZE,
): Promise<T[]> {
  const items: T[] = []
  let total = Number.POSITIVE_INFINITY
  for (let page = 1; items.length < total; page++) {
    let result: Page<T>
    try {
      result = await getPage({ page, per_page: Math.min(perPage, MAX_PAGE_SIZE) })
    } catch (err) {
      if (page === 1) throw err
      throw new PartialListError(items, total, err)
    }
    total = result.total
    if (result.items.length === 0) break // rows were removed while paging: nothing more to read
    items.push(...result.items)
  }
  return items
}
