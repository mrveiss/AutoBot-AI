<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  KnowledgeMainCategories — the three category cards of the Knowledge Browser (#18244,
  Refined UI "Knowledge · Browser"): tile, Edit, name, description, fact count, Populate, Import.
  Choosing a card filters the document tree to that category. Backend connectivity is shown
  above the cards, empty-KB (#5201) apart from broken-KB and fetch-error (#5590).
-->
<template>
  <section class="main-categories-wrapper" :aria-label="$t('knowledge.browser.categoriesLabel')">
    <BaseAlert
      v-if="kbFetchError"
      class="kb-status-panel kb-status-panel--error"
      variant="error"
      role="alert"
      :title="$t('knowledge.categoriesFetchError.title')"
      :message="$t('knowledge.categoriesFetchError.description')"
    />
    <BaseAlert
      v-else-if="!kbConnected"
      class="kb-status-panel kb-status-panel--error"
      variant="error"
      role="alert"
      :title="$t('knowledge.categoriesError.title')"
      :message="$t('knowledge.categoriesError.description')"
    />
    <BaseAlert
      v-else-if="showEmptyStateHint"
      class="kb-status-panel kb-status-panel--info"
      variant="info"
      role="status"
      :title="$t('knowledge.emptyState.title')"
    >
      <p class="kb-status-panel__text">{{ $t('knowledge.emptyState.description') }}</p>
      <p class="kb-status-panel__text">{{ $t('knowledge.emptyState.hint') }}</p>
    </BaseAlert>

    <div class="main-categories">
      <BaseCard
        v-for="mainCat in categories"
        :key="mainCat.id"
        class="main-category-card"
        :class="{ 'is-selected': mainCat.id === selectedId }"
      >
        <div class="cat-top">
          <button
            type="button"
            class="cat-select"
            :aria-pressed="mainCat.id === selectedId"
            :aria-label="$t('knowledge.browser.showCategory', { name: mainCat.name })"
            @click="$emit('select', mainCat.id)"
          >
            <span class="cat-tile"><Icon :name="categoryIcon(mainCat)" /></span>
          </button>
          <BaseTooltip :text="$t('knowledge.browser.editCategory')" placement="left">
            <template #default="{ describedby }">
              <BaseButton
                variant="outline"
                size="sm"
                :aria-label="$t('knowledge.browser.editCategory')"
                :aria-describedby="describedby"
                @click="$emit('edit', mainCat)"
              >
                <Icon name="pencil-alt" />
              </BaseButton>
            </template>
          </BaseTooltip>
        </div>

        <div class="cat-text">
          <h2 class="cat-name">{{ mainCat.name }}</h2>
          <p class="cat-desc">{{ mainCat.description }}</p>
        </div>

        <p class="cat-count">
          {{ formatCount(mainCat.count) }}
          <BaseTooltip :text="$t('knowledge.browser.factsTip')" placement="top">
            <template #default="{ describedby }">
              <span class="cat-unit" tabindex="0" :aria-describedby="describedby">{{ $t('knowledge.browser.facts') }}</span>
            </template>
          </BaseTooltip>
        </p>

        <div class="cat-actions">
          <BaseTooltip v-if="canPopulate(mainCat.id)" :text="$t('knowledge.browser.populateTip')" placement="top">
            <template #default="{ describedby }">
              <BaseButton
                variant="outline"
                size="sm"
                :loading="populationStates[mainCat.id]?.isPopulating"
                :disabled="populationStates[mainCat.id]?.isPopulating"
                :aria-describedby="describedby"
                @click="$emit('populate', mainCat.id)"
              >
                <span v-if="!populationStates[mainCat.id]?.isPopulating">{{ $t('knowledge.browser.populate') }}</span>
                <span v-else>{{ populationStates[mainCat.id]?.progress || 0 }}%</span>
              </BaseButton>
            </template>
          </BaseTooltip>
          <BaseTooltip :text="$t('knowledge.browser.importTip')" placement="top">
            <template #default="{ describedby }">
              <BaseButton variant="outline" size="sm" :aria-describedby="describedby" @click="$emit('import')">
                {{ $t('knowledge.browser.import') }}
              </BaseButton>
            </template>
          </BaseTooltip>
        </div>
      </BaseCard>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { BaseAlert, BaseButton, BaseCard, BaseTooltip } from '@autobot/ui'
import Icon from '@/components/ui/Icon.vue'
import type { IconName } from '@/components/ui/Icon.vue'
import { asIconName } from '@/utils/iconMappings'

interface MainCategory {
  id: string
  name: string
  description: string
  icon: string
  color: string
  count: number
}

interface PopulationState {
  isPopulating: boolean
  progress: number
}

interface Props {
  categories: MainCategory[]
  populationStates: Record<string, PopulationState>
  /** The card whose category filters the tree. */
  selectedId?: string | null
  // #5201: backend Redis/KB reachability; true for older backends that omit the flag.
  kbConnected?: boolean
  // #5590: the fetch itself failed (5xx / network), distinct from kbConnected=false.
  kbFetchError?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  selectedId: null,
  kbConnected: true,
  kbFetchError: false,
})

defineEmits<{
  select: [categoryId: string]
  populate: [categoryId: string]
  import: []
  edit: [category: MainCategory]
}>()

// Only these two have a source to fill them from; the user's own knowledge is imported.
const POPULATABLE = new Set(['autobot-documentation', 'system-knowledge'])
const canPopulate = (id: string) => POPULATABLE.has(id)

// #9724: icons come from the backend as plain strings; unknown names fall back to 'folder'.
const categoryIcon = (cat: MainCategory): IconName => asIconName(cat.icon, 'folder')

const formatCount = (n: number) => (n ?? 0).toLocaleString()

// The empty hint shows only once categories loaded AND every count is 0 (no flash at startup).
const showEmptyStateHint = computed(
  () => props.kbConnected && props.categories.length > 0 && props.categories.every((c) => (c.count ?? 0) === 0),
)
</script>

<style scoped>
.main-categories-wrapper {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.kb-status-panel__text {
  margin: 0;
}

.main-categories {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: var(--spacing-3);
}

.main-category-card {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.main-category-card.is-selected {
  border-color: var(--primary);
}

.cat-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
}

.cat-select {
  padding: 0;
  border: 0;
  background: transparent;
  cursor: pointer;
  border-radius: var(--radius-lg);
}

.cat-select:focus-visible {
  outline: 3px solid var(--focus);
  outline-offset: 2px;
}

.cat-tile {
  display: grid;
  place-items: center;
  inline-size: 44px;
  block-size: 44px;
  border-radius: var(--radius-lg);
  background: var(--tile);
  border: var(--bw) solid var(--tile-b);
  color: var(--stroke);
}

.cat-text {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.cat-name {
  margin: 0;
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text);
}

.cat-desc {
  margin: 0;
  font-size: var(--text-sm);
  line-height: 1.45;
  color: var(--text2);
}

.cat-count {
  margin: 0;
  font-size: var(--text-2xl);
  font-weight: 600;
  color: var(--text);
}

.cat-unit {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--muted);
}

.cat-actions {
  display: flex;
  gap: var(--spacing-2);
}
</style>
