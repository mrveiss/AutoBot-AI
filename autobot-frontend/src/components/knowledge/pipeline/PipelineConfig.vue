<!-- AutoBot - Knowledge Graph Pipeline (Issue #759) -->
<template>
  <div class="pipeline-config">
    <div class="config-header">
      <h4><i class="fas fa-sliders-h"></i> Pipeline Configuration</h4>
      <p class="header-description">
        Configure pipeline stages and processing parameters
      </p>
    </div>

    <!-- Stage Configuration -->
    <div class="stages-section">
      <h5>Processing Stages</h5>
      <div class="stage-list">
        <div
          v-for="stage in stages"
          :key="stage.id"
          class="stage-card"
          :class="{ disabled: !stage.enabled }"
        >
          <div class="stage-header">
            <div class="stage-toggle">
              <input
                :id="`stage-${stage.id}`"
                v-model="stage.enabled"
                type="checkbox"
                class="toggle-input"
              />
              <label :for="`stage-${stage.id}`" class="toggle-label">
                <i :class="stage.icon"></i>
                {{ stage.name }}
              </label>
            </div>
            <span class="stage-badge" :class="stage.id">
              {{ stage.id }}
            </span>
          </div>
          <p class="stage-description">{{ stage.description }}</p>

          <!-- Stage Tasks -->
          <div v-if="stage.enabled" class="stage-tasks">
            <div
              v-for="task in stage.tasks"
              :key="task.id"
              class="task-item"
            >
              <input
                :id="`task-${stage.id}-${task.id}`"
                v-model="task.enabled"
                type="checkbox"
                class="task-checkbox"
              />
              <label :for="`task-${stage.id}-${task.id}`">
                {{ task.name }}
              </label>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Parameters -->
    <div class="params-section">
      <h5>Processing Parameters</h5>

      <div class="param-group">
        <label for="batch-size">
          Batch Size: <strong>{{ batchSize }}</strong>
        </label>
        <input
          id="batch-size"
          v-model.number="batchSize"
          type="range"
          min="1"
          max="100"
          step="1"
          class="range-input"
        />
        <div class="range-labels">
          <span>1</span>
          <span>50</span>
          <span>100</span>
        </div>
      </div>

      <div class="param-group">
        <label for="confidence">
          Confidence Threshold: <strong>{{ confidenceThreshold.toFixed(2) }}</strong>
        </label>
        <input
          id="confidence"
          v-model.number="confidenceThreshold"
          type="range"
          min="0"
          max="1"
          step="0.05"
          class="range-input"
        />
        <div class="range-labels">
          <span>0.00</span>
          <span>0.50</span>
          <span>1.00</span>
        </div>
      </div>
    </div>

    <!-- Generated Config Preview -->
    <div class="preview-section">
      <h5>
        <i class="fas fa-code"></i>
        Configuration Preview
      </h5>
      <pre class="config-preview">{{ configPreview }}</pre>
    </div>

    <!-- Actions -->
    <div class="config-actions">
      <button class="action-btn secondary" @click="resetDefaults">
        <i class="fas fa-undo"></i> Reset Defaults
      </button>
      <button class="action-btn primary" @click="emitConfig">
        <i class="fas fa-check"></i> Apply Configuration
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref, reactive, computed } from 'vue'

interface StageTask {
  id: string
  name: string
  enabled: boolean
}

interface Stage {
  id: string
  name: string
  icon: string
  description: string
  enabled: boolean
  tasks: StageTask[]
}

const emit = defineEmits<{
  (e: 'config-change', config: Record<string, unknown>): void
}>()

const batchSize = ref(10)
const confidenceThreshold = ref(0.7)

const stages = reactive<Stage[]>([
  {
    id: 'extract',
    name: 'Extract',
    icon: 'fas fa-file-alt',
    description: 'Parse documents into chunks and extract raw content',
    enabled: true,
    tasks: [
      { id: 'chunk', name: 'Chunk Documents', enabled: true },
      { id: 'parse_metadata', name: 'Parse Metadata', enabled: true },
      { id: 'detect_language', name: 'Detect Language', enabled: true },
    ],
  },
  {
    id: 'cognify',
    name: 'Cognify',
    icon: 'fas fa-brain',
    description: 'Extract entities, relationships, and temporal events',
    enabled: true,
    tasks: [
      { id: 'entities', name: 'Entity Extraction', enabled: true },
      { id: 'relationships', name: 'Relationship Detection', enabled: true },
      { id: 'events', name: 'Temporal Event Detection', enabled: true },
      { id: 'coreference', name: 'Coreference Resolution', enabled: false },
    ],
  },
  {
    id: 'load',
    name: 'Load',
    icon: 'fas fa-database',
    description: 'Generate summaries and load into graph storage',
    enabled: true,
    tasks: [
      { id: 'summaries', name: 'Generate Summaries', enabled: true },
      { id: 'embeddings', name: 'Compute Embeddings', enabled: true },
      { id: 'index', name: 'Update Graph Index', enabled: true },
    ],
  },
])

const configPreview = computed(() => {
  const config: Record<string, unknown> = {
    batch_size: batchSize.value,
    confidence_threshold: confidenceThreshold.value,
    stages: {} as Record<string, unknown>,
  }

  for (const stage of stages) {
    const stageConfig: Record<string, unknown> = {
      enabled: stage.enabled,
      tasks: {} as Record<string, boolean>,
    }
    for (const task of stage.tasks) {
      (stageConfig.tasks as Record<string, boolean>)[task.id] =
        task.enabled
    }
    (config.stages as Record<string, unknown>)[stage.id] = stageConfig
  }

  return JSON.stringify(config, null, 2)
})

function resetDefaults(): void {
  batchSize.value = 10
  confidenceThreshold.value = 0.7
  for (const stage of stages) {
    stage.enabled = true
    for (const task of stage.tasks) {
      task.enabled = true
    }
  }
  // Disable coreference by default
  const cognifyStage = stages.find(s => s.id === 'cognify')
  if (cognifyStage) {
    const coref = cognifyStage.tasks.find(t => t.id === 'coreference')
    if (coref) coref.enabled = false
  }
}

function emitConfig(): void {
  emit('config-change', JSON.parse(configPreview.value))
}
</script>

<style scoped>
.pipeline-config {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
  padding: var(--spacing-lg);
}

.config-header h4 {
  font-size: var(--text-xl);
  font-weight: var(--font-bold);
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin: 0;
}

.config-header h4 i {
  color: var(--color-primary);
}

.header-description {
  color: var(--text-secondary);
  font-size: var(--text-sm);
  margin-top: var(--spacing-xs);
}

h5 {
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin: 0 0 var(--spacing-md) 0;
}

h5 i {
  color: var(--color-primary);
}

/* Stages */
.stage-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.stage-card {
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  padding: var(--spacing-md);
  transition: opacity var(--duration-200);
}

.stage-card.disabled {
  opacity: 0.5;
}

.stage-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-xs);
}

.stage-toggle {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.toggle-input {
  accent-color: var(--color-primary);
}

.toggle-label {
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.toggle-label i {
  color: var(--color-primary);
}

.stage-badge {
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
  padding: var(--spacing-xs) var(--spacing-sm);
  border-radius: var(--radius-full);
  text-transform: uppercase;
}

.stage-badge.extract {
  background: rgba(59, 130, 246, 0.1);
  color: rgb(59, 130, 246);
}

.stage-badge.cognify {
  background: rgba(168, 85, 247, 0.1);
  color: rgb(168, 85, 247);
}

.stage-badge.load {
  background: rgba(34, 197, 94, 0.1);
  color: rgb(34, 197, 94);
}

.stage-description {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: 0 0 var(--spacing-sm) 0;
}

.stage-tasks {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-sm);
  padding-top: var(--spacing-sm);
  border-top: 1px solid var(--border-subtle);
}

.task-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.task-checkbox {
  accent-color: var(--color-primary);
}

.task-item label {
  cursor: pointer;
}

/* Parameters */
.param-group {
  margin-bottom: var(--spacing-md);
}

.param-group label {
  display: block;
  font-size: var(--text-sm);
  color: var(--text-primary);
  margin-bottom: var(--spacing-xs);
}

.range-input {
  width: 100%;
  accent-color: var(--color-primary);
}

.range-labels {
  display: flex;
  justify-content: space-between;
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

/* Preview */
.config-preview {
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  padding: var(--spacing-md);
  font-family: 'Fira Code', 'Cascadia Code', monospace;
  font-size: var(--text-xs);
  color: var(--text-primary);
  overflow-x: auto;
  margin: 0;
}

/* Actions */
.config-actions {
  display: flex;
  gap: var(--spacing-sm);
  justify-content: flex-end;
}

.action-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  cursor: pointer;
  transition: all var(--duration-200);
}

.action-btn.secondary {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  color: var(--text-secondary);
}

.action-btn.secondary:hover {
  background: var(--bg-hover);
}

.action-btn.primary {
  background: var(--color-primary);
  border: none;
  color: white;
}

.action-btn.primary:hover {
  opacity: 0.9;
}

@media (max-width: 768px) {
  .config-actions {
    flex-direction: column;
  }

  .action-btn {
    justify-content: center;
  }
}
</style>
