<template>
  <div class="workflow-canvas-container">
    <!-- Toolbar -->
    <div class="canvas-toolbar">
      <div class="toolbar-left">
        <button class="tool-btn" @click="addStepNode" :title="$t('workflow.canvas.addStep')">
          <Icon name="plus" /> {{ $t('workflow.canvas.addStep') }}
        </button>
        <button class="tool-btn" @click="addConditionNode" :title="$t('workflow.canvas.addCondition')">
          <Icon name="code-branch" /> {{ $t('workflow.canvas.condition') }}
        </button>
        <button class="tool-btn" @click="addSwitchNode" :title="$t('workflow.canvas.addSwitch')">
          <Icon name="random" /> {{ $t('workflow.canvas.switch') }}
        </button>
        <div class="toolbar-divider"></div>
        <div class="dropdown-container">
          <button class="tool-btn" @click="showVisionDropdown = !showVisionDropdown" :title="$t('workflow.canvas.addVisionNode')">
            <Icon name="eye" /> {{ $t('workflow.canvas.vision') }}
            <Icon name="caret-down" />
          </button>
          <div v-if="showVisionDropdown" class="dropdown-menu" @mouseleave="showVisionDropdown = false">
            <button @click="addVisionNode('vision-capture')"><Icon name="camera" /> {{ $t('workflow.canvas.visionCapture') }}</button>
            <button @click="addVisionNode('vision-find-element')"><Icon name="search" /> {{ $t('workflow.canvas.visionFindElement') }}</button>
            <button @click="addVisionNode('vision-click')"><Icon name="mouse-pointer" /> {{ $t('workflow.canvas.visionClick') }}</button>
            <button @click="addVisionNode('vision-type-text')"><Icon name="keyboard" /> {{ $t('workflow.canvas.visionTypeText') }}</button>
            <button @click="addVisionNode('vision-ocr')"><Icon name="font" /> {{ $t('workflow.canvas.visionOcr') }}</button>
            <button @click="addVisionNode('vision-wait')"><Icon name="clock" /> {{ $t('workflow.canvas.visionWait') }}</button>
          </div>
        </div>
        <div class="toolbar-divider"></div>
        <button class="tool-btn" @click="clearCanvas" :title="$t('workflow.canvas.clear')" :aria-label="$t('workflow.canvas.clear')">
          <Icon name="trash-alt" />
        </button>
        <button class="tool-btn" @click="autoLayout" :title="$t('workflow.canvas.autoLayout')" :aria-label="$t('workflow.canvas.autoLayout')">
          <Icon name="magic" />
        </button>
      </div>
      <div class="toolbar-right">
        <button class="tool-btn" @click="zoomIn" :aria-label="$t('common.zoomIn')"><Icon name="search-plus" /></button>
        <button class="tool-btn" @click="zoomOut" :aria-label="$t('common.zoomOut')"><Icon name="search-minus" /></button>
        <button class="tool-btn" @click="resetZoom" :aria-label="$t('common.fitToView')"><Icon name="compress-arrows-alt" /></button>
        <div class="toolbar-divider"></div>
        <button class="tool-btn primary" @click="saveWorkflow" :disabled="nodes.length === 0">
          <Icon name="save" /> {{ $t('workflow.canvas.save') }}
        </button>
      </div>
    </div>

    <!-- Canvas -->
    <div ref="canvasRef" class="canvas-area" @mousedown="startPan" @mousemove="onMouseMove"
         @mouseup="endInteraction" @wheel.prevent="handleWheel">
      <div class="canvas-content" :style="canvasTransform">
        <!-- Connection Lines SVG -->
        <svg class="connections-svg">
          <defs>
            <marker id="arrow" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
              <polygon points="0 0, 10 3.5, 0 7" fill="var(--color-primary)" />
            </marker>
          </defs>
          <path v-for="conn in connections" :key="conn.id" :d="conn.path" class="connection-line" marker-end="url(#arrow)" />
          <path v-if="drawingLine" :d="drawingLinePath" class="drawing-line" />
        </svg>

        <!-- Nodes -->
        <div v-for="node in nodes" :key="node.id" class="workflow-node" :class="[node.type, { selected: selectedNodeId === node.id }]"
             :style="{ left: node.position.x + 'px', top: node.position.y + 'px' }"
             @mousedown.stop="startDrag(node, $event)" @click.stop="selectNode(node.id)">
          <div class="node-header">
            <i :class="nodeIcons[node.type]"></i>
            <span>{{ nodeLabels[node.type] }}</span>
            <button class="delete-btn" @click.stop="deleteNode(node.id)" :aria-label="$t('common.delete')"><Icon name="times" /></button>
          </div>
          <div class="node-body">
            <template v-if="node.type === 'step'">
              <input v-model="node.data.description" :placeholder="$t('workflow.canvas.description')" @click.stop />
              <input v-model="node.data.command" :placeholder="$t('workflow.canvas.command')" class="mono" @click.stop />
              <div class="node-row">
                <select v-model="node.data.risk_level" @click.stop>
                  <option value="low">{{ $t('workflow.canvas.lowRisk') }}</option>
                  <option value="medium">{{ $t('workflow.canvas.mediumRisk') }}</option>
                  <option value="high">{{ $t('workflow.canvas.highRisk') }}</option>
                </select>
                <label class="checkbox"><input type="checkbox" v-model="node.data.requires_confirmation" @click.stop /> {{ $t('workflow.canvas.confirm') }}</label>
              </div>
            </template>
            <template v-else-if="node.type === 'condition'">
              <select v-model="(node.data as any).condition_type" @click.stop>
                <option value="expression">{{ $t('workflow.canvas.conditionExpr') }}</option>
                <option value="jsonpath">JSONPath</option>
                <option value="compare">{{ $t('workflow.canvas.conditionCompare') }}</option>
              </select>
              <input v-model="(node.data as any).condition" :placeholder="(node.data as any).condition_type === 'jsonpath' ? '$.result.status == &quot;ok&quot;' : $t('workflow.canvas.conditionPlaceholder')" class="mono" @click.stop />
              <div class="branch-labels">
                <span class="branch-true">✓ True</span>
                <span class="branch-false">✗ False</span>
              </div>
            </template>
            <template v-else-if="node.type === 'switch'">
              <input v-model="(node.data as any).switch_on" :placeholder="$t('workflow.canvas.switchOnPlaceholder')" class="mono" @click.stop />
              <div class="switch-cases">
                <div v-for="(c, i) in (((node.data as any).cases || []) as string[])" :key="i" class="switch-case-row">
                  <input v-model="(node.data as any).cases[i]" :placeholder="`case ${i + 1}`" class="mono" @click.stop />
                  <button class="delete-case-btn" @click.stop="removeCase(node, i)">×</button>
                </div>
                <button class="add-case-btn" @click.stop="addCase(node)">+ {{ $t('workflow.canvas.addCase') }}</button>
              </div>
              <span class="hint">{{ $t('workflow.canvas.switchDefaultHint') }}</span>
            </template>
            <template v-else-if="node.type.startsWith('vision-')">
              <div class="node-row">
                <label class="target-label">Target:</label>
                <select v-model="(node.data as any).target" @click.stop>
                  <option value="vnc">VNC</option>
                  <option value="web">Web</option>
                </select>
              </div>
              <template v-if="node.type === 'vision-capture'">
                <label class="checkbox"><input type="checkbox" v-model="(node.data as any).include_ocr" @click.stop /> OCR</label>
                <label class="checkbox"><input type="checkbox" v-model="(node.data as any).include_elements" @click.stop /> Elements</label>
              </template>
              <template v-else-if="node.type === 'vision-find-element'">
                <input v-model="(node.data as any).element_type" placeholder="Element type (button, input...)" @click.stop />
                <input v-model="(node.data as any).text_match" placeholder="Text to match" @click.stop />
              </template>
              <template v-else-if="node.type === 'vision-click'">
                <select v-model="(node.data as any).click_type" @click.stop>
                  <option value="single">Single Click</option>
                  <option value="double">Double Click</option>
                  <option value="right">Right Click</option>
                </select>
              </template>
              <template v-else-if="node.type === 'vision-type-text'">
                <input v-model="(node.data as any).text" placeholder="Text to type" @click.stop />
                <label class="checkbox"><input type="checkbox" v-model="(node.data as any).clear_first" @click.stop /> Clear first</label>
              </template>
              <template v-else-if="node.type === 'vision-ocr'">
                <span class="hint">Extracts all text from screen</span>
              </template>
              <template v-else-if="node.type === 'vision-wait'">
                <input v-model="(node.data as any).element_criteria" placeholder="Element to wait for" @click.stop />
                <input v-model.number="(node.data as any).timeout_ms" type="number" placeholder="Timeout (ms)" @click.stop />
              </template>
            </template>
          </div>
          <div class="port port-in" @mousedown.stop="startConnect(node.id, 'in', $event)"></div>
          <div class="port port-out" @mousedown.stop="startConnect(node.id, 'out', $event)"></div>
        </div>

        <!-- Empty State -->
        <div v-if="nodes.length === 0" class="empty-state">
          <Icon name="project-diagram" />
          <h3>{{ $t('workflow.canvas.emptyTitle') }}</h3>
          <p>{{ $t('workflow.canvas.emptyDescription') }}</p>
          <button class="btn-primary" @click="addStepNode"><Icon name="plus" /> {{ $t('workflow.canvas.addStep') }}</button>
        </div>
      </div>
    </div>

    <!-- Save Dialog -->
    <div v-if="showSaveDialog" class="dialog-overlay" @click.self="showSaveDialog = false">
      <div class="dialog">
        <h3><Icon name="save" /> {{ $t('workflow.canvas.saveWorkflow') }}</h3>
        <input v-model="saveName" :placeholder="$t('workflow.canvas.workflowName')" />
        <textarea v-model="saveDesc" :placeholder="$t('workflow.canvas.description')" rows="3"></textarea>
        <div class="dialog-actions">
          <button class="btn-secondary" @click="showSaveDialog = false">{{ $t('workflow.canvas.cancelBtn') }}</button>
          <button class="btn-primary" @click="confirmSave" :disabled="!saveName.trim()">{{ $t('workflow.canvas.save') }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { ref, reactive, computed } from 'vue';
import { useI18n } from 'vue-i18n';
import type { WorkflowNode } from '@/composables/useWorkflowBuilder';

const { t } = useI18n();

const props = defineProps<{ nodes: WorkflowNode[]; selectedNodeId: string | null }>();
const emit = defineEmits<{
  (e: 'node-added', node: WorkflowNode): void;
  (e: 'node-removed', nodeId: string): void;
  (e: 'node-moved', nodeId: string, pos: { x: number; y: number }): void;
  (e: 'node-selected', nodeId: string | null): void;
  (e: 'nodes-connected', src: string, tgt: string): void;
  (e: 'save-workflow', name: string, desc: string): void;
}>();

const showVisionDropdown = ref(false);

const nodeIcons: Record<string, string> = {
  step: 'terminal',
  condition: 'code-branch',
  switch: 'random',
  parallel: 'columns',
  'vision-capture': 'camera',
  'vision-find-element': 'search',
  'vision-click': 'mouse-pointer',
  'vision-type-text': 'keyboard',
  'vision-ocr': 'font',
  'vision-wait': 'clock',
};
const nodeLabels = computed(() => ({
  step: t('workflow.canvas.stepLabel'),
  condition: t('workflow.canvas.conditionLabel'),
  switch: t('workflow.canvas.switchLabel'),
  parallel: t('workflow.canvas.parallelLabel'),
  // #9724: 'loop' is part of WorkflowNode['type'] but had no label entry
  loop: t('workflow.canvas.loopLabel', 'Loop'),
  'vision-capture': t('workflow.canvas.visionCapture'),
  'vision-find-element': t('workflow.canvas.visionFindElement'),
  'vision-click': t('workflow.canvas.visionClick'),
  'vision-type-text': t('workflow.canvas.visionTypeText'),
  'vision-ocr': t('workflow.canvas.visionOcr'),
  'vision-wait': t('workflow.canvas.visionWait'),
}));

const canvasRef = ref<HTMLElement | null>(null);
const zoom = ref(1);
const pan = reactive({ x: 50, y: 50 });
const isPanning = ref(false);
const panStart = reactive({ x: 0, y: 0 });
const dragNode = ref<WorkflowNode | null>(null);
const dragOffset = reactive({ x: 0, y: 0 });
const drawingLine = ref(false);
const lineStart = reactive({ nodeId: '', x: 0, y: 0 });
const mousePos = reactive({ x: 0, y: 0 });
const showSaveDialog = ref(false);
const saveName = ref('');
const saveDesc = ref('');

const canvasTransform = computed(() => ({ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom.value})` }));

const connections = computed(() => {
  const result: { id: string; path: string }[] = [];
  props.nodes.forEach(node => {
    node.connections.forEach(targetId => {
      const target = props.nodes.find(n => n.id === targetId);
      if (target) {
        const x1 = node.position.x + 240, y1 = node.position.y + 50;
        const x2 = target.position.x, y2 = target.position.y + 50;
        const mx = (x1 + x2) / 2;
        result.push({ id: `${node.id}-${targetId}`, path: `M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}` });
      }
    });
  });
  return result;
});

const drawingLinePath = computed(() => {
  if (!drawingLine.value) return '';
  const tx = (mousePos.x - pan.x) / zoom.value, ty = (mousePos.y - pan.y) / zoom.value;
  const mx = (lineStart.x + tx) / 2;
  return `M${lineStart.x},${lineStart.y} C${mx},${lineStart.y} ${mx},${ty} ${tx},${ty}`;
});

const genId = () => `node_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

function addStepNode() {
  const node: WorkflowNode = {
    id: genId(), type: 'step',
    position: { x: 100 + props.nodes.length * 40, y: 100 + props.nodes.length * 30 },
    data: { command: '', description: '', risk_level: 'low', requires_confirmation: true, estimated_duration: 30 },
    connections: []
  };
  emit('node-added', node);
  emit('node-selected', node.id);
}

function addConditionNode() {
  const node: WorkflowNode = {
    id: genId(), type: 'condition',
    position: { x: 100 + props.nodes.length * 40, y: 100 + props.nodes.length * 30 },
    data: { condition: '' }, connections: []
  };
  emit('node-added', node);
  emit('node-selected', node.id);
}

function addSwitchNode() {
  const node: WorkflowNode = {
    id: genId(), type: 'switch',
    position: { x: 100 + props.nodes.length * 40, y: 100 + props.nodes.length * 30 },
    data: { switch_on: '', cases: [''] }, connections: []
  };
  emit('node-added', node);
  emit('node-selected', node.id);
}

function addCase(node: WorkflowNode) {
  const data = node.data as Record<string, unknown>;
  const cases = (data.cases as string[]) || [];
  cases.push('');
  data.cases = cases;
}

function removeCase(node: WorkflowNode, index: number) {
  const data = node.data as Record<string, unknown>;
  const cases = (data.cases as string[]) || [];
  cases.splice(index, 1);
  data.cases = cases;
}

function addVisionNode(type: WorkflowNode['type']) {
  const defaultData: Record<string, Record<string, unknown>> = {
    'vision-capture': { target: 'vnc', include_ocr: true, include_elements: true, include_layout: true },
    'vision-find-element': { target: 'vnc', element_type: '', text_match: '', confidence_threshold: 0.7 },
    'vision-click': { target: 'vnc', element_ref: '', click_type: 'single' },
    'vision-type-text': { target: 'vnc', element_ref: '', text: '', clear_first: false },
    'vision-ocr': { target: 'vnc', region: null },
    'vision-wait': { target: 'vnc', element_criteria: '', timeout_ms: 10000, poll_interval_ms: 500 },
  };
  const node: WorkflowNode = {
    id: genId(),
    type,
    position: { x: 100 + props.nodes.length * 40, y: 100 + props.nodes.length * 30 },
    data: defaultData[type] || {},
    connections: [],
  };
  emit('node-added', node);
  emit('node-selected', node.id);
  showVisionDropdown.value = false;
}

function deleteNode(id: string) {
  emit('node-removed', id);
  if (props.selectedNodeId === id) emit('node-selected', null);
}

function selectNode(id: string) { emit('node-selected', id); }

function clearCanvas() {
  if (props.nodes.length && confirm(t('workflow.canvas.clearConfirm'))) {
    props.nodes.forEach(n => emit('node-removed', n.id));
    emit('node-selected', null);
  }
}

function autoLayout() {
  props.nodes.forEach((node, i) => {
    emit('node-moved', node.id, { x: 100 + (i % 3) * 300, y: 100 + Math.floor(i / 3) * 180 });
  });
}

function zoomIn() { zoom.value = Math.min(2, zoom.value + 0.1); }
function zoomOut() { zoom.value = Math.max(0.3, zoom.value - 0.1); }
function resetZoom() { zoom.value = 1; pan.x = 50; pan.y = 50; }
function handleWheel(e: WheelEvent) { zoom.value = Math.max(0.3, Math.min(2, zoom.value + (e.deltaY > 0 ? -0.05 : 0.05))); }

function startPan(e: MouseEvent) {
  if (e.button === 1 || e.shiftKey) { isPanning.value = true; panStart.x = e.clientX - pan.x; panStart.y = e.clientY - pan.y; }
}

function startDrag(node: WorkflowNode, e: MouseEvent) {
  dragNode.value = node;
  dragOffset.x = e.clientX - node.position.x * zoom.value - pan.x;
  dragOffset.y = e.clientY - node.position.y * zoom.value - pan.y;
}

function startConnect(nodeId: string, port: string, e: MouseEvent) {
  drawingLine.value = true;
  const node = props.nodes.find(n => n.id === nodeId);
  if (node) {
    lineStart.nodeId = nodeId;
    lineStart.x = node.position.x + (port === 'out' ? 240 : 0);
    lineStart.y = node.position.y + 50;
  }
  mousePos.x = e.clientX; mousePos.y = e.clientY;
}

function onMouseMove(e: MouseEvent) {
  mousePos.x = e.clientX; mousePos.y = e.clientY;
  if (isPanning.value) { pan.x = e.clientX - panStart.x; pan.y = e.clientY - panStart.y; }
  else if (dragNode.value) {
    const x = (e.clientX - dragOffset.x - pan.x) / zoom.value;
    const y = (e.clientY - dragOffset.y - pan.y) / zoom.value;
    emit('node-moved', dragNode.value.id, { x: Math.max(0, x), y: Math.max(0, y) });
  }
}

function endInteraction(e: MouseEvent) {
  if (drawingLine.value) {
    const rect = canvasRef.value?.getBoundingClientRect();
    if (rect) {
      const x = (e.clientX - rect.left - pan.x) / zoom.value;
      const y = (e.clientY - rect.top - pan.y) / zoom.value;
      const target = props.nodes.find(n => x >= n.position.x && x <= n.position.x + 240 && y >= n.position.y && y <= n.position.y + 100);
      if (target && target.id !== lineStart.nodeId) emit('nodes-connected', lineStart.nodeId, target.id);
    }
  }
  isPanning.value = false; dragNode.value = null; drawingLine.value = false;
}

function saveWorkflow() { showSaveDialog.value = true; }
function confirmSave() { emit('save-workflow', saveName.value, saveDesc.value); showSaveDialog.value = false; saveName.value = ''; saveDesc.value = ''; }
</script>

<style scoped>
.workflow-canvas-container { display: flex; flex-direction: column; height: 100%; background: var(--bg-primary); border-radius: var(--radius-lg); overflow: hidden; }
.canvas-toolbar { display: flex; justify-content: space-between; padding: var(--spacing-3) var(--spacing-4); background: var(--bg-secondary); border-bottom: 1px solid var(--border-default); }
.toolbar-left, .toolbar-right { display: flex; align-items: center; gap: var(--spacing-2); }
.tool-btn { display: flex; align-items: center; gap: var(--spacing-1-5); padding: var(--spacing-2) var(--spacing-3); background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: var(--radius-md); color: var(--text-secondary); font-size: var(--text-sm); cursor: pointer; transition: all 0.15s; }
.tool-btn:hover:not(:disabled) { background: var(--bg-hover); color: var(--text-primary); }
.tool-btn.primary { background: var(--color-primary); color: var(--text-on-primary); border-color: var(--color-primary); }
.tool-btn.primary:hover:not(:disabled) { filter: brightness(1.1); }
.tool-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.tool-btn.btn-experimental { opacity: 0.85; position: relative; }
.badge-experimental { font-size: 9px; padding: var(--spacing-px) var(--spacing-1); background: var(--color-warning); color: #000; border-radius: var(--radius-default); font-weight: 700; text-transform: uppercase; line-height: 1; }
.toolbar-divider { width: 1px; height: 24px; background: var(--border-default); margin: var(--spacing-0) var(--spacing-1); }

.canvas-area { flex: 1; position: relative; overflow: hidden; background: linear-gradient(var(--border-subtle) 1px, transparent 1px), linear-gradient(90deg, var(--border-subtle) 1px, transparent 1px); background-size: 20px 20px; cursor: grab; }
.canvas-area:active { cursor: grabbing; }
.canvas-content { position: absolute; min-width: 100%; min-height: 100%; transform-origin: 0 0; }

.connections-svg { position: absolute; inset: 0; width: 3000px; height: 2000px; pointer-events: none; }
.connection-line { fill: none; stroke: var(--color-primary); stroke-width: 2; }
.drawing-line { fill: none; stroke: var(--color-primary); stroke-width: 2; stroke-dasharray: 5; opacity: 0.6; }

.workflow-node { position: absolute; width: 240px; background: var(--bg-secondary); border: 2px solid var(--border-default); border-radius: var(--radius-xl); box-shadow: var(--shadow-sm); cursor: move; user-select: none; }
.workflow-node:hover { box-shadow: var(--shadow-md); }
.workflow-node.selected { border-color: var(--color-primary); box-shadow: 0 0 0 3px var(--color-primary-bg); }
.workflow-node.step .node-header { background: var(--color-primary); }
.workflow-node.condition .node-header { background: var(--color-warning); }
.workflow-node.switch .node-header { background: #0891b2; }
.workflow-node[class*="vision-"] .node-header { background: linear-gradient(135deg, #7c3aed, #6d28d9); }
.branch-labels { display: flex; justify-content: space-between; font-size: var(--text-xs); margin-top: var(--spacing-1); }
.branch-true { color: var(--color-success, #22c55e); font-weight: 600; }
.branch-false { color: var(--color-error, #ef4444); font-weight: 600; }
.switch-cases { display: flex; flex-direction: column; gap: var(--spacing-1); }
.switch-case-row { display: flex; gap: var(--spacing-1); align-items: center; }
.switch-case-row input { flex: 1; }
.delete-case-btn { padding: 2px 6px; background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: var(--radius-default); color: var(--text-secondary); cursor: pointer; font-size: var(--text-xs); line-height: 1; }
.delete-case-btn:hover { color: var(--color-error, #ef4444); }
.add-case-btn { padding: var(--spacing-1) var(--spacing-2); background: transparent; border: 1px dashed var(--border-default); border-radius: var(--radius-default); color: var(--text-secondary); cursor: pointer; font-size: var(--text-xs); text-align: left; }
.add-case-btn:hover { border-color: var(--color-primary); color: var(--color-primary); }

.dropdown-container { position: relative; display: inline-block; }
.dropdown-menu { position: absolute; top: 100%; left: 0; z-index: 10; background: var(--bg-secondary, #1e293b); border: 1px solid var(--border-color, #334155); border-radius: var(--radius-md); padding: var(--spacing-1) var(--spacing-0); min-width: 180px; box-shadow: 0 4px 12px rgba(0,0,0,0.3); }
.dropdown-menu button { display: flex; align-items: center; gap: var(--spacing-2); width: 100%; padding: var(--spacing-2) var(--spacing-3); border: none; background: none; color: var(--text-primary, #e2e8f0); cursor: pointer; font-size: 0.85rem; }
.dropdown-menu button:hover { background: var(--bg-tertiary, #334155); }
.target-label { font-size: var(--text-xs); color: var(--text-secondary, #94a3b8); }
.hint { font-size: var(--text-xs); color: var(--text-secondary, #94a3b8); font-style: italic; }

.node-header { display: flex; align-items: center; gap: var(--spacing-2); padding: var(--spacing-2) var(--spacing-3); color: var(--text-on-primary); border-radius: var(--radius-lg) 8px 0 0; font-size: var(--text-sm); font-weight: 600; }
.node-header span { flex: 1; }
.delete-btn { padding: var(--spacing-1); background: transparent; border: none; color: inherit; cursor: pointer; opacity: 0.7; border-radius: var(--radius-default); }
.delete-btn:hover { opacity: 1; background: rgba(255,255,255,0.2); }

.node-body { padding: var(--spacing-3); display: flex; flex-direction: column; gap: var(--spacing-2); }
.node-body input, .node-body select { width: 100%; padding: var(--spacing-1-5) var(--spacing-2); background: var(--bg-primary); border: 1px solid var(--border-default); border-radius: var(--radius-default); color: var(--text-primary); font-size: var(--text-xs); }
.node-body input:focus, .node-body select:focus { outline: none; border-color: var(--color-primary); }
.node-body input:focus-visible, .node-body select:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 2px; }
.node-body input.mono { font-family: monospace; }
.node-row { display: flex; gap: var(--spacing-2); align-items: center; }
.node-row select { flex: 1; }
.checkbox { display: flex; align-items: center; gap: var(--spacing-1); font-size: var(--text-xs); color: var(--text-secondary); white-space: nowrap; }
.checkbox input { width: 14px; height: 14px; }

.port { position: absolute; width: 12px; height: 12px; background: var(--bg-secondary); border: 2px solid var(--color-primary); border-radius: 50%; cursor: crosshair; top: 50%; transform: translateY(-50%); }
.port:hover { transform: translateY(-50%) scale(1.3); background: var(--color-primary); }
.port-in { left: -6px; }
.port-out { right: -6px; }

.empty-state { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); text-align: center; padding: var(--spacing-10); }
.empty-state i { font-size: var(--text-5xl); color: var(--text-muted); margin-bottom: var(--spacing-4); }
.empty-state h3 { margin: var(--spacing-0) var(--spacing-0) var(--spacing-2); color: var(--text-primary); }
.empty-state p { margin: var(--spacing-0) var(--spacing-0) var(--spacing-5); color: var(--text-tertiary); }

.dialog-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: var(--z-modal-backdrop); }
.dialog { width: 400px; background: var(--bg-secondary); border-radius: var(--radius-xl); padding: var(--spacing-6); }
.dialog h3 { margin: var(--spacing-0) var(--spacing-0) var(--spacing-5); display: flex; align-items: center; gap: var(--spacing-2-5); color: var(--text-primary); }
.dialog h3 i { color: var(--color-primary); }
.dialog input, .dialog textarea { width: 100%; padding: var(--spacing-2-5) var(--spacing-3); margin-bottom: var(--spacing-3); background: var(--bg-primary); border: 1px solid var(--border-default); border-radius: var(--radius-md); color: var(--text-primary); font-size: var(--text-sm); font-family: inherit; }
.dialog input:focus, .dialog textarea:focus { outline: none; border-color: var(--color-primary); }
.dialog input:focus-visible, .dialog textarea:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 2px; }
.dialog-actions { display: flex; justify-content: flex-end; gap: var(--spacing-3); margin-top: var(--spacing-3); }

.btn-primary { padding: var(--spacing-2-5) var(--spacing-5); background: var(--color-primary); color: var(--text-on-primary); border: none; border-radius: var(--radius-md); font-size: var(--text-sm); font-weight: 500; cursor: pointer; display: inline-flex; align-items: center; gap: var(--spacing-2); }
.btn-primary:hover:not(:disabled) { filter: brightness(1.1); }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-secondary { padding: var(--spacing-2-5) var(--spacing-5); background: var(--bg-tertiary); color: var(--text-secondary); border: 1px solid var(--border-default); border-radius: var(--radius-md); font-size: var(--text-sm); cursor: pointer; }
.btn-secondary:hover { background: var(--bg-hover); }
</style>
