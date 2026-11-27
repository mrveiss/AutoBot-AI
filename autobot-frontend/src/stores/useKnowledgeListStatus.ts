// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * What the Manage list can honestly claim about itself (#17530): it is a server read, so it is
 * stale after a failed re-read and truncated when the server held more than was fetched.
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useKnowledgeListStatus = defineStore('knowledgeListStatus', () => {
  const stale = ref(false)
  const truncated = ref(false)

  function loaded(wasTruncated: boolean) {
    stale.value = false
    truncated.value = wasTruncated
  }
  function failed() {
    stale.value = true
  }
  return { stale, truncated, loaded, failed }
})
