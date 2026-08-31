<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Author: mrveiss -->
<!--
  #14221 step 6b: the add/remove control for one kind of thing a role carries.

  The Roles tab shipped read-only: it could show a role's permissions, tools,
  workflows and credentials, but not change any of them, so eleven backend
  endpoints had no way to be reached. Five near-identical panels would have been
  five places for that gap to reopen, so the panel is one component used five
  times.

  Deliberately dumb: it owns no fetching and no optimistic state. The parent
  reloads after a successful call, so what is drawn is always what the server
  last returned — an optimistic list that diverges from the server is worse than
  a slightly slower one, because it shows access that may not exist.
-->
<template>
  <section class="attachment-panel">
    <header class="attachment-header">
      <h4 class="attachment-title">{{ title }}</h4>
      <span v-if="items.length" class="attachment-count">{{ items.length }}</span>
    </header>

    <p v-if="items.length === 0" class="attachment-empty">{{ emptyLabel }}</p>

    <ul v-else class="attachment-list">
      <li v-for="item in items" :key="item" class="attachment-chip">
        <span class="attachment-value">{{ item }}</span>
        <button
          type="button"
          class="attachment-remove"
          :disabled="busy"
          :aria-label="`${removeLabel}: ${item}`"
          @click="$emit('remove', item)"
        >
          ×
        </button>
      </li>
    </ul>

    <form class="attachment-add" @submit.prevent="submit">
      <label class="attachment-add-label" :for="inputId">{{ addLabel }}</label>
      <input
        :id="inputId"
        v-model="draft"
        type="text"
        :placeholder="placeholder"
        :disabled="busy"
        class="attachment-input"
      />
      <BaseButton type="submit" variant="secondary" :disabled="busy || !draft.trim()">
        {{ addLabel }}
      </BaseButton>
    </form>
  </section>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import BaseButton from '@/components/base/BaseButton.vue'

const props = defineProps<{
  /**
   * Locale-invariant identity for this panel, e.g. "permissions".
   *
   * The DOM id was previously derived from `title`, which is translated. The
   * slug regex keeps only `a-z0-9`, so every non-Latin script collapsed to the
   * empty string and all four panels rendered the identical id
   * `attachment--` in Arabic, Hebrew, Farsi and Urdu — duplicate ids on one
   * page, and every `<label for>` pointing at the first panel's input.
   *
   * A DOM id must never depend on the display language.
   */
  panelKey: string
  title: string
  items: string[]
  addLabel: string
  removeLabel: string
  emptyLabel: string
  placeholder?: string
  /** Set while a call is in flight, so a double submit cannot fire twice. */
  busy?: boolean
}>()

const emit = defineEmits<{
  (e: 'add', value: string): void
  (e: 'remove', value: string): void
}>()

const draft = ref('')

// Unique per panel so the label/input pair stays associated when several are on
// one page. Built from `panelKey`, never from the translated title.
const inputId = computed(() => `attachment-${props.panelKey}`)

function submit(): void {
  const value = draft.value.trim()
  if (!value || props.busy) return
  emit('add', value)
  draft.value = ''
}
</script>

<style scoped>
.attachment-panel {
  margin-top: var(--spacing-md);
}

.attachment-header {
  display: flex;
  align-items: baseline;
  gap: var(--spacing-xs);
}

.attachment-title {
  margin: 0 0 var(--spacing-xs);
  font-size: var(--font-size-md);
  color: var(--color-text-primary);
}

.attachment-count {
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
}

.attachment-empty {
  margin: 0 0 var(--spacing-xs);
  color: var(--color-text-secondary);
}

.attachment-list {
  list-style: none;
  margin: 0 0 var(--spacing-xs);
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-xs);
}

.attachment-chip {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-xs) var(--spacing-sm);
  border-radius: var(--radius-sm);
  background: var(--color-surface-hover);
  color: var(--color-text-primary);
  font-family: var(--font-family-mono, monospace);
  font-size: var(--font-size-sm);
}

.attachment-remove {
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  font-size: var(--font-size-md);
  line-height: 1;
  padding: 0;
}

.attachment-remove:hover:not(:disabled) {
  color: var(--color-text-primary);
}

.attachment-remove:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.attachment-add {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  flex-wrap: wrap;
}

.attachment-add-label {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}

.attachment-input {
  flex: 1 1 12rem;
  min-width: 0;
}
</style>
