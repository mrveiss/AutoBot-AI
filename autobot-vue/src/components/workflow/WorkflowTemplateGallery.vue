<template>
  <div class="template-gallery">
    <div class="gallery-header">
      <div class="search-box">
        <i class="fas fa-search"></i>
        <input v-model="searchQuery" placeholder="Search templates..." />
      </div>
      <div class="category-filters">
        <button v-for="cat in categories" :key="cat" class="filter-btn" :class="{ active: selectedCategory === cat }" @click="selectedCategory = cat">
          {{ cat }}
        </button>
      </div>
    </div>

    <div v-if="loading" class="loading-state">
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
          <i :class="template.icon"></i>
        </div>
        <div class="template-info">
          <h4>{{ template.name }}</h4>
          <p>{{ template.description }}</p>
          <div class="template-meta">
            <span class="category-badge">{{ template.category }}</span>
            <span class="steps-count"><i class="fas fa-list-ol"></i> {{ template.steps.length }} steps</span>
          </div>
        </div>
        <div class="template-actions">
          <button class="btn-icon" @click.stop="$emit('select-template', template)" title="Edit"><i class="fas fa-edit"></i></button>
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
          <h4>Steps</h4>
          <div class="preview-steps">
            <div v-for="(step, i) in previewTemplate.steps" :key="i" class="preview-step">
              <span class="step-num">{{ i + 1 }}</span>
              <div class="step-content">
                <span class="step-desc">{{ step.description }}</span>
                <code>{{ step.command }}</code>
                <div class="step-meta">
                  <span class="risk" :class="step.risk_level">{{ step.risk_level }}</span>
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
import { ref, computed } from 'vue';
import type { WorkflowTemplate } from '@/composables/useWorkflowBuilder';

const props = defineProps<{ templates: WorkflowTemplate[]; loading: boolean }>();
defineEmits<{ (e: 'select-template', t: WorkflowTemplate): void; (e: 'run-template', t: WorkflowTemplate): void }>();

const searchQuery = ref('');
const selectedCategory = ref('All');
const previewTemplate = ref<WorkflowTemplate | null>(null);

const categories = computed(() => ['All', ...new Set(props.templates.map(t => t.category))]);

const filteredTemplates = computed(() => {
  let result = props.templates;
  if (selectedCategory.value !== 'All') result = result.filter(t => t.category === selectedCategory.value);
  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase();
    result = result.filter(t => t.name.toLowerCase().includes(q) || t.description.toLowerCase().includes(q));
  }
  return result;
});

const getCategoryClass = (cat: string) => ({ system: cat === 'System', development: cat === 'Development', security: cat === 'Security', backup: cat === 'Backup' });
</script>

<style scoped>
.template-gallery { height: 100%; display: flex; flex-direction: column; }
.gallery-header { padding: 0 0 20px; display: flex; flex-direction: column; gap: 16px; }
.search-box { display: flex; align-items: center; gap: 10px; padding: 10px 14px; background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: 8px; }
.search-box i { color: var(--text-muted); }
.search-box input { flex: 1; background: none; border: none; color: var(--text-primary); font-size: 14px; outline: none; }
.category-filters { display: flex; gap: 8px; flex-wrap: wrap; }
.filter-btn { padding: 6px 14px; background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: 20px; color: var(--text-secondary); font-size: 13px; cursor: pointer; transition: all 0.15s; }
.filter-btn:hover { background: var(--bg-hover); }
.filter-btn.active { background: var(--color-primary); color: var(--text-on-primary); border-color: var(--color-primary); }

.loading-state, .empty-state { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; color: var(--text-tertiary); }
.empty-state i { font-size: 48px; }

.templates-grid { flex: 1; display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; overflow-y: auto; padding-bottom: 20px; }
.template-card { display: flex; gap: 16px; padding: 16px; background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: 10px; cursor: pointer; transition: all 0.2s; }
.template-card:hover { border-color: var(--color-primary); box-shadow: 0 4px 12px rgba(0,0,0,0.1); }

.template-icon { width: 48px; height: 48px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 20px; background: var(--bg-tertiary); color: var(--text-secondary); }
.template-icon.system { background: var(--color-info-bg); color: var(--color-info); }
.template-icon.development { background: var(--color-primary-bg); color: var(--color-primary); }
.template-icon.security { background: var(--color-warning-bg); color: var(--color-warning); }
.template-icon.backup { background: var(--color-success-bg); color: var(--color-success); }

.template-info { flex: 1; min-width: 0; }
.template-info h4 { margin: 0 0 4px; font-size: 15px; color: var(--text-primary); }
.template-info p { margin: 0 0 10px; font-size: 13px; color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.template-meta { display: flex; gap: 12px; font-size: 12px; }
.category-badge { padding: 2px 8px; background: var(--bg-tertiary); color: var(--text-tertiary); border-radius: 10px; }
.steps-count { color: var(--text-tertiary); display: flex; align-items: center; gap: 4px; }

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
.step-meta .risk.high { background: var(--color-error-bg); color: var(--color-error); }
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
