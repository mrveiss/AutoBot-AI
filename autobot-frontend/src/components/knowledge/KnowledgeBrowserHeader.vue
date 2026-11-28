<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  KnowledgeBrowserHeader — the Browser's one header and one search box (#18244, owner decision D2).
  Typing filters the document tree at once (`filter`); Enter runs the unified knowledge search
  (`submit`). The search options (RAG, access level) sit in an advanced popover beside the box.
-->
<template>
  <PageHeader
    class="kb-header"
    :title="$t('knowledge.browserHeader.title')"
    :subtitle="$t('knowledge.browserHeader.subtitle')"
  >
    <template #breadcrumb>
      <span class="kb-crumb">{{ $t('knowledge.browserHeader.breadcrumb') }}</span>
    </template>
    <template #actions>
      <div class="kb-search">
        <BaseInput
          :model-value="query"
          type="search"
          class="kb-search__box"
          data-testid="knowledge-search"
          :aria-label="$t('knowledge.browserHeader.searchLabel')"
          :placeholder="$t('knowledge.browserHeader.searchPlaceholder')"
          :clearable="true"
          :clear-label="$t('knowledge.browserHeader.clearSearch')"
          @update:model-value="$emit('filter', $event)"
          @keydown.enter="$emit('submit')"
          @clear="$emit('clear')"
        >
          <template #prefix><Icon name="search" aria-hidden="true" /></template>
        </BaseInput>
        <BasePopover :label="$t('knowledge.browserHeader.optionsLabel')" align="end">
          <template #trigger>
            <BaseButton
              variant="outline"
              size="md"
              class="adv"
              data-testid="knowledge-search-options-trigger"
              :aria-label="$t('knowledge.browserHeader.optionsLabel')"
            >
              <Icon name="sliders-h" aria-hidden="true" />
              {{ $t('knowledge.browserHeader.options') }}
            </BaseButton>
          </template>
          <KnowledgeSearchBar :search="search" />
        </BasePopover>
      </div>
    </template>
  </PageHeader>
</template>

<script setup lang="ts">
import { BaseButton, BaseInput, BasePopover, PageHeader } from '@autobot/ui'
import Icon from '@/components/ui/Icon.vue'
import KnowledgeSearchBar from './KnowledgeSearchBar.vue'
import type { useKnowledgeSearch } from '@/composables/knowledge/useKnowledgeSearch'

defineProps<{
  /** The text in the box: filters the tree as it changes. */
  query: string
  search: ReturnType<typeof useKnowledgeSearch>
}>()

defineEmits<{
  filter: [query: string]
  submit: []
  clear: []
}>()
</script>

<style scoped>
.kb-header {
  --aui-page-header-bg: transparent;
  --aui-page-header-border: transparent;
  --aui-page-header-px: 0;
  --aui-page-header-py: 0;
}

.kb-crumb {
  font-size: var(--text-sm);
  color: var(--muted);
}

.kb-search {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.kb-search__box {
  flex: 0 1 360px;
  min-inline-size: 220px;
}
</style>
