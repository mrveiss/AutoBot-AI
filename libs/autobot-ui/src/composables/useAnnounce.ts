// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// useAnnounce — screen-reader announcements via one body-level aria-live
// region. Promoted from autobot-slm-frontend useAccessibility (#754) into the
// kit (#18240) so both apps share ONE announcer. Behaviour is unchanged: the
// region is created on first use, and the message is cleared then set on the
// next animation frame so an identical message is re-announced.

import { onMounted } from 'vue'

export const LIVE_REGION_ID = 'a11y-live-region'

export type AnnouncePriority = 'polite' | 'assertive'

function ensureLiveRegion(): HTMLElement {
  const existing = document.getElementById(LIVE_REGION_ID)
  if (existing) return existing
  const region = document.createElement('div')
  region.id = LIVE_REGION_ID
  region.setAttribute('aria-live', 'polite')
  region.setAttribute('aria-atomic', 'true')
  region.setAttribute('role', 'status')
  region.className = 'sr-only'
  document.body.appendChild(region)
  return region
}

export function useAnnounce() {
  function announce(message: string, priority: AnnouncePriority = 'polite'): void {
    const region = ensureLiveRegion()
    region.setAttribute('aria-live', priority)
    // Clear then set to ensure re-announcement
    region.textContent = ''
    requestAnimationFrame(() => {
      region.textContent = message
    })
  }

  onMounted(() => {
    ensureLiveRegion()
  })

  return { announce }
}
