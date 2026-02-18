<template>
  <div class="workflow-canvas-container">
    <!-- Toolbar -->
    <div class="canvas-toolbar">
      <div class="toolbar-left">
        <button class="tool-btn" @click="addStepNode" title="Add Step">
          <i class="fas fa-plus"></i> Add Step
        </button>
        <button class="tool-btn" @click="addConditionNode" title="Add Condition">
          <i class="fas fa-code-branch"></i> Condition
        </button>
        <div class="toolbar-divider"></div>
        <button class="tool-btn" @click="clearCanvas" title="Clear">
          <i class="fas fa-trash-alt"></i>
        </button>
        <button class="tool-btn" @click="autoLayout" title="Auto Layout">
          <i class="fas fa-magic"></i>
        </button>
      </div>
      <div class="toolbar-right">
        <button class="tool-btn" @click="zoomIn"><i class="fas fa-search-plus"></i></button>
        <button class="tool-btn" @click="zoomOut"><i class="fas fa-search-minus"></i></button>
        <button class="tool-btn" @click="resetZoom"><i class="fas fa-compress-arrows-alt"></i></button>
        <div class="toolbar-divider"></div>
        <button class="tool-btn primary" @click="saveWorkflow" :disabled="nodes.length === 0">
          <i class="fas fa-save"></i> Save
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
            <button class="delete-btn" @click.stop="deleteNode(node.id)"><i class="fas fa-times"></i></button>
          </div>
          <div class="node-body">
            <template v-if="node.type === 'step'">
              <input v-model="node.data.description" placeholder="Description" @click.stop />
              <input v-model="node.data.command" placeholder="Command" class="mono" @click.stop />
              <div class="node-row">
                <select v-model="node.data.risk_level" @click.stop>
                  <option value="low">Low Risk</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                </select>
                <label class="checkbox"><input type="checkbox" v-model="node.data.requires_confirmation" @click.stop /> Confirm</label>
              </div>
            </template>
            <template v-else-if="node.type === 'condition'">
              <input v-model="(node.data as any).condition" placeholder="Condition (e.g., $? -eq 0)" @click.stop />
            </template>
          </div>
          <div class="port port-in" @mousedown.stop="startConnect(node.id, 'in', $event)"></div>
          <div class="port port-out" @mousedown.stop="startConnect(node.id, 'out', $event)"></div>
        </div>

        <!-- Empty State -->
        <div v-if="nodes.length === 0" class="empty-state">
          <i class="fas fa-project-diagram"></i>
          <h3>Start Building Your Workflow</h3>
          <p>Add nodes using the toolbar or click below</p>
          <button class="btn-primary" @click="addStepNode"><i class="fas fa-plus"></i> Add Step</button>
        </div>
      </div>
    </div>

    <!-- Save Dialog -->
    <div v-if="showSaveDialog" class="dialog-overlay" @click.self="showSaveDialog = false">
      <div class="dialog">
        <h3><i class="fas fa-save"></i> Save Workflow</h3>
        <input v-model="saveName" placeholder="Workflow name" />
        <textarea v-model="saveDesc" placeholder="Description" rows="3"></textarea>
        <div class="dialog-actions">
          <button class="btn-secondary" @click="showSaveDialog = false">Cancel</button>
          <button class="btn-primary" @click="confirmSave" :disabled="!saveName.trim()">Save</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed } from 'vue';
import type { WorkflowNode } from '@/composables/useWorkflowBuilder';

const props = defineProps<{ nodes: WorkflowNode[]; selectedNodeId: string | null }>();
const emit = defineEmits<{
  (e: 'node-added', node: WorkflowNode): void;
  (e: 'node-removed', nodeId: string): void;
  (e: 'node-moved', nodeId: string, pos: { x: number; y: number }): void;
  (e: 'node-selected', nodeId: string | null): void;
  (e: 'nodes-connected', src: string, tgt: string): void;
  (e: 'save-workflow', name: string, desc: string): void;
}>();

const nodeIcons: Record<string, string> = { step: 'fas fa-terminal', condition: 'fas fa-code-branch', parallel: 'fas fa-columns' };
const nodeLabels: Record<string, string> = { step: 'Step', condition: 'Condition', parallel: 'Parallel' };

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

function deleteNode(id: string) {
  emit('node-removed', id);
  if (props.selectedNodeId === id) emit('node-selected', null);
}

function selectNode(id: string) { emit('node-selected', id); }

function clearCanvas() {
  if (props.nodes.length && confirm('Clear all nodes?')) {
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
.workflow-canvas-container { display: flex; flex-direction: column; height: 100%; background: var(--bg-primary); border-radius: 8px; overflow: hidden; }
.canvas-toolbar { display: flex; justify-content: space-between; padding: 12px 16px; background: var(--bg-secondary); border-bottom: 1px solid var(--border-default); }
.toolbar-left, .toolbar-right { display: flex; align-items: center; gap: 8px; }
.tool-btn { display: flex; align-items: center; gap: 6px; padding: 8px 12px; background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: 6px; color: var(--text-secondary); font-size: 13px; cursor: pointer; transition: all 0.15s; }
.tool-btn:hover:not(:disabled) { background: var(--bg-hover); color: var(--text-primary); }
.tool-btn.primary { background: var(--color-primary); color: var(--text-on-primary); border-color: var(--color-primary); }
.tool-btn.primary:hover:not(:disabled) { filter: brightness(1.1); }
.tool-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.toolbar-divider { width: 1px; height: 24px; background: var(--border-default); margin: 0 4px; }

.canvas-area { flex: 1; position: relative; overflow: hidden; background: linear-gradient(var(--border-subtle) 1px, transparent 1px), linear-gradient(90deg, var(--border-subtle) 1px, transparent 1px); background-size: 20px 20px; cursor: grab; }
.canvas-area:active { cursor: grabbing; }
.canvas-content { position: absolute; min-width: 100%; min-height: 100%; transform-origin: 0 0; }

.connections-svg { position: absolute; inset: 0; width: 3000px; height: 2000px; pointer-events: none; }
.connection-line { fill: none; stroke: var(--color-primary); stroke-width: 2; }
.drawing-line { fill: none; stroke: var(--color-primary); stroke-width: 2; stroke-dasharray: 5; opacity: 0.6; }

.workflow-node { position: absolute; width: 240px; background: var(--bg-secondary); border: 2px solid var(--border-default); border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); cursor: move; user-select: none; }
.workflow-node:hover { box-shadow: 0 4px 16px rgba(0,0,0,0.15); }
.workflow-node.selected { border-color: var(--color-primary); box-shadow: 0 0 0 3px var(--color-primary-bg); }
.workflow-node.step .node-header { background: var(--color-primary); }
.workflow-node.condition .node-header { background: var(--color-warning); }

.node-header { display: flex; align-items: center; gap: 8px; padding: 8px 12px; color: var(--text-on-primary); border-radius: 8px 8px 0 0; font-size: 13px; font-weight: 600; }
.node-header span { flex: 1; }
.delete-btn { padding: 4px; background: transparent; border: none; color: inherit; cursor: pointer; opacity: 0.7; border-radius: 4px; }
.delete-btn:hover { opacity: 1; background: rgba(255,255,255,0.2); }

.node-body { padding: 12px; display: flex; flex-direction: column; gap: 8px; }
.node-body input, .node-body select { width: 100%; padding: 6px 8px; background: var(--bg-primary); border: 1px solid var(--border-default); border-radius: 4px; color: var(--text-primary); font-size: 12px; }
.node-body input:focus, .node-body select:focus { outline: none; border-color: var(--color-primary); }
.node-body input.mono { font-family: monospace; }
.node-row { display: flex; gap: 8px; align-items: center; }
.node-row select { flex: 1; }
.checkbox { display: flex; align-items: center; gap: 4px; font-size: 12px; color: var(--text-secondary); white-space: nowrap; }
.checkbox input { width: 14px; height: 14px; }

.port { position: absolute; width: 12px; height: 12px; background: var(--bg-secondary); border: 2px solid var(--color-primary); border-radius: 50%; cursor: crosshair; top: 50%; transform: translateY(-50%); }
.port:hover { transform: translateY(-50%) scale(1.3); background: var(--color-primary); }
.port-in { left: -6px; }
.port-out { right: -6px; }

.empty-state { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); text-align: center; padding: 40px; }
.empty-state i { font-size: 48px; color: var(--text-muted); margin-bottom: 16px; }
.empty-state h3 { margin: 0 0 8px; color: var(--text-primary); }
.empty-state p { margin: 0 0 20px; color: var(--text-tertiary); }

.dialog-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 100; }
.dialog { width: 400px; background: var(--bg-secondary); border-radius: 12px; padding: 24px; }
.dialog h3 { margin: 0 0 20px; display: flex; align-items: center; gap: 10px; color: var(--text-primary); }
.dialog h3 i { color: var(--color-primary); }
.dialog input, .dialog textarea { width: 100%; padding: 10px 12px; margin-bottom: 12px; background: var(--bg-primary); border: 1px solid var(--border-default); border-radius: 6px; color: var(--text-primary); font-size: 14px; font-family: inherit; }
.dialog input:focus, .dialog textarea:focus { outline: none; border-color: var(--color-primary); }
.dialog-actions { display: flex; justify-content: flex-end; gap: 12px; margin-top: 12px; }

.btn-primary { padding: 10px 20px; background: var(--color-primary); color: var(--text-on-primary); border: none; border-radius: 6px; font-size: 14px; font-weight: 500; cursor: pointer; display: inline-flex; align-items: center; gap: 8px; }
.btn-primary:hover:not(:disabled) { filter: brightness(1.1); }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-secondary { padding: 10px 20px; background: var(--bg-tertiary); color: var(--text-secondary); border: 1px solid var(--border-default); border-radius: 6px; font-size: 14px; cursor: pointer; }
.btn-secondary:hover { background: var(--bg-hover); }
</style>
