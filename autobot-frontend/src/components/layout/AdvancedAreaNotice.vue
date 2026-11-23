<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  AdvancedAreaNotice — the "This is an advanced area" card (#18244, Refined UI).
  Shown by a section shell on routes marked `meta.adv`. It carries `only-min`, so
  the shared CSS shows it only while Minimal mode is on (the route still opens by
  deep link; the page below it stays visible). "Show all features" switches to Full
  mode through useUiMode; "Go to Home" leaves the area. The shell's own "Showing
  essentials" note (AppHeader) is not repeated here.
-->
<template>
  <BaseCard class="only-min advanced-area" data-testid="advanced-area-notice" :aria-labelledby="titleId" flush>
    <div class="advanced-area__body">
      <span class="advanced-area__tile" aria-hidden="true"><Icon name="layer-group" /></span>
      <div class="advanced-area__text">
        <h2 :id="titleId" class="advanced-area__title">{{ $t('ui.advancedArea.title') }}</h2>
        <span class="advanced-area__sub">{{ $t('ui.advancedArea.body') }}</span>
      </div>
      <div class="advanced-area__actions">
        <BaseButton variant="outline" size="sm" data-testid="advanced-area-show-all" @click="showAll">
          {{ $t('ui.minimalNoteAction') }}
        </BaseButton>
        <BaseButton variant="outline" size="sm" :as="RouterLink" to="/">
          {{ $t('ui.advancedArea.goHome') }}
        </BaseButton>
      </div>
    </div>
  </BaseCard>
</template>

<script setup lang="ts">
import { useId } from 'vue'
import { RouterLink } from 'vue-router'
import { BaseButton, BaseCard } from '@autobot/ui'
import Icon from '@/components/ui/Icon.vue'
import { useUiMode, useUiModeAnnouncer } from '@/composables/useUiMode'

const titleId = `advanced-area-${useId()}`
const { setMode } = useUiMode()
const announceMode = useUiModeAnnouncer()

function showAll(): void {
  setMode('full')
  announceMode('full')
}
</script>

<style scoped>
/* No `display` here: `.only-min` (components.css) owns show/hide by UI mode. */
.advanced-area {
  margin: var(--spacing-4) var(--page-margin) 0;
}

.advanced-area__body {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-3) var(--spacing-4);
  inline-size: 100%;
}

.advanced-area__tile {
  display: grid;
  place-items: center;
  inline-size: 34px;
  block-size: 34px;
  border-radius: var(--radius-lg);
  background: var(--tile);
  border: var(--bw) solid var(--tile-b);
  color: var(--text2);
}

.advanced-area__text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1 1 240px;
  min-inline-size: 0;
}

.advanced-area__title {
  margin: 0;
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text);
}

.advanced-area__sub {
  font-size: var(--text-sm);
  color: var(--muted);
}

.advanced-area__actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-2);
}
</style>
