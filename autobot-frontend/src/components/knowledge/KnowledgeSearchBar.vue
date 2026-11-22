<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  KnowledgeSearchBar — the search OPTIONS of the Knowledge Browser (#18244, owner decision D2).
  There is one search box (KnowledgeBrowserHeader); this is the body of the popover next to it:
  traditional vs RAG-enhanced search, the access-level filter and the RAG options. It holds no
  query and no search button.
-->
<template>
  <div class="search-options" data-testid="knowledge-search-options">
    <section class="opt-group">
      <div class="opt-row">
        <BaseSwitch v-model="useRagSearch" :label="$t('knowledge.search.ragEnhanced')" />
        <span class="opt-name">{{ $t('knowledge.search.ragEnhanced') }}</span>
      </div>
      <p class="opt-desc">
        {{ useRagSearch ? $t('knowledge.search.ragDesc') : $t('knowledge.search.traditionalDesc') }}
      </p>
    </section>

    <section class="opt-group" :aria-label="$t('knowledge.search.filterByAccessLevel')">
      <h3 class="opt-title">{{ $t('knowledge.search.filterByAccessLevel') }}</h3>
      <div class="chips">
        <BaseButton
          v-for="level in accessLevels"
          :key="level.value"
          size="xs"
          :variant="selectedAccessLevel === level.value ? 'primary' : 'outline'"
          :aria-pressed="selectedAccessLevel === level.value"
          @click="toggleAccessLevel(level.value)"
        >
          {{ level.label }}
        </BaseButton>
        <BaseButton
          v-if="selectedAccessLevel"
          size="xs"
          variant="ghost"
          :aria-label="$t('knowledge.search.clearAccessLevelFilter')"
          @click="clearAccessLevelFilter()"
        >
          {{ $t('knowledge.search.clear') }}
        </BaseButton>
      </div>
    </section>

    <section v-if="useRagSearch" class="opt-group">
      <div class="opt-row">
        <BaseSwitch v-model="ragOptions.reformulateQuery" :label="$t('knowledge.search.autoEnhanceQuery')" />
        <span class="opt-name">{{ $t('knowledge.search.autoEnhanceQuery') }}</span>
      </div>
      <div class="opt-row">
        <BaseSwitch v-model="ragOptions.enableReranking" :label="$t('knowledge.search.enableReranking')" />
        <span class="opt-name">{{ $t('knowledge.search.enableReranking') }}</span>
        <BaseBadge variant="info" size="xs">{{ $t('knowledge.search.rerankingBadge') }}</BaseBadge>
      </div>
      <div class="opt-row">
        <span class="opt-name">{{ $t('knowledge.search.resultsLimit') }}</span>
        <BaseSelectMenu v-model="limit" :options="LIMIT_OPTIONS" :label="$t('knowledge.search.resultsLimit')" size="sm" />
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseBadge, BaseButton, BaseSelectMenu, BaseSwitch } from '@autobot/ui'
import type { useKnowledgeSearch } from '@/composables/knowledge/useKnowledgeSearch'

const props = defineProps<{ search: ReturnType<typeof useKnowledgeSearch> }>()
const { t } = useI18n()

// The same stable refs the composable owns; destructured so the template does not mutate a prop object.
const { useRagSearch, ragOptions, selectedAccessLevel, toggleAccessLevel, clearAccessLevelFilter } = props.search

const LIMIT_OPTIONS = ['5', '10', '15', '20'].map((value) => ({ value, label: value }))

const limit = computed({
  get: () => String(ragOptions.value.limit),
  set: (value: string) => {
    ragOptions.value.limit = Number(value)
  },
})

const accessLevels = computed(() => [
  { value: 'autobot', label: t('knowledge.search.accessPlatform') },
  { value: 'general', label: t('knowledge.search.accessPublic') },
  { value: 'system', label: t('knowledge.search.accessSystem') },
  { value: 'user', label: t('knowledge.search.accessUser') },
])
</script>

<style scoped>
.search-options {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-4);
}

.opt-group {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.opt-title {
  margin: 0;
  font-size: var(--text-xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted);
}

.opt-row {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  min-block-size: 32px;
}

.opt-name {
  font-size: var(--text-sm);
  color: var(--text);
}

.opt-desc {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--muted);
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-2);
}
</style>
