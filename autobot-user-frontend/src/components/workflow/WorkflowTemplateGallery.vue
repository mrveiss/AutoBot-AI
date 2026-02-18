<template>
  <div class="template-gallery">
    <div class="gallery-header">
      <div class="search-box">
        <i class="fas fa-search"></i>
        <input v-model="searchQuery" placeholder="Search templates..." />
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
      <i class="fas fa-exclamation-triangle"></i>
      <p>{{ apiError }}</p>
      <button class="btn-secondary" @click="retryLoad"><i class="fas fa-redo"></i> Retry</button>
    </div>

    <div v-else-if="effectiveLoading" class="loading-state">
      <i class="fas fa-spinner fa-spin"></i>
      <span>Loading templates...</span>
    </div>

    <div v-else-if="filteredTemplates.length === 0" class="empty-state">
      <i class="fas fa-clone"></i>
      <p>No templates match your search</p>
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
            <span v-if="getStepsCount(template)" class="steps-count"><i class="fas fa-list-ol"></i> {{ getStepsCount(template) }} steps</span>
            <span v-if="template.estimated_duration_minutes" class="duration"><i class="fas fa-clock"></i> {{ template.estimated_duration_minutes }}m</span>
          </div>
        </div>
        <div class="template-actions">
          <button class="btn-icon" @click.stop="previewTemplate = template" title="Preview"><i class="fas fa-eye"></i></button>
          <button class="btn-run" @click.stop="$emit('run-template', template)" title="Run Now"><i class="fas fa-play"></i></button>
        </div>
      </div>
    </div>

    <!-- Template Preview -->
    <Transition name="slide">
      <div v-if="previewTemplate" class="preview-panel">
        <div class="preview-header">
          <h3>{{ previewTemplate.name }}</h3>
          <button @click="previewTemplate = null"><i class="fas fa-times"></i></button>
        </div>
        <div class="preview-body">
          <p class="preview-desc">{{ previewTemplate.description }}</p>

          <!-- Template metadata -->
          <div v-if="previewTemplate.agents_involved?.length" class="preview-agents">
            <h4>Agents Involved</h4>
            <div class="agent-tags">
              <span v-for="agent in previewTemplate.agents_involved" :key="agent" class="agent-tag">{{ agent }}</span>
            </div>
          </div>

          <h4>Steps</h4>
          <div class="preview-steps">
            <div v-for="(step, i) in getTemplateSteps(previewTemplate)" :key="i" class="preview-step">
              <span class="step-num">{{ i + 1 }}</span>
              <div class="step-content">
                <span class="step-desc">{{ step.description }}</span>
                <code v-if="step.command">{{ step.command }}</code>
                <div class="step-meta">
                  <span v-if="step.risk_level" class="risk" :class="step.risk_level">{{ step.risk_level }}</span>
                  <span v-if="step.requires_confirmation"><i class="fas fa-shield-alt"></i> Requires confirmation</span>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div class="preview-actions">
          <button class="btn-secondary" @click="$emit('select-template', previewTemplate)"><i class="fas fa-edit"></i> Edit in Canvas</button>
          <button class="btn-primary" @click="$emit('run-template', previewTemplate)"><i class="fas fa-play"></i> Run Workflow</button>
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
  fetchCategories
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

// Get steps count - handle both API and local templates
const getStepsCount = (template: AnyTemplate): number => {
  if ('steps' in template && Array.isArray(template.steps)) {
    return template.steps.length
  }
  return 0
}

// Get template steps for preview
const getTemplateSteps = (template: AnyTemplate): TemplateStep[] => {
  if ('steps' in template && Array.isArray(template.steps)) {
    return template.steps.map((step, index): TemplateStep => ({
      step_id: (step as Partial<TemplateStep>).step_id ?? `step-${index}`,
      description: step.description,
      command: step.command,
      requires_confirmation: step.requires_confirmation,
      risk_level: step.risk_level as TemplateStep['risk_level'],
      estimated_duration_seconds: (step as Partial<TemplateStep>).estimated_duration_seconds ?? 0,
      agent_type: (step as Partial<TemplateStep>).agent_type,
    }))
  }
  return []
}

// Get default icon based on category
const getDefaultIcon = (category: string): string => {
  const icons: Record<string, string> = {
    security: 'fas fa-shield-alt',
    research: 'fas fa-search',
    development: 'fas fa-code',
    system_admin: 'fas fa-server',
    analysis: 'fas fa-chart-bar',
    System: 'fas fa-cog',
    Development: 'fas fa-code',
    Security: 'fas fa-lock',
    Backup: 'fas fa-database'
  }
  return icons[category] || 'fas fa-tasks'
}

// Category styling
const getCategoryClass = (cat: string) => ({
  system: cat === 'System' || cat === 'system_admin',
  development: cat === 'Development' || cat === 'development',
  security: cat === 'Security' || cat === 'security',
  backup: cat === 'Backup',
  research: cat === 'Research' || cat === 'research',
  analysis: cat === 'Analysis' || cat === 'analysis'
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
.gallery-header { padding: 0 0 20px; display: flex; flex-direction: column; gap: 16px; }
.search-box { display: flex; align-items: center; gap: 10px; padding: 10px 14px; background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: 8px; }
.search-box i { color: var(--text-muted); }
.search-box input { flex: 1; background: none; border: none; color: var(--text-primary); font-size: 14px; outline: none; }
.category-filters { display: flex; gap: 8px; flex-wrap: wrap; }
.filter-btn { padding: 6px 14px; background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: 20px; color: var(--text-secondary); font-size: 13px; cursor: pointer; transition: all 0.15s; display: flex; align-items: center; gap: 6px; }
.filter-btn:hover { background: var(--bg-hover); }
.filter-btn.active { background: var(--color-primary); color: var(--text-on-primary); border-color: var(--color-primary); }
.count-badge { font-size: 11px; padding: 1px 6px; background: rgba(255,255,255,0.2); border-radius: 10px; }

.loading-state, .empty-state, .error-state { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; color: var(--text-tertiary); }
.empty-state i, .error-state i { font-size: 48px; }
.error-state { color: var(--color-error); }
.error-state p { color: var(--text-secondary); }

.templates-grid { flex: 1; display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; overflow-y: auto; padding-bottom: 20px; }
.template-card { display: flex; gap: 16px; padding: 16px; background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: 10px; cursor: pointer; transition: all 0.2s; }
.template-card:hover { border-color: var(--color-primary); box-shadow: 0 4px 12px rgba(0,0,0,0.1); }

.template-icon { width: 48px; height: 48px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 20px; background: var(--bg-tertiary); color: var(--text-secondary); flex-shrink: 0; }
.template-icon.system { background: var(--color-info-bg); color: var(--color-info); }
.template-icon.development { background: var(--color-primary-bg); color: var(--color-primary); }
.template-icon.security { background: var(--color-warning-bg); color: var(--color-warning); }
.template-icon.backup { background: var(--color-success-bg); color: var(--color-success); }
.template-icon.research { background: #e8f4fd; color: #0077b6; }
.template-icon.analysis { background: #f3e8ff; color: #7c3aed; }

.template-info { flex: 1; min-width: 0; }
.template-info h4 { margin: 0 0 4px; font-size: 15px; color: var(--text-primary); }
.template-info p { margin: 0 0 10px; font-size: 13px; color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.template-meta { display: flex; gap: 12px; font-size: 12px; flex-wrap: wrap; }
.category-badge { padding: 2px 8px; background: var(--bg-tertiary); color: var(--text-tertiary); border-radius: 10px; }
.steps-count, .duration { color: var(--text-tertiary); display: flex; align-items: center; gap: 4px; }

.template-actions { display: flex; flex-direction: column; gap: 8px; }
.btn-icon { width: 32px; height: 32px; background: var(--bg-tertiary); border: none; border-radius: 6px; color: var(--text-secondary); cursor: pointer; }
.btn-icon:hover { background: var(--bg-hover); color: var(--text-primary); }
.btn-run { width: 32px; height: 32px; background: var(--color-success); border: none; border-radius: 6px; color: white; cursor: pointer; }
.btn-run:hover { filter: brightness(1.1); }

.preview-panel { position: fixed; right: 0; top: 0; bottom: 0; width: 400px; background: var(--bg-secondary); border-left: 1px solid var(--border-default); display: flex; flex-direction: column; z-index: 50; box-shadow: -4px 0 20px rgba(0,0,0,0.1); }
.preview-header { display: flex; justify-content: space-between; align-items: center; padding: 20px; border-bottom: 1px solid var(--border-default); }
.preview-header h3 { margin: 0; font-size: 16px; color: var(--text-primary); }
.preview-header button { padding: 6px; background: transparent; border: none; color: var(--text-tertiary); cursor: pointer; }
.preview-body { flex: 1; overflow-y: auto; padding: 20px; }
.preview-desc { margin: 0 0 20px; color: var(--text-secondary); }
.preview-body h4 { margin: 0 0 12px; font-size: 13px; color: var(--text-tertiary); text-transform: uppercase; }

.preview-agents { margin-bottom: 20px; }
.agent-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.agent-tag { padding: 4px 10px; background: var(--color-primary-bg); color: var(--color-primary); border-radius: 12px; font-size: 12px; }

.preview-steps { display: flex; flex-direction: column; gap: 12px; }
.preview-step { display: flex; gap: 12px; padding: 12px; background: var(--bg-tertiary); border-radius: 8px; }
.step-num { width: 24px; height: 24px; background: var(--color-primary); color: white; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 600; flex-shrink: 0; }
.step-content { flex: 1; min-width: 0; }
.step-desc { display: block; font-size: 13px; color: var(--text-primary); margin-bottom: 4px; }
.step-content code { display: block; padding: 6px 8px; background: var(--bg-primary); border-radius: 4px; font-size: 11px; color: var(--text-secondary); overflow-x: auto; }
.step-meta { display: flex; gap: 10px; margin-top: 8px; font-size: 11px; }
.step-meta .risk { padding: 2px 6px; border-radius: 8px; }
.step-meta .risk.low { background: var(--color-success-bg); color: var(--color-success); }
.step-meta .risk.medium { background: var(--color-warning-bg); color: var(--color-warning); }
.step-meta .risk.high, .step-meta .risk.critical { background: var(--color-error-bg); color: var(--color-error); }
.step-meta span { color: var(--text-tertiary); display: flex; align-items: center; gap: 4px; }
.preview-actions { padding: 16px 20px; border-top: 1px solid var(--border-default); display: flex; gap: 12px; }
.preview-actions .btn-secondary, .preview-actions .btn-primary { flex: 1; justify-content: center; }

.btn-primary { padding: 10px 16px; background: var(--color-primary); color: var(--text-on-primary); border: none; border-radius: 6px; font-size: 13px; font-weight: 500; cursor: pointer; display: inline-flex; align-items: center; gap: 8px; }
.btn-primary:hover { filter: brightness(1.1); }
.btn-secondary { padding: 10px 16px; background: var(--bg-tertiary); color: var(--text-secondary); border: 1px solid var(--border-default); border-radius: 6px; font-size: 13px; cursor: pointer; display: inline-flex; align-items: center; gap: 8px; }
.btn-secondary:hover { background: var(--bg-hover); }

.slide-enter-active, .slide-leave-active { transition: transform 0.25s ease; }
.slide-enter-from, .slide-leave-to { transform: translateX(100%); }
</style>
