<template>
  <div class="template-gallery">
    <div class="gallery-header">
      <div class="search-box">
        <Icon name="search" />
        <input v-model="searchQuery" :placeholder="$t('workflow.templates.searchPlaceholder')" />
      </div>
      <div class="category-filters">
        <button v-for="cat in categories" :key="cat" class="filter-btn" :class="{ active: selectedCategory === cat }" @click="onCategoryChange(cat)">
          {{ cat }}
          <span v-if="getCategoryCount(cat)" class="count-badge">{{ getCategoryCount(cat) }}</span>
        </button>
      </div>
    </div>

    <!-- Error State -->
    <div v-if="apiError" class="error-state">
      <Icon name="exclamation-triangle" />
      <p>{{ apiError }}</p>
      <button class="btn-secondary" @click="retryLoad"><Icon name="redo" /> {{ $t('workflow.templates.retry') }}</button>
    </div>

    <div v-else-if="effectiveLoading" class="loading-state">
      <Icon name="spinner" :spin="true" />
      <span>{{ $t('workflow.templates.loading') }}</span>
    </div>

    <div v-else-if="filteredTemplates.length === 0" class="empty-state">
      <Icon name="clone" />
      <p>{{ $t('workflow.templates.noMatch') }}</p>
    </div>

    <div v-else class="templates-grid">
      <div v-for="template in filteredTemplates" :key="template.id" class="template-card" @click="$emit('select-template', template)">
        <div class="template-icon" :class="getCategoryClass(template.category)">
          <i :class="template.icon || getDefaultIcon(template.category)"></i>
        </div>
        <div class="template-info">
          <h4>{{ template.name }}</h4>
          <p>{{ template.description }}</p>
          <div class="template-meta">
            <span class="category-badge">{{ template.category }}</span>
            <span v-if="getStepsCount(template)" class="steps-count"><Icon name="list-ol" /> {{ $t('workflow.templates.stepsCount', { count: getStepsCount(template) }) }}</span>
            <span v-if="template.estimated_duration_minutes" class="duration"><Icon name="clock" /> {{ template.estimated_duration_minutes }}m</span>
          </div>
        </div>
        <div class="template-actions">
          <button class="btn-icon" @click.stop="openPreview(template)" :title="$t('workflow.templates.preview')" :aria-label="$t('workflow.templates.preview')"><Icon name="eye" /></button>
          <button class="btn-run" @click.stop="$emit('run-template', template)" :title="$t('workflow.templates.runNow')" :aria-label="$t('workflow.templates.runNow')"><Icon name="play" /></button>
        </div>
      </div>
    </div>

    <!-- Template Preview -->
    <Transition name="slide">
      <div v-if="previewTemplate" class="preview-panel">
        <div class="preview-header">
          <h3>{{ previewTemplate.name }}</h3>
          <button @click="previewTemplate = null" :aria-label="$t('common.close')"><Icon name="times" /></button>
        </div>
        <div class="preview-body">
          <p class="preview-desc">{{ previewTemplate.description }}</p>

          <!-- Template metadata -->
          <div v-if="previewTemplate.agents_involved?.length" class="preview-agents">
            <h4>{{ $t('workflow.templates.agentsInvolved') }}</h4>
            <div class="agent-tags">
              <span v-for="agent in previewTemplate.agents_involved" :key="agent" class="agent-tag">{{ agent }}</span>
            </div>
          </div>

          <!-- Required Credentials (#1415) -->
          <div v-if="(previewTemplate as any).required_secrets && Object.keys((previewTemplate as any).required_secrets).length" class="preview-secrets">
            <h4>Required Credentials</h4>
            <div class="secret-items">
              <div v-for="(meta, key) in (previewTemplate as any).required_secrets" :key="key" class="secret-item">
                <Icon name="key" />
                <div class="secret-info">
                  <span class="secret-name">{{ key }}</span>
                  <span class="secret-desc">{{ meta.description }}</span>
                </div>
                <span class="secret-scope" :class="meta.scope">{{ meta.scope }}</span>
              </div>
            </div>
          </div>

          <h4>{{ $t('workflow.templates.steps') }}</h4>
          <div class="preview-steps">
            <div v-for="(step, i) in getTemplateSteps(previewTemplate)" :key="i" class="preview-step">
              <span class="step-num">{{ i + 1 }}</span>
              <div class="step-content">
                <span class="step-desc">{{ step.description }}</span>
                <code v-if="step.command">{{ step.command }}</code>
                <code v-else-if="step.action">{{ step.action }}</code>
                <div class="step-meta">
                  <span v-if="step.agent_type" class="agent">{{ step.agent_type }}</span>
                  <span v-if="step.requires_approval"><Icon name="shield-alt" /> {{ $t('workflow.templates.requiresConfirmation') }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div class="preview-actions">
          <button class="btn-secondary" @click="$emit('select-template', previewTemplate)"><Icon name="edit" /> {{ $t('workflow.templates.editInCanvas') }}</button>
          <button class="btn-primary" @click="$emit('run-template', previewTemplate)"><Icon name="play" /> {{ $t('workflow.templates.runWorkflow') }}</button>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
// Issue #778 - Workflow Templates Enhancement

import { ref, computed, onMounted, watch } from 'vue'
import type { WorkflowTemplate } from '@/composables/useWorkflowBuilder'
import { useWorkflowTemplates } from '@/composables/useWorkflowTemplates'
import type { WorkflowTemplateSummary, TemplateCategory, TemplateStep } from '@/types/workflowTemplates'
import Icon from '@/components/ui/Icon.vue'

// Combined template type for flexibility
type AnyTemplate = WorkflowTemplate | WorkflowTemplateSummary

// Props for backward compatibility - can receive templates from parent
const props = withDefaults(defineProps<{
  templates?: WorkflowTemplate[]
  loading?: boolean
  useApi?: boolean
}>(), {
  templates: () => [],
  loading: false,
  useApi: true
})

defineEmits<{
  (e: 'select-template', t: AnyTemplate): void
  (e: 'run-template', t: AnyTemplate): void
}>()

// API composable
const {
  templates: apiTemplates,
  categories: apiCategories,
  loading: apiLoading,
  error: apiError,
  fetchTemplates,
  fetchCategories,
  fetchTemplateDetail
} = useWorkflowTemplates()

// Local state
const searchQuery = ref('')
const selectedCategory = ref('All')
const previewTemplate = ref<AnyTemplate | null>(null)
const searchResults = ref<WorkflowTemplateSummary[]>([])
const isSearching = ref(false)

// Determine data source - API or props
const effectiveTemplates = computed((): AnyTemplate[] => {
  if (isSearching.value && searchResults.value.length > 0) {
    return searchResults.value
  }
  if (props.useApi && apiTemplates.value.length > 0) {
    return apiTemplates.value
  }
  return props.templates
})

const effectiveLoading = computed(() => {
  return props.useApi ? apiLoading.value : props.loading
})

// Categories from API or computed from templates
const categories = computed(() => {
  if (props.useApi && apiCategories.value.length > 0) {
    return ['All', ...apiCategories.value.map(c => c.display_name)]
  }
  return ['All', ...new Set(effectiveTemplates.value.map(t => t.category))]
})

// Get category count for display
const getCategoryCount = (cat: string): number | null => {
  if (cat === 'All') return effectiveTemplates.value.length || null
  if (props.useApi && apiCategories.value.length > 0) {
    const category = apiCategories.value.find(c => c.display_name === cat)
    return category?.template_count || null
  }
  return effectiveTemplates.value.filter(t => t.category === cat).length || null
}

// Get category key for API filter
const getCategoryKey = (displayName: string): TemplateCategory | undefined => {
  if (displayName === 'All') return undefined
  const cat = apiCategories.value.find(c => c.display_name === displayName)
  return cat?.name as TemplateCategory | undefined
}

// Filter templates locally
const filteredTemplates = computed(() => {
  let result = effectiveTemplates.value
  if (selectedCategory.value !== 'All' && !props.useApi) {
    result = result.filter(t => t.category === selectedCategory.value)
  }
  if (searchQuery.value && !isSearching.value) {
    const q = searchQuery.value.toLowerCase()
    result = result.filter(t => t.name.toLowerCase().includes(q) || t.description.toLowerCase().includes(q))
  }
  return result
})

// Handle category change - fetch from API with filter
const onCategoryChange = async (cat: string) => {
  selectedCategory.value = cat
  searchQuery.value = ''
  isSearching.value = false
  searchResults.value = []
  if (props.useApi) {
    const categoryKey = getCategoryKey(cat)
    await fetchTemplates(categoryKey)
  }
}

// Handle search with debounce
let searchTimeout: ReturnType<typeof setTimeout> | null = null
watch(searchQuery, (query) => {
  if (searchTimeout) clearTimeout(searchTimeout)
  if (!query.trim()) {
    isSearching.value = false
    searchResults.value = []
    return
  }
  searchTimeout = setTimeout(async () => {
    if (props.useApi && query.trim()) {
      isSearching.value = true
      const { searchTemplates } = useWorkflowTemplates()
      searchResults.value = await searchTemplates(query)
    }
  }, 300)
})

// Open preview - fetch full detail if steps missing (#1415)
const openPreview = async (template: AnyTemplate) => {
  previewTemplate.value = template
  if (!('steps' in template) || !Array.isArray(template.steps) || template.steps.length === 0) {
    const detail = await fetchTemplateDetail(template.id)
    if (detail) {
      previewTemplate.value = detail
    }
  }
}

// Get steps count - handle both API and local templates (#1415)
const getStepsCount = (template: AnyTemplate): number => {
  if ('steps' in template && Array.isArray(template.steps)) {
    return template.steps.length
  }
  if ('step_count' in template && typeof template.step_count === 'number') {
    return template.step_count
  }
  return 0
}

// Get template steps for preview — backend emits canonical fields after #6951 Phase 2F.
// Tolerates both ``WorkflowTemplate`` (canonical task_id / requires_approval) and
// ``WorkflowTemplateSummary`` shapes via partial-cast fallbacks for in-flight data.
const getTemplateSteps = (template: AnyTemplate): TemplateStep[] => {
  if ('steps' in template && Array.isArray(template.steps)) {
    return template.steps.map((step, index): TemplateStep => {
      const s = step as Partial<TemplateStep>
      return {
        task_id: s.task_id ?? `step-${index}`,
        agent_type: s.agent_type ?? '',
        action: s.action ?? '',
        command: s.command ?? null,
        description: step.description,
        requires_approval: s.requires_approval ?? false,
        dependencies: s.dependencies ?? [],
        inputs: s.inputs ?? {},
        estimated_duration_seconds: s.estimated_duration_seconds ?? 0,
        prompt: s.prompt ?? null,
        tools_allowed: s.tools_allowed ?? null,
        tools_denied: s.tools_denied ?? [],
      }
    })
  }
  return []
}

// Get default icon based on category (#1415)
const getDefaultIcon = (category: string): string => {
  const icons: Record<string, string> = {
    security: 'fas fa-shield-alt',
    research: 'fas fa-search',
    development: 'fas fa-code',
    system_admin: 'fas fa-server',
    analysis: 'fas fa-chart-bar',
    community: 'fas fa-users',
    System: 'fas fa-cog',
    Development: 'fas fa-code',
    Security: 'fas fa-lock',
    Backup: 'fas fa-database',
    Community: 'fas fa-users'
  }
  return icons[category] || 'fas fa-tasks'
}

// Category styling (#1415)
const getCategoryClass = (cat: string) => ({
  system: cat === 'System' || cat === 'system_admin',
  development: cat === 'Development' || cat === 'development',
  security: cat === 'Security' || cat === 'security',
  backup: cat === 'Backup',
  research: cat === 'Research' || cat === 'research',
  analysis: cat === 'Analysis' || cat === 'analysis',
  community: cat === 'Community' || cat === 'community'
})

// Retry loading on error
const retryLoad = async () => {
  await Promise.all([fetchTemplates(), fetchCategories()])
}

// Initialize on mount
onMounted(async () => {
  if (props.useApi) {
    await Promise.all([fetchTemplates(), fetchCategories()])
  }
})
</script>

<style scoped>
.template-gallery { height: 100%; display: flex; flex-direction: column; }
.gallery-header { padding: var(--spacing-0) var(--spacing-0) var(--spacing-5); display: flex; flex-direction: column; gap: var(--spacing-4); }
.search-box { display: flex; align-items: center; gap: var(--spacing-2-5); padding: var(--spacing-2-5) var(--spacing-3-5); background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: var(--radius-lg); }
.search-box i { color: var(--text-muted); }
.search-box input { flex: 1; background: none; border: none; color: var(--text-primary); font-size: var(--text-sm); outline: none; }
.search-box input:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 2px; }
.category-filters { display: flex; gap: var(--spacing-2); flex-wrap: wrap; }
.filter-btn { padding: var(--spacing-1-5) var(--spacing-3-5); background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: var(--radius-2xl); color: var(--text-secondary); font-size: var(--text-sm); cursor: pointer; transition: all 0.15s; display: flex; align-items: center; gap: var(--spacing-1-5); }
.filter-btn:hover { background: var(--bg-hover); }
.filter-btn.active { background: var(--color-primary); color: var(--text-on-primary); border-color: var(--color-primary); }
.count-badge { font-size: var(--text-xs); padding: var(--spacing-px) var(--spacing-1-5); background: rgba(255,255,255,0.2); border-radius: var(--radius-xl); }

.loading-state, .empty-state, .error-state { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: var(--spacing-3); color: var(--text-tertiary); }
.empty-state i, .error-state i { font-size: var(--text-5xl); }
.error-state { color: var(--color-error); }
.error-state p { color: var(--text-secondary); }

.templates-grid { flex: 1; display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: var(--spacing-4); overflow-y: auto; padding-bottom: var(--spacing-5); }
.template-card { display: flex; gap: var(--spacing-4); padding: var(--spacing-4); background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: var(--radius-xl); cursor: pointer; transition: all 0.2s; }
.template-card:hover { border-color: var(--color-primary); box-shadow: 0 4px 12px rgba(0,0,0,0.1); }

.template-icon { width: 48px; height: 48px; border-radius: var(--radius-xl); display: flex; align-items: center; justify-content: center; font-size: var(--text-xl); background: var(--bg-tertiary); color: var(--text-secondary); flex-shrink: 0; }
.template-icon.system { background: var(--color-info-bg); color: var(--color-info); }
.template-icon.development { background: var(--color-primary-bg); color: var(--color-primary); }
.template-icon.security { background: var(--color-warning-bg); color: var(--color-warning); }
.template-icon.backup { background: var(--color-success-bg); color: var(--color-success); }
.template-icon.research { background: var(--color-info-bg); color: var(--color-info); }
.template-icon.analysis { background: var(--color-info-bg); color: var(--color-info); }
.template-icon.community { background: var(--color-success-bg); color: var(--color-success); }

.template-info { flex: 1; min-width: 0; }
.template-info h4 { margin: var(--spacing-0) var(--spacing-0) var(--spacing-1); font-size: 15px; color: var(--text-primary); }
.template-info p { margin: var(--spacing-0) var(--spacing-0) var(--spacing-2-5); font-size: var(--text-sm); color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.template-meta { display: flex; gap: var(--spacing-3); font-size: var(--text-xs); flex-wrap: wrap; }
.category-badge { padding: var(--spacing-0-5) var(--spacing-2); background: var(--bg-tertiary); color: var(--text-tertiary); border-radius: var(--radius-xl); }
.steps-count, .duration { color: var(--text-tertiary); display: flex; align-items: center; gap: var(--spacing-1); }

.template-actions { display: flex; flex-direction: column; gap: var(--spacing-2); }
.btn-icon { width: 32px; height: 32px; background: var(--bg-tertiary); border: none; border-radius: var(--radius-md); color: var(--text-secondary); cursor: pointer; }
.btn-icon:hover { background: var(--bg-hover); color: var(--text-primary); }
.btn-run { width: 32px; height: 32px; background: var(--color-success); border: none; border-radius: var(--radius-md); color: white; cursor: pointer; }
.btn-run:hover { filter: brightness(1.1); }

.preview-panel { position: fixed; right: 0; top: 0; bottom: 0; width: 400px; background: var(--bg-secondary); border-left: 1px solid var(--border-default); display: flex; flex-direction: column; z-index: 50; box-shadow: -4px 0 20px rgba(0,0,0,0.1); }
.preview-header { display: flex; justify-content: space-between; align-items: center; padding: var(--spacing-5); border-bottom: 1px solid var(--border-default); }
.preview-header h3 { margin: var(--spacing-0); font-size: var(--text-base); color: var(--text-primary); }
.preview-header button { padding: var(--spacing-1-5); background: transparent; border: none; color: var(--text-tertiary); cursor: pointer; }
.preview-body { flex: 1; overflow-y: auto; padding: var(--spacing-5); }
.preview-desc { margin: var(--spacing-0) var(--spacing-0) var(--spacing-5); color: var(--text-secondary); }
.preview-body h4 { margin: var(--spacing-0) var(--spacing-0) var(--spacing-3); font-size: var(--text-sm); color: var(--text-tertiary); text-transform: uppercase; }

.preview-agents { margin-bottom: var(--spacing-5); }
.agent-tags { display: flex; flex-wrap: wrap; gap: var(--spacing-1-5); }
.agent-tag { padding: var(--spacing-1) var(--spacing-2-5); background: var(--color-primary-bg); color: var(--color-primary); border-radius: var(--radius-xl); font-size: var(--text-xs); }

.preview-secrets { margin-bottom: var(--spacing-5); }
.secret-items { display: flex; flex-direction: column; gap: var(--spacing-2); }
.secret-item { display: flex; align-items: center; gap: var(--spacing-2-5); padding: var(--spacing-2) var(--spacing-3); background: var(--bg-tertiary); border-radius: var(--radius-lg); font-size: var(--text-sm); }
.secret-item i { color: var(--text-tertiary); font-size: var(--text-xs); }
.secret-info { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.secret-name { font-weight: 600; color: var(--text-primary); font-size: var(--text-xs); }
.secret-desc { color: var(--text-tertiary); font-size: var(--text-xs); }
.secret-scope { padding: var(--spacing-0-5) var(--spacing-1-5); border-radius: var(--radius-lg); font-size: var(--text-xs); background: var(--bg-secondary); color: var(--text-tertiary); }
.secret-scope.write { background: var(--color-warning-bg); color: var(--color-warning); }
.secret-scope.read { background: var(--color-success-bg); color: var(--color-success); }

.preview-steps { display: flex; flex-direction: column; gap: var(--spacing-3); }
.preview-step { display: flex; gap: var(--spacing-3); padding: var(--spacing-3); background: var(--bg-tertiary); border-radius: var(--radius-lg); }
.step-num { width: 24px; height: 24px; background: var(--color-primary); color: white; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: var(--text-xs); font-weight: 600; flex-shrink: 0; }
.step-content { flex: 1; min-width: 0; }
.step-desc { display: block; font-size: var(--text-sm); color: var(--text-primary); margin-bottom: var(--spacing-1); }
.step-content code { display: block; padding: var(--spacing-1-5) var(--spacing-2); background: var(--bg-primary); border-radius: var(--radius-default); font-size: var(--text-xs); color: var(--text-secondary); overflow-x: auto; }
.step-meta { display: flex; gap: var(--spacing-2-5); margin-top: var(--spacing-2); font-size: var(--text-xs); }
.step-meta .risk { padding: var(--spacing-0-5) var(--spacing-1-5); border-radius: var(--radius-lg); }
.step-meta .risk.low { background: var(--color-success-bg); color: var(--color-success); }
.step-meta .risk.medium { background: var(--color-warning-bg); color: var(--color-warning); }
.step-meta .risk.high, .step-meta .risk.critical { background: var(--color-error-bg); color: var(--color-error); }
.step-meta span { color: var(--text-tertiary); display: flex; align-items: center; gap: var(--spacing-1); }
.preview-actions { padding: var(--spacing-4) var(--spacing-5); border-top: 1px solid var(--border-default); display: flex; gap: var(--spacing-3); }
.preview-actions .btn-secondary, .preview-actions .btn-primary { flex: 1; justify-content: center; }

.btn-primary { padding: var(--spacing-2-5) var(--spacing-4); background: var(--color-primary); color: var(--text-on-primary); border: none; border-radius: var(--radius-md); font-size: var(--text-sm); font-weight: 500; cursor: pointer; display: inline-flex; align-items: center; gap: var(--spacing-2); }
.btn-primary:hover { filter: brightness(1.1); }
.btn-secondary { padding: var(--spacing-2-5) var(--spacing-4); background: var(--bg-tertiary); color: var(--text-secondary); border: 1px solid var(--border-default); border-radius: var(--radius-md); font-size: var(--text-sm); cursor: pointer; display: inline-flex; align-items: center; gap: var(--spacing-2); }
.btn-secondary:hover { background: var(--bg-hover); }

.slide-enter-active, .slide-leave-active { transition: transform 0.25s ease; }
.slide-enter-from, .slide-leave-to { transform: translateX(100%); }
</style>
