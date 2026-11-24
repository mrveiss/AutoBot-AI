<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  UiModeToggle — the Minimal / Full switch in the header (#18240). A toggle
  button, not a menu: aria-pressed is true while Minimal is on, focus stays on
  the button after a press, and the change is announced through the kit's one
  live region. The mode itself lives in useUiMode (the only writer of data-ui).
-->
<template>
  <BaseTooltip :text="$t('nav.uiMode.tip')" placement="bottom">
    <template #default="{ describedby }">
      <BaseButton
        variant="ghost"
        class="h-10"
        :aria-label="$t('nav.uiMode.label')"
        :aria-pressed="isMinimal"
        :aria-describedby="describedby"
        data-testid="ui-mode-toggle"
        @click="onToggle"
      >
        <template #icon-left>
          <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
            <path d="M6 4h12a2 2 0 012 2v12a2 2 0 01-2 2H6a2 2 0 01-2-2V6a2 2 0 012-2z" />
            <path d="M4 9h16M9 9v11" />
            <path d="M12.5 12.5h4v4h-4z" />
          </svg>
        </template>
        <span class="hidden xl:inline">{{ $t('nav.uiMode.label') }}</span>
      </BaseButton>
    </template>
  </BaseTooltip>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { BaseButton, BaseTooltip } from '@autobot/ui'
import { useUiMode, useUiModeAnnouncer } from '@/composables/useUiMode'

const { uiMode, toggle } = useUiMode()
const announceMode = useUiModeAnnouncer()
const isMinimal = computed(() => uiMode.value === 'minimal')

function onToggle(): void {
  toggle()
  announceMode(uiMode.value)
}
</script>
