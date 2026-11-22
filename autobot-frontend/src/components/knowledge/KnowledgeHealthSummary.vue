<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  KnowledgeHealthSummary — the advanced health strip of the Knowledge Browser (#18244,
  Refined UI "Knowledge · Browser"): Total Facts, Total Vectors, Database Size and whether
  RAG is available. Every figure comes from the knowledge stats the backend already serves
  (useVectorStats); the mockup's Quality Score and warnings count have no source there, so
  they are not drawn (filed as a backend gap, not invented).
-->
<template>
  <BaseCard class="kb-health adv" data-testid="knowledge-health-summary" :aria-label="$t('knowledge.healthSummary.label')" role="region">
    <dl class="kb-health__stats">
      <div class="stat">
        <dt>{{ $t('knowledge.healthSummary.totalFacts') }}</dt>
        <dd>{{ count(vectorStats?.total_facts) }}</dd>
      </div>
      <div class="stat">
        <BaseTooltip :text="$t('knowledge.healthSummary.vectorsTip')" placement="top">
          <template #default="{ describedby }">
            <dt tabindex="0" :aria-describedby="describedby">{{ $t('knowledge.healthSummary.totalVectors') }}</dt>
          </template>
        </BaseTooltip>
        <dd>{{ count(vectorStats?.total_vectors) }}</dd>
      </div>
      <div class="stat">
        <dt>{{ $t('knowledge.healthSummary.databaseSize') }}</dt>
        <dd>{{ formatFileSize(vectorStats?.db_size ?? 0) }}</dd>
      </div>
    </dl>
    <BaseTooltip :text="ragTip" placement="top">
      <template #default="{ describedby }">
        <BaseBadge
          class="kb-health__rag"
          :variant="ragAvailable ? 'info' : 'neutral'"
          tabindex="0"
          :aria-describedby="describedby"
        >
          {{ ragAvailable ? $t('knowledge.healthSummary.ragAvailable') : $t('knowledge.healthSummary.ragUnavailable') }}
        </BaseBadge>
      </template>
    </BaseTooltip>
  </BaseCard>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseBadge, BaseCard, BaseTooltip } from '@autobot/ui'
import { formatFileSize } from '@/utils/formatHelpers'
import { useVectorStats } from '@/composables/knowledge/useVectorStats'

const { t } = useI18n()
const { vectorStats, refresh } = useVectorStats()

const ragAvailable = computed(() => vectorStats.value?.rag_available === true)
const ragTip = computed(() => (ragAvailable.value ? t('knowledge.healthSummary.ragTipOn') : t('knowledge.healthSummary.ragTipOff')))
const count = (n?: number) => (n ?? 0).toLocaleString()

onMounted(() => {
  void refresh()
})
</script>

<style scoped>
.kb-health :deep(.aui-card__body) {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--spacing-6);
}

.kb-health__stats {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-7);
  margin: 0;
}

.stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.stat dt {
  font-size: var(--text-sm);
  color: var(--muted);
}

.stat dd {
  margin: 0;
  font-size: var(--text-2xl);
  font-weight: 600;
  color: var(--text);
}

.kb-health__rag {
  margin-inline-start: auto;
}
</style>
