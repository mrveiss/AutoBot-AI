<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  KnowledgeEntriesFilters — the Manage search box, the category and type filters and the
  entry count (#18244). The filter state lives in the parent; an empty string means "all".
-->
<template>
  <div class="flex flex-wrap items-end gap-3">
    <BaseInput
      v-model="search"
      type="search"
      class="min-w-56 flex-1"
      :label="$t('knowledge.entries.searchAriaLabel')"
      :placeholder="$t('knowledge.entries.searchPlaceholder')"
    />
    <BaseSelectMenu
      :model-value="category || ALL"
      :label="$t('knowledge.entries.filterByCategoryAria')"
      :options="categoryOptions"
      @update:model-value="category = $event === ALL ? '' : $event"
    />
    <BaseSelectMenu
      :model-value="type || ALL"
      :label="$t('knowledge.entries.filterByTypeAria')"
      :options="typeOptions"
      @update:model-value="type = $event === ALL ? '' : $event"
    />
    <BaseButton variant="secondary" size="sm" @click="emit('clear')">{{ $t('knowledge.entries.clearFilters') }}</BaseButton>
    <span class="ms-auto text-sm text-[var(--muted)]">{{ total }} {{ $t('knowledge.entries.entries') }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseButton, BaseInput, BaseSelectMenu } from '@autobot/ui'
import type { KnowledgeCategory } from '@/stores/useKnowledgeStore'

const props = defineProps<{ categories: KnowledgeCategory[]; total: number }>()
const emit = defineEmits<{ clear: [] }>()

const search = defineModel<string>('search', { required: true })
const category = defineModel<string>('category', { required: true })
const type = defineModel<string>('type', { required: true })

const { t } = useI18n()
// A select option cannot carry an empty value, so "all" travels as a sentinel.
const ALL = '__all__'

const categoryOptions = computed(() => [
  { value: ALL, label: t('knowledge.entries.allCategories') },
  ...props.categories.map((c) => ({ value: c.name, label: `${c.name} (${c.documentCount})` })),
])
const typeOptions = computed(() => [
  { value: ALL, label: t('knowledge.entries.allTypes') },
  { value: 'document', label: t('knowledge.entries.documents') },
  { value: 'webpage', label: t('knowledge.entries.webPages') },
  { value: 'api', label: t('knowledge.entries.apiDocs') },
  { value: 'upload', label: t('knowledge.entries.uploads') },
])
</script>
