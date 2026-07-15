<template>
  <div class="scrape-template-panel">
    <!-- Header -->
    <div class="panel-header flex items-center justify-between p-3 border-b border-autobot-border">
      <div class="flex items-center gap-2">
        <Icon name="layer-group" class="text-autobot-text-secondary" />
        <span class="font-medium text-sm text-autobot-text-primary">{{ $t('browser.scrapeTemplates.title') }}</span>
        <span v-if="templates.length" class="text-xs text-autobot-text-muted bg-autobot-bg-tertiary px-1.5 py-0.5 rounded-full">{{ templates.length }}</span>
      </div>
      <button
        @click="load"
        :disabled="isLoading"
        class="browser-btn text-autobot-text-muted hover:text-autobot-text-primary"
        :title="$t('browser.scrapeTemplates.refresh')"
        :aria-label="$t('browser.scrapeTemplates.refresh')"
      >
        <Icon :name="isLoading ? 'spinner' : 'sync-alt'" :class="isLoading ? 'animate-spin' : ''" />
      </button>
    </div>

    <!-- Loading -->
    <div v-if="isLoading && !templates.length" class="flex items-center justify-center p-8">
      <Icon name="spinner" class="animate-spin text-autobot-text-muted text-2xl" />
    </div>

    <!-- Empty state -->
    <div v-else-if="!templates.length" class="empty-state p-6 text-center">
      <Icon name="layer-group" class="text-4xl text-autobot-text-muted mb-3" />
      <p class="text-sm font-medium text-autobot-text-primary mb-1">{{ $t('browser.scrapeTemplates.emptyTitle') }}</p>
      <p class="text-xs text-autobot-text-muted">{{ $t('browser.scrapeTemplates.emptyMessage') }}</p>
    </div>

    <!-- Template list -->
    <div v-else class="template-list overflow-y-auto">
      <div
        v-for="template in templates"
        :key="template.id"
        class="template-item p-3 border-b border-autobot-border hover:bg-autobot-bg-secondary transition-colors"
      >
        <div class="flex items-start justify-between gap-2">
          <div class="flex-1 min-w-0">
            <div class="text-sm font-medium text-autobot-text-primary truncate">{{ template.name }}</div>
            <div class="text-xs text-autobot-text-muted truncate mt-0.5">{{ template.url_pattern }}</div>
            <div class="flex items-center gap-1 mt-1 flex-wrap">
              <span
                v-for="region in template.regions.slice(0, 3)"
                :key="region.label"
                class="text-xs px-1.5 py-0.5 rounded bg-autobot-bg-tertiary text-autobot-text-secondary"
              >{{ region.label }}</span>
              <span
                v-if="template.regions.length > 3"
                class="text-xs text-autobot-text-muted"
              >+{{ template.regions.length - 3 }}</span>
            </div>
          </div>

          <!-- Actions -->
          <div class="flex items-center gap-1 shrink-0">
            <button
              @click="openRunDialog(template)"
              class="action-btn text-color-primary"
              :title="$t('browser.scrapeTemplates.run')"
              :aria-label="$t('browser.scrapeTemplates.run')"
            >
              <Icon name="play" />
            </button>
            <button
              @click="duplicateTemplate(template)"
              :disabled="isDuplicating === template.id"
              class="action-btn"
              :title="$t('browser.scrapeTemplates.duplicate')"
              :aria-label="$t('browser.scrapeTemplates.duplicate')"
            >
              <Icon :name="isDuplicating === template.id ? 'spinner' : 'copy'" :class="isDuplicating === template.id ? 'animate-spin' : ''" />
            </button>
            <button
              @click="confirmDelete(template)"
              class="action-btn text-red-500"
              :title="$t('browser.scrapeTemplates.delete')"
              :aria-label="$t('browser.scrapeTemplates.delete')"
            >
              <Icon name="trash" />
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Run dialog -->
    <div
      v-if="runDialog.open"
      class="run-dialog absolute inset-0 bg-autobot-bg-primary z-30 flex flex-col"
    >
      <div class="flex items-center gap-2 p-3 border-b border-autobot-border">
        <button
          @click="closeRunDialog"
          class="browser-btn"
          :aria-label="$t('common.back')"
        >
          <Icon name="arrow-left" />
        </button>
        <span class="font-medium text-sm text-autobot-text-primary truncate">{{ runDialog.template?.name }}</span>
      </div>

      <div class="p-3 flex-1 flex flex-col gap-3 overflow-y-auto">
        <div>
          <label class="block text-xs font-medium text-autobot-text-secondary mb-1">
            {{ $t('browser.scrapeTemplates.targetUrl') }}
          </label>
          <div class="flex gap-2">
            <input
              v-model="runDialog.url"
              @keyup.enter="runTemplate"
              type="url"
              class="flex-1 px-3 py-2 text-sm bg-autobot-bg-secondary border border-autobot-border rounded-lg outline-hidden focus:border-color-primary"
              :placeholder="runDialog.template?.url_pattern || 'https://...'"
            />
            <button
              @click="runTemplate"
              :disabled="!runDialog.url.trim() || isRunning"
              class="px-3 py-2 text-sm rounded-lg font-medium transition-colors"
              style="background: var(--color-primary); color: #fff"
            >
              <Icon :name="isRunning ? 'spinner' : 'play'" :class="isRunning ? 'animate-spin mr-1' : 'mr-1'" />
              {{ isRunning ? $t('browser.scrapeTemplates.running') : $t('browser.scrapeTemplates.runButton') }}
            </button>
          </div>
        </div>

        <!-- Run error -->
        <div v-if="runDialog.error" class="p-3 rounded-lg text-sm" style="background: var(--color-error-bg); color: var(--color-error)">
          <Icon name="exclamation-triangle" class="mr-1" />
          {{ runDialog.error }}
        </div>

        <!-- Run results -->
        <div v-if="runDialog.results" class="flex-1">
          <div class="text-xs font-medium text-autobot-text-secondary mb-2">
            {{ $t('browser.scrapeTemplates.extractedResults') }}
          </div>
          <div class="space-y-2">
            <div
              v-for="(value, label) in runDialog.results"
              :key="label"
              class="result-item p-2 rounded-lg bg-autobot-bg-secondary border border-autobot-border"
            >
              <div class="text-xs font-medium text-autobot-text-secondary mb-1">{{ label }}</div>
              <div class="text-sm text-autobot-text-primary break-words">
                {{ value !== null ? value : $t('browser.scrapeTemplates.noValue') }}
              </div>
            </div>
          </div>
        </div>

        <!-- Empty results -->
        <div v-if="runDialog.results && Object.keys(runDialog.results).length === 0" class="text-sm text-autobot-text-muted text-center py-4">
          {{ $t('browser.scrapeTemplates.noResults') }}
        </div>
      </div>
    </div>

    <!-- Delete confirmation -->
    <div
      v-if="deleteConfirm.open"
      class="absolute inset-0 bg-black/50 z-40 flex items-end justify-center p-4"
    >
      <div class="bg-autobot-bg-elevated rounded-xl w-full max-w-sm p-4 shadow-xl">
        <p class="text-sm text-autobot-text-primary mb-4">
          {{ $t('browser.scrapeTemplates.deleteConfirm', { name: deleteConfirm.template?.name }) }}
        </p>
        <div class="flex gap-2 justify-end">
          <button
            @click="deleteConfirm.open = false"
            class="px-4 py-2 text-sm rounded-lg border border-autobot-border bg-autobot-bg-secondary text-autobot-text-secondary hover:bg-autobot-bg-tertiary"
          >
            {{ $t('common.cancel') }}
          </button>
          <button
            @click="doDelete"
            :disabled="isDeleting"
            class="px-4 py-2 text-sm rounded-lg font-medium"
            style="background: var(--color-error); color: #fff"
          >
            <Icon v-if="isDeleting" name="spinner" class="animate-spin mr-1" />
            {{ $t('common.delete') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import { ref, onMounted } from 'vue'
import { useScrapeTemplates } from '@/composables/browser/useScrapeTemplates'
import type { ScrapeTemplate } from '@/composables/browser/useScrapeTemplates'
import { createLogger } from '@/utils/debugUtils'
import Icon from '@/components/ui/Icon.vue'

const logger = createLogger('ScrapeTemplatePanel')

export default {
  name: 'ScrapeTemplatePanel',
  components: { Icon },
  setup() {
    const api = useScrapeTemplates()

    const templates = ref<ScrapeTemplate[]>([])
    const isLoading = ref(false)
    const isDuplicating = ref<string | null>(null)
    const isDeleting = ref(false)
    const isRunning = ref(false)

    const runDialog = ref<{
      open: boolean
      template: ScrapeTemplate | null
      url: string
      results: Record<string, string | null> | null
      error: string | null
    }>({
      open: false,
      template: null,
      url: '',
      results: null,
      error: null,
    })

    const deleteConfirm = ref<{
      open: boolean
      template: ScrapeTemplate | null
    }>({
      open: false,
      template: null,
    })

    async function load() {
      isLoading.value = true
      try {
        templates.value = await api.listTemplates()
      } finally {
        isLoading.value = false
      }
    }

    function openRunDialog(template: ScrapeTemplate) {
      runDialog.value = {
        open: true,
        template,
        url: template.url_pattern.startsWith('http') ? template.url_pattern : '',
        results: null,
        error: null,
      }
    }

    function closeRunDialog() {
      runDialog.value.open = false
    }

    async function runTemplate() {
      if (!runDialog.value.template || !runDialog.value.url.trim()) return
      isRunning.value = true
      runDialog.value.error = null
      runDialog.value.results = null
      try {
        const resp = await api.runTemplate(runDialog.value.template.id, runDialog.value.url.trim())
        runDialog.value.results = resp.results
      } catch (err) {
        logger.warn('Template run failed', err)
        runDialog.value.error = (err as { message?: string })?.message ?? String(err)
      } finally {
        isRunning.value = false
      }
    }

    async function duplicateTemplate(template: ScrapeTemplate) {
      isDuplicating.value = template.id
      try {
        const copy = await api.duplicateTemplate(template)
        templates.value = [copy, ...templates.value]
      } catch (err) {
        logger.warn('Duplicate failed', err)
      } finally {
        isDuplicating.value = null
      }
    }

    function confirmDelete(template: ScrapeTemplate) {
      deleteConfirm.value = { open: true, template }
    }

    async function doDelete() {
      if (!deleteConfirm.value.template) return
      isDeleting.value = true
      try {
        await api.deleteTemplate(deleteConfirm.value.template.id)
        templates.value = templates.value.filter(t => t.id !== deleteConfirm.value.template!.id)
        deleteConfirm.value.open = false
      } catch (err) {
        logger.warn('Delete failed', err)
      } finally {
        isDeleting.value = false
      }
    }

    onMounted(load)

    return {
      templates,
      isLoading,
      isDuplicating,
      isDeleting,
      isRunning,
      runDialog,
      deleteConfirm,
      load,
      openRunDialog,
      closeRunDialog,
      runTemplate,
      duplicateTemplate,
      confirmDelete,
      doDelete,
    }
  },
}
</script>

<style scoped>
.scrape-template-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  position: relative;
  background: var(--bg-primary);
}

.panel-header {
  flex-shrink: 0;
}

.template-list {
  flex: 1;
  min-height: 0;
}

.browser-btn {
  padding: var(--spacing-1-5) var(--spacing-2);
  border: none;
  background: transparent;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background-color var(--duration-200);
  font-size: var(--text-sm);
}

.browser-btn:hover {
  background-color: var(--bg-tertiary-transparent);
}

.action-btn {
  padding: var(--spacing-1) var(--spacing-1-5);
  border: none;
  background: transparent;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background-color var(--duration-200);
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.action-btn:hover {
  background-color: var(--bg-tertiary-transparent);
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
