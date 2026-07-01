<template>
  <div class="template-browser">
    <div class="browser-header">
      <div class="search-box">
        <Icon name="search" />
        <input
          v-model="searchQuery"
          :placeholder="$t('llc.templates.searchPlaceholder')"
          class="search-input"
        />
      </div>
      <div class="category-filters">
        <button
          v-for="cat in categories"
          :key="cat"
          class="filter-btn"
          :class="{ active: selectedCategory === cat }"
          @click="selectedCategory = cat"
        >
          {{ getCategoryLabel(cat) }}
          <span v-if="getCategoryCount(cat)" class="count-badge">{{
            getCategoryCount(cat)
          }}</span>
        </button>
      </div>
    </div>

    <!-- Error State -->
    <div v-if="error" class="error-state">
      <Icon name="exclamation-triangle" />
      <p>{{ error }}</p>
      <button class="btn-secondary" @click="loadTemplates">
        <Icon name="redo" /> {{ $t('common.retry') }}
      </button>
    </div>

    <!-- Loading State -->
    <div v-else-if="loading" class="loading-state">
      <Icon name="spinner" spin />
      <span>{{ $t('llc.templates.loading') }}</span>
    </div>

    <!-- Empty State -->
    <div v-else-if="filteredTemplates.length === 0" class="empty-state">
      <Icon name="briefcase" />
      <p>{{ $t('llc.templates.noMatch') }}</p>
    </div>

    <!-- Templates Grid -->
    <div v-else class="templates-grid">
      <div
        v-for="template in filteredTemplates"
        :key="template.key"
        class="template-card"
        :class="{ selected: selectedTemplate?.key === template.key }"
        @click="selectTemplate(template)"
      >
        <div class="template-icon" :class="getCategoryClass(template.category)">
          <Icon :name="(template.icon as any) || getDefaultIcon(template.category)" />
        </div>
        <div class="template-info">
          <h4>{{ template.name }}</h4>
          <p class="description">{{ template.description }}</p>
          <div class="template-meta">
            <span class="category-badge">{{ getCategoryLabel(template.category) }}</span>
            <span v-if="template.estimated_agents" class="agents-count">
              <Icon name="users" /> {{ template.estimated_agents }} agents
            </span>
            <span v-if="template.estimated_monthly_cost_cents" class="cost">
              <Icon name="dollar-sign" />
              ${{ (template.estimated_monthly_cost_cents / 100).toFixed(0) }}/mo
            </span>
          </div>
          <div v-if="template.tags?.length" class="template-tags">
            <span v-for="tag in template.tags.slice(0, 3)" :key="tag" class="tag">{{ tag }}</span>
            <span v-if="template.tags.length > 3" class="tag-more">
              +{{ template.tags.length - 3 }}
            </span>
          </div>
        </div>
        <div class="template-actions">
          <button
            class="btn-icon"
            @click.stop="openPreview(template)"
            :title="$t('llc.templates.preview')"
            :aria-label="$t('llc.templates.preview')"
          >
            <Icon name="eye" />
          </button>
          <button
            v-if="!hideSelect"
            class="btn-select"
            :class="{ selected: selectedTemplate?.key === template.key }"
            @click.stop="selectTemplate(template)"
            :title="$t('llc.templates.select')"
            :aria-label="$t('llc.templates.select')"
          >
            <Icon name="check" />
          </button>
        </div>
      </div>
    </div>

    <!-- Template Preview -->
    <Transition name="slide">
      <div v-if="previewTemplate" class="preview-panel">
        <div class="preview-header">
          <h3>{{ previewTemplate.name }}</h3>
          <button @click="previewTemplate = null" :aria-label="$t('common.close')">
            <Icon name="times" />
          </button>
        </div>
        <div class="preview-body">
          <p class="preview-desc">{{ previewTemplate.description }}</p>

          <div class="preview-meta">
            <div class="meta-item">
              <Icon name="layer-group" />
              <span>{{ getCategoryLabel(previewTemplate.category) }}</span>
            </div>
            <div v-if="previewTemplate.estimated_agents" class="meta-item">
              <Icon name="users" />
              <span>{{ previewTemplate.estimated_agents }} agents</span>
            </div>
            <div v-if="previewTemplate.estimated_monthly_cost_cents" class="meta-item">
              <Icon name="dollar-sign" />
              <span>${{ (previewTemplate.estimated_monthly_cost_cents / 100).toFixed(0) }}/mo estimated</span>
            </div>
          </div>

          <!-- Agents -->
          <div v-if="previewTemplate.agents?.length" class="preview-section">
            <h4><Icon name="users" /> Agents Included</h4>
            <div class="agent-list">
              <div v-for="agent in previewTemplate.agents" :key="agent.name" class="agent-item">
                <span class="agent-name">{{ agent.title }}</span>
                <span class="agent-role">{{ agent.role }}</span>
              </div>
            </div>
          </div>

          <!-- Goals -->
          <div v-if="previewTemplate.goals?.length" class="preview-section">
            <h4><Icon name="bullseye" /> Goals</h4>
            <div class="goal-list">
              <div v-for="(goal, i) in previewTemplate.goals" :key="i" class="goal-item">
                <span class="goal-level">{{ goal.level }}</span>
                <span class="goal-title">{{ goal.title }}</span>
              </div>
            </div>
          </div>

          <!-- Knowledge Collections -->
          <div v-if="previewTemplate.kb_collections?.length" class="preview-section">
            <h4><Icon name="book" /> Knowledge Collections</h4>
            <div class="kb-list">
              <div v-for="(kb, i) in previewTemplate.kb_collections" :key="i" class="kb-item">
                <Icon name="book-open" />
                <div>
                  <span class="kb-name">{{ kb.name }}</span>
                  <p class="kb-desc">{{ kb.description }}</p>
                </div>
              </div>
            </div>
          </div>

          <!-- Work Items -->
          <div v-if="previewTemplate.work_items?.length" class="preview-section">
            <h4><Icon name="tasks" /> Initial Work Items</h4>
            <div class="work-list">
              <div v-for="(item, i) in previewTemplate.work_items.slice(0, 5)" :key="i" class="work-item">
                <span class="work-type">{{ item.type }}</span>
                <span class="work-title">{{ item.title }}</span>
              </div>
              <span v-if="previewTemplate.work_items.length > 5" class="work-more">
                +{{ previewTemplate.work_items.length - 5 }} more
              </span>
            </div>
          </div>
        </div>
        <div class="preview-actions">
          <button class="btn-secondary" @click="previewTemplate = null">
            <Icon name="times" /> {{ $t('common.close') }}
          </button>
          <button class="btn-primary" @click="selectAndClose(previewTemplate)">
            <Icon name="check" /> {{ $t('llc.templates.useTemplate') }}
          </button>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
// GH#9164 - Template Browser UI for Company Creation Wizard

import { ref, computed, onMounted } from 'vue'
import { useCompanyTemplates, type CompanyTemplate, type TemplateCategory } from '@/composables/llc/useCompanyTemplates'
import Icon from '@/components/ui/Icon.vue'

const props = withDefaults(
  defineProps<{
    hideSelect?: boolean
    modelValue?: CompanyTemplate | null
  }>(),
  {
    hideSelect: false,
    modelValue: null,
  }
)

const emit = defineEmits<{
  (e: 'update:modelValue', template: CompanyTemplate | null): void
  (e: 'select', template: CompanyTemplate): void
}>()

const { templates, loading, error, listBuiltInTemplates } = useCompanyTemplates()

const searchQuery = ref('')
const selectedCategory = ref<TemplateCategory | 'all'>('all')
const selectedTemplate = ref<CompanyTemplate | null>(props.modelValue)
const previewTemplate = ref<CompanyTemplate | null>(null)

const categories = computed<Array<TemplateCategory | 'all'>>(() => [
  'all',
  'software-team',
  'marketing-agency',
  'consulting-firm',
  'research-lab',
  'startup',
  'custom',
])

const filteredTemplates = computed(() => {
  let result = templates.value

  // Filter by category
  if (selectedCategory.value !== 'all') {
    result = result.filter(t => t.category === selectedCategory.value)
  }

  // Filter by search query
  if (searchQuery.value.trim()) {
    const q = searchQuery.value.toLowerCase()
    result = result.filter(
      t =>
        t.name.toLowerCase().includes(q) ||
        t.description.toLowerCase().includes(q) ||
        t.tags?.some(tag => tag.toLowerCase().includes(q))
    )
  }

  return result
})

function getCategoryLabel(cat: TemplateCategory | 'all'): string {
  const labels: Record<string, string> = {
    all: 'All Templates',
    'software-team': 'Software Team',
    'marketing-agency': 'Marketing Agency',
    'consulting-firm': 'Consulting Firm',
    'research-lab': 'Research Lab',
    startup: 'Startup',
    custom: 'Custom',
  }
  return labels[cat] || cat
}

function getCategoryCount(cat: TemplateCategory | 'all'): number {
  if (cat === 'all') return templates.value.length
  return templates.value.filter(t => t.category === cat).length
}

function getCategoryClass(cat: TemplateCategory): string {
  return `category-${cat}`
}

function getDefaultIcon(cat: TemplateCategory): string {
  const icons: Record<TemplateCategory, string> = {
    'software-team': 'code',
    'marketing-agency': 'comments',
    'consulting-firm': 'briefcase',
    'research-lab': 'lightbulb',
    startup: 'rocket',
    custom: 'cog',
  }
  return icons[cat] || 'briefcase'
}

function selectTemplate(template: CompanyTemplate) {
  selectedTemplate.value = template
  emit('update:modelValue', template)
  emit('select', template)
}

function selectAndClose(template: CompanyTemplate) {
  selectTemplate(template)
  previewTemplate.value = null
}

function openPreview(template: CompanyTemplate) {
  previewTemplate.value = template
}

async function loadTemplates() {
  await listBuiltInTemplates()
}

onMounted(() => {
  loadTemplates()
})
</script>

<style scoped>
.template-browser {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg-primary);
}

.browser-header {
  padding: var(--spacing-4);
  border-bottom: 1px solid var(--border-color);
}

.search-box {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-3);
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  margin-bottom: var(--spacing-3);
}

.search-input {
  flex: 1;
  border: none;
  background: transparent;
  outline: none;
  color: var(--text-primary);
  font-size: var(--text-sm);
}

.category-filters {
  display: flex;
  gap: var(--spacing-2);
  flex-wrap: wrap;
}

.filter-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
  padding: var(--spacing-1-5) var(--spacing-3);
  border: 1px solid var(--border-color);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  font-size: var(--text-sm);
  cursor: pointer;
  transition: all var(--duration-200);
}

.filter-btn:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.filter-btn.active {
  background: var(--color-primary);
  color: white;
  border-color: var(--color-primary);
}

.count-badge {
  padding: 0 var(--spacing-1-5);
  background: rgba(255, 255, 255, 0.2);
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  font-weight: 600;
}

.error-state,
.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-8);
  gap: var(--spacing-3);
  color: var(--text-muted);
  text-align: center;
}

.templates-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: var(--spacing-4);
  padding: var(--spacing-4);
  overflow-y: auto;
}

.template-card {
  display: flex;
  flex-direction: column;
  padding: var(--spacing-4);
  background: var(--bg-secondary);
  border: 2px solid var(--border-color);
  border-radius: var(--radius-lg);
  cursor: pointer;
  transition: all var(--duration-200);
}

.template-card:hover {
  border-color: var(--color-primary);
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.template-card.selected {
  border-color: var(--color-primary);
  background: var(--bg-tertiary);
}

.template-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  border-radius: var(--radius-md);
  margin-bottom: var(--spacing-3);
  font-size: var(--text-2xl);
}

.category-software-team {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

.category-marketing-agency {
  background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
  color: white;
}

.category-consulting-firm {
  background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
  color: white;
}

.category-research-lab {
  background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%);
  color: white;
}

.category-startup {
  background: linear-gradient(135deg, #fa709a 0%, #fee140 100%);
  color: white;
}

.category-custom {
  background: linear-gradient(135deg, #a8edea 0%, #fed6e3 100%);
  color: white;
}

.template-info {
  flex: 1;
}

.template-info h4 {
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 var(--spacing-2);
}

.template-info .description {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: 0 0 var(--spacing-3);
  line-height: 1.5;
}

.template-meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-2);
  margin-bottom: var(--spacing-2);
  font-size: var(--text-xs);
}

.category-badge,
.agents-count,
.cost {
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
  padding: var(--spacing-1) var(--spacing-2);
  background: var(--bg-primary);
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
}

.template-tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-1);
}

.tag {
  padding: var(--spacing-0-5) var(--spacing-1-5);
  background: var(--bg-tertiary);
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.tag-more {
  padding: var(--spacing-0-5) var(--spacing-1-5);
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.template-actions {
  display: flex;
  gap: var(--spacing-2);
  margin-top: var(--spacing-3);
  padding-top: var(--spacing-3);
  border-top: 1px solid var(--border-color);
}

.btn-icon,
.btn-select {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-2);
  border: 1px solid var(--border-color);
  background: var(--bg-primary);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--duration-200);
}

.btn-icon:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.btn-select {
  flex: 1;
}

.btn-select:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.btn-select.selected {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: white;
}

/* Preview Panel */
.preview-panel {
  position: fixed;
  top: 0;
  right: 0;
  width: 480px;
  /* #10750 C2: cap height so long previews scroll internally (.preview-body) */
  max-height: 90vh;
  background: var(--bg-elevated);
  box-shadow: -4px 0 24px rgba(0, 0, 0, 0.2);
  display: flex;
  flex-direction: column;
  z-index: 100;
}

.preview-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-4);
  border-bottom: 1px solid var(--border-color);
}

.preview-header h3 {
  font-size: var(--text-xl);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.preview-header button {
  padding: var(--spacing-2);
  border: none;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  border-radius: var(--radius-md);
  transition: all var(--duration-200);
}

.preview-header button:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.preview-body {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-4);
}

.preview-desc {
  font-size: var(--text-base);
  color: var(--text-secondary);
  line-height: 1.6;
  margin: 0 0 var(--spacing-4);
}

.preview-meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-3);
  margin-bottom: var(--spacing-4);
  padding-bottom: var(--spacing-4);
  border-bottom: 1px solid var(--border-color);
}

.meta-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  color: var(--text-secondary);
  font-size: var(--text-sm);
}

.preview-section {
  margin-bottom: var(--spacing-4);
}

.preview-section h4 {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 var(--spacing-3);
}

.agent-list,
.goal-list,
.kb-list,
.work-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.agent-item,
.goal-item,
.work-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
}

.agent-name,
.goal-title,
.work-title {
  color: var(--text-primary);
}

.agent-role,
.goal-level,
.work-type {
  padding: var(--spacing-0-5) var(--spacing-1-5);
  background: var(--bg-tertiary);
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.kb-item {
  display: flex;
  gap: var(--spacing-2);
  padding: var(--spacing-2);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
}

.kb-name {
  display: block;
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: var(--spacing-0-5);
}

.kb-desc {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  margin: 0;
}

.work-more {
  padding: var(--spacing-2);
  text-align: center;
  font-size: var(--text-sm);
  color: var(--text-muted);
}

.preview-actions {
  display: flex;
  gap: var(--spacing-2);
  padding: var(--spacing-4);
  border-top: 1px solid var(--border-color);
}

.btn-secondary,
.btn-primary {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2-5) var(--spacing-4);
  border: none;
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  transition: all var(--duration-200);
}

.btn-secondary {
  background: var(--bg-secondary);
  color: var(--text-secondary);
}

.btn-secondary:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.btn-primary {
  flex: 1;
  background: var(--color-primary);
  color: white;
}

.btn-primary:hover {
  opacity: 0.9;
}

/* Slide Transition */
.slide-enter-active,
.slide-leave-active {
  transition: transform var(--duration-300) ease;
}

.slide-enter-from,
.slide-leave-to {
  transform: translateX(100%);
}
</style>
