<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  UiModeSettingsCard — "Preferred mode" in Settings › Appearance (#18240).
  Minimal / Full as two pressed-state cards, and which mode AutoBot opens in at
  sign-in (Last used / Minimal / Full) as a radiogroup. Both write through
  useUiMode, the same state the header toggle drives; usePreferences syncs it
  to the account.
-->
<template>
  <section class="rounded-lg border border-autobot-border bg-autobot-bg-secondary" aria-labelledby="ui-mode-title">
    <header class="border-b border-autobot-border bg-autobot-bg-tertiary px-5 py-4">
      <h3 id="ui-mode-title" class="text-base font-semibold text-autobot-text-primary">{{ $t('settings.preferredMode.title') }}</h3>
      <p class="mt-1 text-sm text-autobot-text-secondary">{{ $t('settings.preferredMode.subtitle') }}</p>
    </header>

    <div class="space-y-4 p-5">
      <div class="grid gap-3 sm:grid-cols-2" role="group" :aria-label="$t('settings.preferredMode.group')">
        <button
          v-for="card in modes"
          :key="card.mode"
          type="button"
          :class="[cardClass, uiMode === card.mode ? 'border-autobot-primary bg-autobot-primary-bg' : 'border-autobot-border hover:bg-autobot-bg-tertiary']"
          :aria-pressed="uiMode === card.mode"
          :data-testid="`ui-mode-${card.mode}`"
          @click="pickMode(card.mode)"
        >
          <span class="flex items-center gap-2 font-semibold text-autobot-text-primary">
            {{ $t(card.label) }}
            <BaseBadge v-if="uiMode === card.mode" variant="info" size="sm" tone="solid" class="ms-auto">{{ $t('settings.preferredMode.selected') }}</BaseBadge>
          </span>
          <span class="text-sm text-autobot-text-secondary">{{ $t(card.desc) }}</span>
        </button>
      </div>

      <div class="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-autobot-border pt-3">
        <div class="min-w-52 flex-1">
          <span id="ui-start-label" class="block text-sm font-semibold text-autobot-text-primary">{{ $t('settings.preferredMode.startIn') }}</span>
          <span class="text-sm text-autobot-text-secondary">{{ $t('settings.preferredMode.startInDesc') }}</span>
        </div>
        <div class="flex gap-0.5 rounded-lg border border-autobot-border bg-autobot-bg-tertiary p-0.5" role="radiogroup" aria-labelledby="ui-start-label" @keydown="onStartKey">
          <button
            v-for="opt in starts"
            :key="opt.start"
            type="button"
            role="radio"
            :aria-checked="uiStart === opt.start"
            :tabindex="uiStart === opt.start ? 0 : -1"
            :class="[segClass, uiStart === opt.start ? 'bg-autobot-bg-secondary font-semibold text-autobot-text-primary shadow-sm' : 'text-autobot-text-secondary hover:text-autobot-text-primary']"
            :data-testid="`ui-start-${opt.start}`"
            @click="setStart(opt.start)"
          >
            {{ $t(opt.label) }}
          </button>
        </div>
      </div>

      <ul class="space-y-1 text-sm text-autobot-text-secondary">
        <li v-for="note in notes" :key="note">{{ $t(note) }}</li>
      </ul>
    </div>
  </section>
</template>

<script setup lang="ts">
import { nextTick } from 'vue'
import { BaseBadge } from '@autobot/ui'
import { useUiMode, useUiModeAnnouncer, type UiMode, type UiStart } from '@/composables/useUiMode'

const { uiMode, uiStart, setMode, setStart } = useUiMode()
const announceMode = useUiModeAnnouncer()

const cardClass = 'flex flex-col gap-1.5 rounded-lg border p-4 text-start transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-autobot-primary'
const segClass = 'h-8 rounded-md px-3 text-sm transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-autobot-primary'

const modes: Array<{ mode: UiMode; label: string; desc: string }> = [
  { mode: 'minimal', label: 'settings.preferredMode.minimal', desc: 'settings.preferredMode.minimalDesc' },
  { mode: 'full', label: 'settings.preferredMode.full', desc: 'settings.preferredMode.fullDesc' },
]
const starts: Array<{ start: UiStart; label: string }> = [
  { start: 'last', label: 'settings.preferredMode.startLast' },
  { start: 'minimal', label: 'settings.preferredMode.startMinimal' },
  { start: 'full', label: 'settings.preferredMode.startFull' },
]
const notes = [
  'settings.preferredMode.noteSynced',
  'settings.preferredMode.noteDirectLinks',
  'settings.preferredMode.noteNeverHidden',
]

/** Roving radio: arrows move the choice and its focus together. */
function onStartKey(event: KeyboardEvent): void {
  const forward = event.key === 'ArrowRight' || event.key === 'ArrowDown'
  const back = event.key === 'ArrowLeft' || event.key === 'ArrowUp'
  if (!forward && !back) return
  event.preventDefault()
  const group = event.currentTarget as HTMLElement
  const at = starts.findIndex((opt) => opt.start === uiStart.value)
  setStart(starts[(at + (forward ? 1 : -1) + starts.length) % starts.length].start)
  void nextTick(() => group.querySelector<HTMLElement>('[aria-checked="true"]')?.focus())
}

function pickMode(mode: UiMode): void {
  if (mode === uiMode.value) return
  setMode(mode)
  announceMode(mode)
}
</script>
