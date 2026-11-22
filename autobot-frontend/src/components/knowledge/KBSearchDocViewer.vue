<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  KBSearchDocViewer — the read-only document pane of the search results (#3296, split out of
  KBSearchResultPanel in #18244): the selected hit's title and meta, its full text with the
  query terms marked, and Copy.
-->
<template>
  <div class="flex min-h-0 min-w-0 flex-col" role="complementary" :aria-label="$t('knowledge.searchPanel.viewerLabel')">
    <div v-if="!result" class="viewer-empty flex flex-col items-center justify-center gap-2 px-4 py-8 text-center text-[var(--muted)]">
      <Icon name="hand-paper" aria-hidden="true" />
      <p class="m-0">{{ $t('knowledge.searchPanel.selectResult') }}</p>
      <p class="viewer-hint text-xs">{{ $t('knowledge.searchPanel.keyboardHint') }}</p>
    </div>

    <template v-else>
      <header class="viewer-header flex flex-col gap-1 border-b border-[var(--line)] px-4 py-3">
        <h4 class="viewer-title m-0 text-base font-semibold break-words text-[var(--text)]">{{ title }}</h4>
        <div class="viewer-meta flex flex-wrap items-center gap-3 text-xs text-[var(--muted)]">
          <span v-if="result.document?.category"><Icon name="folder" aria-hidden="true" /> {{ result.document.category }}</span>
          <span v-if="result.document?.type"><Icon name="tag" aria-hidden="true" /> {{ result.document.type }}</span>
          <span v-if="result.document?.updatedAt"><Icon name="clock" aria-hidden="true" /> {{ formatDate(result.document.updatedAt) }}</span>
          <BaseBadge :variant="scoreVariant(result.score)" size="sm">
            {{ $t('knowledge.searchPanel.match', { score: Math.round(result.score * 100) }) }}
          </BaseBadge>
        </div>
      </header>

      <div v-if="loading" class="viewer-loading flex items-center gap-2 p-4 text-[var(--muted)]" role="status">
        <BaseSpinner size="sm" />
        {{ $t('knowledge.searchPanel.loadingDocument') }}
      </div>
      <div v-else class="viewer-body min-h-0 flex-1 overflow-auto px-4 py-3">
        <pre class="viewer-content m-0 font-sans text-sm leading-relaxed break-words whitespace-pre-wrap text-[var(--text)]" v-html="highlightText(content, query)"></pre>
      </div>

      <footer class="viewer-footer flex items-center gap-3 border-t border-[var(--line)] px-4 py-3">
        <BaseButton variant="outline" size="sm" :disabled="!content" @click="copyContent">
          <Icon name="copy" aria-hidden="true" /> {{ $t('knowledge.searchPanel.copy') }}
        </BaseButton>
        <span v-if="copied" class="copy-success inline-flex items-center gap-1 text-sm text-[var(--ok-fg)]" role="status"><Icon name="check" aria-hidden="true" /> {{ $t('knowledge.searchPanel.copied') }}</span>
      </footer>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseBadge, BaseButton, BaseSpinner } from '@autobot/ui'
import Icon from '@/components/ui/Icon.vue'
import type { SearchResult } from '@/stores/useKnowledgeStore'
import { createLogger } from '@/utils/debugUtils'
import { createDateFormatter, formatManPageTitle } from '@/utils/formatHelpers'
import { highlightText, scoreVariant } from '@/composables/knowledge/searchHighlight'

const COPIED_MS = 2000

const props = defineProps<{
  result: SearchResult | null
  content: string
  query: string
  loading: boolean
}>()

const logger = createLogger('KBSearchDocViewer')
const { t } = useI18n()
const copied = ref(false)
const formatDate = createDateFormatter({ kind: 'date', invalidText: '' })

const title = computed(
  () =>
    formatManPageTitle(props.result?.document?.title, props.result?.document?.metadata?.factType, t) ||
    t('knowledge.searchPanel.untitled'),
)

async function copyContent(): Promise<void> {
  if (!props.content) return
  try {
    await navigator.clipboard.writeText(props.content)
    copied.value = true
    setTimeout(() => {
      copied.value = false
    }, COPIED_MS)
  } catch (err) {
    logger.error('Clipboard write failed:', err)
  }
}
</script>
