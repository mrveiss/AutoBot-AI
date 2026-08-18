<template>
  <div class="workflow-canvas-container">
    <!-- Toolbar -->
    <div class="canvas-toolbar">
      <div class="toolbar-left">
        <!-- GH#13939: tab strip — rendered only when the consumer supplies tabs -->
        <div v-if="tabs.length > 0" class="canvas-tabs" role="tablist">
          <button
            v-for="tab in tabs"
            :key="tab.id"
            class="canvas-tab"
            :class="{ active: tab.id === activeTabId }"
            role="tab"
            :aria-selected="tab.id === activeTabId"
            @click="emit('tab-selected', tab.id)"
          >
            {{ tab.label }}
          </button>
        </div>
        <!-- GH#13941: which declarative rule set colours the nodes. Offered only
             when there are org nodes to colour, so workflow authoring is
             untouched. -->
        <div v-if="hasOrgNodes" class="rule-mode" role="group" :aria-label="$t('llc.canvasRules.colourBy')">
          <span class="rule-mode-label">{{ $t('llc.canvasRules.colourBy') }}</span>
          <button
            v-for="dimension in SELECTABLE_RULE_DIMENSIONS"
            :key="dimension"
            type="button"
            class="rule-mode-btn"
            :class="{ active: colourMode === dimension }"
            :aria-pressed="colourMode === dimension"
            :data-testid="`rule-mode-${dimension}`"
            @click="colourMode = dimension"
          >
            {{ dimensionLabels[dimension] }}
          </button>
        </div>
        <template v-if="!readonly">
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
        </template>
      </div>
      <div class="toolbar-right">
        <button class="tool-btn" @click="zoomIn" :aria-label="$t('common.zoomIn')"><Icon name="search-plus" /></button>
        <button class="tool-btn" @click="zoomOut" :aria-label="$t('common.zoomOut')"><Icon name="search-minus" /></button>
        <button class="tool-btn" @click="resetZoom" :aria-label="$t('common.fitToView')"><Icon name="compress-arrows-alt" /></button>
        <template v-if="!readonly">
        <div class="toolbar-divider"></div>
        <button class="tool-btn primary" @click="saveWorkflow" :disabled="nodes.length === 0">
          <Icon name="save" /> {{ $t('workflow.canvas.save') }}
        </button>
        </template>
      </div>
    </div>

    <!-- Canvas -->
    <div ref="canvasRef" class="canvas-area" @pointerdown="startPan" @pointermove="onPointerMove"
         @pointerup="endInteraction" @pointercancel="endInteraction" @wheel.prevent="handleWheel">
      <div class="canvas-content" :style="canvasTransform">
        <!-- #14609: keyboard instructions for the canvas's own composite-widget
             navigation (roving tabindex + arrow keys) — not discoverable from
             markup alone, so a screen-reader user needs it stated. Visually
             hidden; referenced from every node via aria-describedby. -->
        <p :id="navInstructionsId" class="sr-only">{{ $t('workflow.canvas.a11yInstructions') }}</p>
        <p v-if="!readonly" :id="moveInstructionsId" class="sr-only">{{ $t('workflow.canvas.a11yInstructionsMove') }}</p>
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
        <!-- #14609: roving tabindex (WAI-ARIA APG composite-widget pattern) —
             exactly one node is a Tab stop; arrow keys move focus between the
             rest, Enter/Space selects (mirrors @click), Escape deselects, and
             a modifier+arrow moves the node (drag's keyboard equivalent, only
             when not readonly). `@keydown` guards `e.target === e.currentTarget`
             so a keypress inside a node's own input/select/button — e.g. typing
             a literal space into a step's description — reaches that control
             instead of being hijacked as "select the node". -->
        <div v-for="node in nodes" :key="node.id" class="workflow-node"
             :ref="(el) => registerNodeEl(node.id, el as Element | null)"
             :class="[node.type, { selected: selectedNodeId === node.id }, ...ruleClasses(node)]"
             :data-rule-id="nodeRuleId(node)"
             :data-node-id="node.id"
             :style="nodeStyle(node)"
             role="button"
             :tabindex="rovingTabStopId === node.id ? 0 : -1"
             :aria-label="nodeAriaLabel(node)"
             :aria-pressed="selectedNodeId === node.id"
             :aria-describedby="instructionsId"
             @pointerdown="onNodePointerDown(node, $event)"
             @click.stop="selectNode(node.id)"
             @focus="focusedNodeId = node.id"
             @keydown="onNodeKeydown(node, $event)">
          <div class="node-header">
            <Icon :name="nodeIcons[node.type]" />
            <span>{{ nodeTitle(node) }}</span>
            <button v-if="!readonly" class="delete-btn" @click.stop="deleteNode(node.id)" :aria-label="$t('common.delete')"><Icon name="times" /></button>
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
            <!-- #13963: a workflow a role runs. Read-only, like the other org
                 nodes — the canvas is a way in to the automation module, not a
                 second place to edit a workflow. -->
            <template v-else-if="node.type === 'org-process'">
              <!-- The node is a way in to the automation module, and the only
                   visible text is a workflow id and a role name — neither says
                   that activating it goes anywhere. The description carries
                   that, so it reaches a screen reader and a hover alike. -->
              <p
                class="org-title"
                :title="$t('llc.orgChart.processOpensWorkflow')"
                :aria-label="$t('llc.orgChart.processOpensWorkflow')"
              >{{ nodeText(node, 'workflow_id') }}</p>
              <div class="org-meta">
                <span class="process-role">{{ nodeText(node, 'role_name') }}</span>
                <!-- #14549: the canvas shows the attachment but could not
                     change it. `.stop` keeps the click from also selecting the
                     node, which would navigate to the workflow builder — the
                     mutation itself is OrgChart.vue's job, reached by event. -->
                <button
                  type="button"
                  class="process-detach-btn"
                  data-testid="process-detach-btn"
                  :aria-label="processDetachLabel(node)"
                  @click.stop="emit('process-detached', nodeText(node, 'role_id'), nodeText(node, 'workflow_id'))"
                >
                  <Icon name="times" />
                </button>
              </div>
            </template>
            <!-- GH#13939: Company OS org nodes are read-only descriptors -->
            <template v-else-if="node.type === 'org-person'">
              <p class="org-title">{{ nodeText(node, 'title') }}</p>
              <div class="org-meta">
                <!-- GH#13941: this was a bare coloured dot — colour was the only
                     signal it carried, and a paused agent was indistinguishable
                     from an errored one to a reader who cannot separate the
                     hues. The chip pairs the active rule's colour with a
                     distinct marker shape and the rule's translated name. -->
                <span class="rule-chip">
                  <span class="rule-marker" aria-hidden="true"></span>
                  <span class="rule-chip-label">{{ nodeRuleLabel(node) }}</span>
                </span>
                <!-- GH#13936: adapter_type is agent vocabulary. A person's node
                     already shows their role as the title, and their adapter_type
                     is the literal "human" — untranslated in all 11 locales. This
                     mirrors the same guard in OrgTreeNode.vue; the canvas is the
                     second renderer of the same org-chart payload. -->
                <span v-if="!nodeFlag(node, 'is_human')" class="org-adapter">{{ nodeText(node, 'adapter_type') }}</span>
              </div>
            </template>
          </div>
          <div v-if="!readonly" class="port port-in" @pointerdown.stop="startConnect(node.id, 'in', $event)"></div>
          <div v-if="!readonly" class="port port-out" @pointerdown.stop="startConnect(node.id, 'out', $event)"></div>
        </div>

        <!-- Empty State -->
        <div v-if="nodes.length === 0" class="empty-state">
          <Icon name="project-diagram" />
          <h3>{{ $t('workflow.canvas.emptyTitle') }}</h3>
          <p>{{ $t('workflow.canvas.emptyDescription') }}</p>
          <button v-if="!readonly" class="btn-primary" @click="addStepNode"><Icon name="plus" /> {{ $t('workflow.canvas.addStep') }}</button>
        </div>
      </div>

      <!-- GH#13941: legend — derived from the same evaluation the nodes use, so
           it lists exactly the rules that won on a node currently drawn. Sits
           outside `.canvas-content` so panning and zooming never move it. -->
      <div v-if="legendRules.length > 0" class="canvas-legend" data-testid="canvas-legend">
        <span class="canvas-legend-title">{{ $t('llc.canvasRules.legendTitle') }}</span>
        <ul class="canvas-legend-items">
          <li
            v-for="rule in legendRules"
            :key="rule.id"
            class="canvas-legend-item"
            :class="[`rule-${rule.swatch}`, `rule-shape-${rule.shape}`]"
            :data-rule-id="rule.id"
          >
            <span class="rule-marker" aria-hidden="true"></span>
            <span>{{ ruleLabel(rule) }}</span>
          </li>
        </ul>
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
import Icon, { type IconName } from '@/components/ui/Icon.vue'
import { ref, reactive, computed, nextTick, useId } from 'vue';
import { useI18n } from 'vue-i18n';
import { useConfirmDialog } from '@/composables/useConfirmDialog';
import type { WorkflowNode } from '@/composables/useWorkflowBuilder';
import { CANVAS_NODE_WIDTH } from './canvasNode';
import type { CanvasNode, CanvasNodeType, CanvasTab } from './canvasNode';
import {
  SELECTABLE_RULE_DIMENSIONS,
  STATUS_RULES,
  OWNER_RULES,
  activeRules,
  matchRule,
  orgNodeFacts,
  rulesForDimension,
  type CanvasNodeFacts,
  type CanvasNodeRule,
  type CanvasRuleDimension,
} from './canvasNodeRules';

const { t } = useI18n();
const { confirm } = useConfirmDialog();

/**
 * GH#13939: `readonly` and `tabs` are additive and default to the previous
 * behaviour, so `WorkflowBuilderView.vue` is unaffected. `nodes` widens to
 * `CanvasNode` (a superset of `WorkflowNode`) so Company OS can draw org
 * nodes on the same canvas.
 */
const props = withDefaults(
  defineProps<{
    nodes: CanvasNode[];
    selectedNodeId: string | null;
    readonly?: boolean;
    tabs?: CanvasTab[];
    activeTabId?: string | null;
  }>(),
  { readonly: false, tabs: () => [], activeTabId: null },
);
const emit = defineEmits<{
  (e: 'node-added', node: WorkflowNode): void;
  (e: 'node-removed', nodeId: string): void;
  (e: 'node-moved', nodeId: string, pos: { x: number; y: number }): void;
  (e: 'node-selected', nodeId: string | null): void;
  (e: 'nodes-connected', src: string, tgt: string): void;
  (e: 'save-workflow', name: string, desc: string): void;
  (e: 'tab-selected', tabId: string): void;
  // #14549: an org-process node's own detach control. Emitted rather than
  // called against the API directly — this component is shared with real
  // workflow editing and must stay ignorant of the LLC endpoints.
  (e: 'process-detached', roleId: string, workflowId: string): void;
}>();

const showVisionDropdown = ref(false);

// #13939: these are Icon component names — they were previously rendered as
// `<i :class="…">`, which silently produced no icon at all.
// #13996: keyed by CanvasNodeType (not `string`), so a node type without an
// icon is a compile error rather than an `<Icon :name="undefined">` warning.
const nodeIcons: Record<CanvasNodeType, IconName> = {
  step: 'terminal',
  condition: 'code-branch',
  switch: 'random',
  parallel: 'columns',
  loop: 'sync-alt',
  'vision-capture': 'camera',
  'vision-find-element': 'search',
  'vision-click': 'mouse-pointer',
  'vision-type-text': 'keyboard',
  'vision-ocr': 'font',
  'vision-wait': 'clock',
  'org-person': 'user',
  'org-group': 'sitemap',
  'org-process': 'project-diagram',
};
const nodeLabels = computed(() => ({
  'org-process': t('llc.orgChart.processNodeLabel'),
  step: t('workflow.canvas.stepLabel'),
  condition: t('workflow.canvas.conditionLabel'),
  switch: t('workflow.canvas.switchLabel'),
  parallel: t('workflow.canvas.parallelLabel'),
  // #9724: 'loop' is part of WorkflowNode['type'] but had no label entry
  // #13996: the key exists in all 11 locales, so the hard-coded English
  // fallback was both dead and a hard-coded UI string.
  loop: t('workflow.canvas.loopLabel'),
  'vision-capture': t('workflow.canvas.visionCapture'),
  'vision-find-element': t('workflow.canvas.visionFindElement'),
  'vision-click': t('workflow.canvas.visionClick'),
  'vision-type-text': t('workflow.canvas.visionTypeText'),
  'vision-ocr': t('workflow.canvas.visionOcr'),
  'vision-wait': t('workflow.canvas.visionWait'),
}));

/**
 * Header caption: authoring nodes are labelled by type, org nodes carry their
 * own label (the person's or unit's name) in `data.label` (GH#13939).
 */
function nodeTitle(node: CanvasNode): string {
  const byType = (nodeLabels.value as Record<string, string | undefined>)[node.type];
  return byType ?? nodeText(node, 'label');
}

/** Read a string field off a node's untyped `data` bag. */
function nodeText(node: CanvasNode, key: string): string {
  const value = (node.data as Record<string, unknown>)[key];
  return typeof value === 'string' ? value : '';
}

/** Boolean counterpart to `nodeText` — `nodeText` returns '' for a boolean, so a
 *  flag read through it is always falsy and can never gate anything (GH#13936). */
function nodeFlag(node: CanvasNode, key: string): boolean {
  return (node.data as Record<string, unknown>)[key] === true;
}

/**
 * Accessible name for a node (#14609): kind, name and — for an org-person,
 * the only node type carrying a status concept — its current state.
 *
 * Built from `STATUS_RULES`/`OWNER_RULES` directly rather than through
 * `ruleForNode`/`nodeRuleLabel`: those read the *active* `colourMode`, and the
 * announcement must not change depending on which dimension the sighted
 * legend happens to be colouring by.
 */
function nodeAriaLabel(node: CanvasNode): string {
  const kind = nodeKindLabel(node);
  const name = nodeTitle(node);
  const state = nodeStatusLabel(node);
  return state
    ? t('workflow.canvas.nodeAriaLabelWithState', { kind, name, state })
    : t('workflow.canvas.nodeAriaLabel', { kind, name });
}

/** The "kind" component of a node's accessible name. */
function nodeKindLabel(node: CanvasNode): string {
  if (node.type === 'org-person') {
    const facts = orgFacts.value.get(node.id);
    if (facts) return ruleLabel(matchRule(OWNER_RULES, facts));
  }
  if (node.type === 'org-group') return t('llc.orgChart.canvasGroupKind');
  return (nodeLabels.value as Record<string, string | undefined>)[node.type] ?? '';
}

/** The "state" component of a node's accessible name — '' when the node carries none. */
function nodeStatusLabel(node: CanvasNode): string {
  const facts = orgFacts.value.get(node.id);
  return facts ? ruleLabel(matchRule(STATUS_RULES, facts)) : '';
}

/**
 * Accessible name for the detach control (#14549).
 *
 * The node's only visible text is a bare workflow id and role name — a
 * screen reader landing on a bare "×" button would not know what it detaches.
 * Mirrors the `processOpensWorkflow` description pattern already on this node.
 */
function processDetachLabel(node: CanvasNode): string {
  return t('llc.orgChart.processDetach', {
    workflow: nodeText(node, 'workflow_id'),
    role: nodeText(node, 'role_name'),
  });
}

/**
 * Position, plus the size a grouping container carries in `data`.
 * #13996: only `org-group` is sized from `data` — `WorkflowNode['data']` is an
 * arbitrary bag, so honouring width/height for every type let unrelated
 * authoring payloads silently resize their node.
 */
function nodeStyle(node: CanvasNode): Record<string, string> {
  const style: Record<string, string> = {
    left: `${node.position.x}px`,
    top: `${node.position.y}px`,
  };
  if (node.type !== 'org-group') return style;
  const data = node.data as Record<string, unknown>;
  if (typeof data.width === 'number') style.width = `${data.width}px`;
  if (typeof data.height === 'number') style.height = `${data.height}px`;
  return style;
}

/* ------------------------------------------------------------------ *
 * GH#13941: declarative node colouring + legend.
 *
 * Presentation only — the rules read facts the nodes already carry and
 * change nothing that is fetched, authorised or persisted. The chosen
 * dimension is component state; it is deliberately not persisted, so the
 * canvas keeps its single source of truth in the org-chart payload.
 * ------------------------------------------------------------------ */

const colourMode = ref<CanvasRuleDimension>('status');

/** Facts per node id, for the nodes the rules apply to (org people only). */
const orgFacts = computed(() => {
  const byId = new Map<string, CanvasNodeFacts>();
  for (const node of props.nodes) {
    const facts = orgNodeFacts(node);
    if (facts) byId.set(node.id, facts);
  }
  return byId;
});

const hasOrgNodes = computed(() => orgFacts.value.size > 0);
const factsOnCanvas = computed(() => [...orgFacts.value.values()]);
const activeRuleSet = computed(() => rulesForDimension(colourMode.value, factsOnCanvas.value));
/** Only rules that won on a node currently drawn — the legend's contents. */
const legendRules = computed(() => activeRules(activeRuleSet.value, factsOnCanvas.value));

const dimensionLabels = computed<Record<CanvasRuleDimension, string>>(() => ({
  status: t('llc.canvasRules.dimension.status'),
  owner: t('llc.canvasRules.dimension.owner'),
  tool: t('llc.canvasRules.dimension.tool'),
}));

function ruleForNode(node: CanvasNode): CanvasNodeRule | null {
  const facts = orgFacts.value.get(node.id);
  return facts ? matchRule(activeRuleSet.value, facts) : null;
}

/** Translated rule name, or the raw data value for a data-derived rule. */
function ruleLabel(rule: CanvasNodeRule): string {
  return rule.labelKey ? t(rule.labelKey) : (rule.labelText ?? '');
}

function nodeRuleLabel(node: CanvasNode): string {
  const rule = ruleForNode(node);
  return rule ? ruleLabel(rule) : '';
}

function nodeRuleId(node: CanvasNode): string | undefined {
  return ruleForNode(node)?.id;
}

/** Swatch (colour token) + shape classes for a node; empty for authoring nodes. */
function ruleClasses(node: CanvasNode): string[] {
  const rule = ruleForNode(node);
  return rule ? [`rule-${rule.swatch}`, `rule-shape-${rule.shape}`] : [];
}

const canvasRef = ref<HTMLElement | null>(null);
const zoom = ref(1);
const pan = reactive({ x: 50, y: 50 });
const isPanning = ref(false);
/**
 * Whether the gesture that is ending actually moved something — panned the
 * canvas, or (#14610) dragged a node — rather than merely pressed and
 * released in place.
 *
 * Originated as `pannedThisGesture` (#14079): a pan translates the canvas by
 * the pointer delta, so the node the gesture started on stays under the
 * cursor/finger. The `mouseup`/`pointerup` therefore lands on that node, the
 * browser fires `click`, and the node's drawer opens over the canvas the
 * user was navigating.
 *
 * #14610 generalised it from "panned" to "moved something": a touch drag has
 * the identical hazard for a node — the finger lifts over the node it just
 * dragged, `click` fires, and without this the drawer would open right after
 * the user repositioned it. One flag covers both cases (and both input
 * types) rather than a second, parallel one — `selectNode` only ever needs
 * to know "did this gesture move", not which kind of move it was.
 *
 * Cleared on the next `pointerdown` rather than by the click it suppresses: a
 * gesture that ends over empty canvas is followed by no node click at all, so
 * a flag cleared only on click would stay set and swallow the user's next
 * genuine click/tap on a node.
 */
const movedThisGesture = ref(false);
const panStart = reactive({ x: 0, y: 0 });
const dragNode = ref<CanvasNode | null>(null);
const dragOffset = reactive({ x: 0, y: 0 });
const drawingLine = ref(false);
const lineStart = reactive({ nodeId: '', x: 0, y: 0 });
const mousePos = reactive({ x: 0, y: 0 });
const showSaveDialog = ref(false);
const saveName = ref('');
const saveDesc = ref('');

/* ------------------------------------------------------------------ *
 * GH#14610: touch support.
 *
 * The canvas unifies mouse and touch on Pointer Events (`pointerdown` /
 * `pointermove` / `pointerup` / `pointercancel`) rather than adding a
 * parallel `touchstart`/`touchmove`/`touchend` path — one input path per
 * gesture, per the repo's "reuse, never fork" rule. `PointerEvent` carries
 * `clientX`/`clientY`/`shiftKey`/`button` exactly like `MouseEvent`, so the
 * existing pan/drag/connect math is untouched; only the event names and the
 * "what starts a pan" decision below changed.
 *
 * How a one-finger touch is disambiguated between pan and drag: there is no
 * modifier key on touch (no shift, no middle button), so the decision moves
 * from "which key is held" to "where the finger landed" — a press starting
 * on empty canvas (or an org-group container, matching the existing
 * shift-drag-from-anywhere behaviour, #13996) pans; a press starting on a
 * node drags it (`onNodePointerDown`), exactly as a plain mouse press
 * already did. `pointerType === 'touch'` is the only new branch in
 * `startPan`; everything downstream (movement math, drag math, the
 * `movedThisGesture` suppression) is shared with mouse.
 *
 * Two-finger touch is reserved for pinch-to-zoom (`activePointers`,
 * `beginPinch`, `applyPinchZoom`) rather than a two-finger pan — pinch takes
 * over as soon as a second pointer is detected, cancelling any in-flight
 * one-finger pan/drag from the first finger.
 */
const activePointers = new Map<number, { x: number; y: number }>();
const pinchStartDistance = ref(0);
const pinchStartZoom = ref(1);

/** Distance between the two active pointers, in client px; 0 with fewer than two. */
function pinchDistance(): number {
  const points = [...activePointers.values()];
  if (points.length < 2) return 0;
  return Math.hypot(points[0].x - points[1].x, points[0].y - points[1].y);
}

/** A second pointer just went down: hand off from pan/drag to pinch-zoom. */
function beginPinch(): void {
  isPanning.value = false;
  dragNode.value = null;
  pinchStartDistance.value = pinchDistance();
  pinchStartZoom.value = zoom.value;
}

/**
 * Widens capture past the element the gesture started on — without it, a
 * touch that drifts off `canvasRef` (or off whichever node it started on)
 * during a pan/drag stops delivering `pointermove` there. Feature-detected:
 * unsupported in jsdom (and on very old engines), where the gesture still
 * works because tests dispatch events directly on the target element.
 */
function capturePointer(e: PointerEvent): void {
  const el = canvasRef.value;
  if (el && typeof el.setPointerCapture === 'function') el.setPointerCapture(e.pointerId);
}

/* ------------------------------------------------------------------ *
 * GH#14609: keyboard operation — a roving-tabindex node graph.
 *
 * `focusedNodeId` is only ever written by user-driven focus (Tab landing on
 * the roving stop, or an arrow-key move) — never reset when `nodes` changes,
 * so a canvas re-layout (same ids, new node objects/positions) keeps the
 * focused DOM element focused: Vue's `:key="node.id"` patching reuses the
 * existing element rather than recreating it, and native browser focus
 * survives that unaffected. A naive index-based (rather than id-based)
 * implementation loses this for free.
 * ------------------------------------------------------------------ */

const _uid = useId();
const navInstructionsId = `workflow-canvas-nav-instructions-${_uid}`;
const moveInstructionsId = `workflow-canvas-move-instructions-${_uid}`;
/** Move instructions only apply when dragging itself is possible. */
const instructionsId = computed(() =>
  props.readonly ? navInstructionsId : `${navInstructionsId} ${moveInstructionsId}`,
);

const focusedNodeId = ref<string | null>(null);
const nodeEls = new Map<string, HTMLElement>();

function registerNodeEl(id: string, el: Element | null): void {
  if (el instanceof HTMLElement) nodeEls.set(id, el);
  else nodeEls.delete(id);
}

/** Row tolerance for the default (first-tab) reading order: nodes within this
 *  many px of vertical offset are treated as the same visual row. */
const NODE_ROW_TOLERANCE = 60;

/** `nodes` sorted into a predictable top-to-bottom, start-to-end reading order —
 *  used only to pick the initial roving tab stop before any focus has occurred. */
const visualOrder = computed<CanvasNode[]>(() =>
  [...props.nodes].sort((a, b) => {
    const rowDelta = a.position.y - b.position.y;
    if (Math.abs(rowDelta) > NODE_ROW_TOLERANCE) return rowDelta;
    return a.position.x - b.position.x;
  }),
);

/** The single node that is a Tab stop. Falls back to reading order when
 *  nothing has been focused yet, or the previously-focused node is gone. */
const rovingTabStopId = computed<string | null>(() => {
  if (focusedNodeId.value && props.nodes.some((n) => n.id === focusedNodeId.value)) {
    return focusedNodeId.value;
  }
  return visualOrder.value[0]?.id ?? null;
});

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

function addCase(node: CanvasNode) {
  const data = node.data as Record<string, unknown>;
  const cases = (data.cases as string[]) || [];
  cases.push('');
  data.cases = cases;
}

function removeCase(node: CanvasNode, index: number) {
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

function selectNode(id: string) {
  // The click/tap that closes a pan or a node drag is not a selection
  // (#14079, generalised for touch drag by #14610).
  if (movedThisGesture.value) return;
  emit('node-selected', id);
}

/** Fixed-size step for a keyboard-driven node move — matches the background grid. */
const NODE_KEYBOARD_MOVE_STEP = 20;

type SpatialDirection = 'up' | 'down' | 'left' | 'right';

/**
 * Resolve an arrow key to a canvas-space direction, folding in writing
 * direction (#14609 acceptance): in an RTL locale, ArrowRight is "back" in
 * reading order — the same node it would reach visually to the left — and
 * ArrowLeft is "forward". ArrowUp/ArrowDown are direction-agnostic.
 *
 * Node positions themselves are never mirrored for RTL (`nodeStyle` always
 * writes a physical `left`, see the #13939 pan/position tests) — only the
 * *meaning* of the two horizontal keys flips, matching how a toolbar or
 * listbox's horizontal arrow-key navigation is expected to behave per the
 * writing-direction convention, independent of whether the widget's own
 * visual layout mirrors.
 */
function resolveArrowDirection(key: string): SpatialDirection | null {
  if (key === 'ArrowUp') return 'up';
  if (key === 'ArrowDown') return 'down';
  if (key === 'ArrowLeft') return isRtl() ? 'right' : 'left';
  if (key === 'ArrowRight') return isRtl() ? 'left' : 'right';
  return null;
}

/** Read fresh on every keypress — not a computed: `document.documentElement.dir`
 *  is not a Vue-reactive source, so caching it would never pick up a runtime
 *  locale switch (`setLocale` in `src/i18n/index.ts` flips the attribute). */
function isRtl(): boolean {
  return document.documentElement.dir === 'rtl';
}

/** A node's approximate visual centre, in canvas space — same anchor the
 *  connection-line paths already use (`x + 240`, `y + 50`, see `connections`). */
function nodeCenter(node: CanvasNode): { x: number; y: number } {
  return { x: node.position.x + CANVAS_NODE_WIDTH / 2, y: node.position.y + 50 };
}

/**
 * Nearest node in `direction` from `from`, by visual position rather than
 * array order (#14609 acceptance) — a directional nearest-neighbour search:
 * candidates strictly on the correct side of `from` are scored by distance
 * along the primary axis plus a heavily-weighted cross-axis penalty, so
 * movement favours a node roughly aligned with the current one (a laid-out
 * grid or row) over one merely closer in Euclidean distance off-axis.
 */
function findNodeInDirection(from: CanvasNode, direction: SpatialDirection): CanvasNode | null {
  const origin = nodeCenter(from);
  let best: CanvasNode | null = null;
  let bestScore = Infinity;
  for (const candidate of props.nodes) {
    if (candidate.id === from.id) continue;
    const point = nodeCenter(candidate);
    const dx = point.x - origin.x;
    const dy = point.y - origin.y;
    let primary: number;
    let cross: number;
    if (direction === 'left') { if (dx >= 0) continue; primary = -dx; cross = dy; }
    else if (direction === 'right') { if (dx <= 0) continue; primary = dx; cross = dy; }
    else if (direction === 'up') { if (dy >= 0) continue; primary = -dy; cross = dx; }
    else { if (dy <= 0) continue; primary = dy; cross = dx; }
    const score = primary + Math.abs(cross) * 2;
    if (score < bestScore) { bestScore = score; best = candidate; }
  }
  return best;
}

/** Move focus (not the node) to the nearest node in `direction`, if any. */
function focusNodeInDirection(from: CanvasNode, direction: SpatialDirection): void {
  const target = findNodeInDirection(from, direction);
  if (!target) return;
  focusedNodeId.value = target.id;
  void nextTick(() => nodeEls.get(target.id)?.focus());
}

/** Move the node itself (drag's keyboard equivalent, #14609) — only ever
 *  called when `!readonly`, mirroring `onPointerMove`'s own drag emit. */
function moveNodeByKeyboard(node: CanvasNode, direction: SpatialDirection): void {
  const delta: Record<SpatialDirection, { x: number; y: number }> = {
    up: { x: 0, y: -NODE_KEYBOARD_MOVE_STEP },
    down: { x: 0, y: NODE_KEYBOARD_MOVE_STEP },
    left: { x: -NODE_KEYBOARD_MOVE_STEP, y: 0 },
    right: { x: NODE_KEYBOARD_MOVE_STEP, y: 0 },
  };
  const { x: dx, y: dy } = delta[direction];
  emit('node-moved', node.id, {
    x: Math.max(0, node.position.x + dx),
    y: Math.max(0, node.position.y + dy),
  });
}

/**
 * Keyboard entry point for a node (#14609): Enter/Space selects — the same
 * effect as `@click` — Escape deselects, a plain arrow moves focus, and a
 * Ctrl/Cmd+arrow moves the node (only when not readonly; dragging is a
 * mutation the read-only Company OS canvas must not offer).
 *
 * Guarded to `e.target === e.currentTarget`: a keypress that bubbled up from
 * one of the node's own inputs/selects/buttons (typing, picking an option)
 * must reach that control, not be reinterpreted as a node-level shortcut.
 */
function onNodeKeydown(node: CanvasNode, e: KeyboardEvent): void {
  if (e.target !== e.currentTarget) return;

  if (e.key === 'Enter' || e.key === ' ' || e.key === 'Spacebar') {
    e.preventDefault();
    selectNode(node.id);
    return;
  }
  if (e.key === 'Escape') {
    e.preventDefault();
    emit('node-selected', null);
    return;
  }

  const direction = resolveArrowDirection(e.key);
  if (!direction) return;
  e.preventDefault();

  if (e.ctrlKey || e.metaKey) {
    if (props.readonly) return;
    moveNodeByKeyboard(node, direction);
    return;
  }
  focusNodeInDirection(node, direction);
}

async function clearCanvas() {
  if (props.nodes.length && (await confirm({ title: t('common.confirm'), message: t('workflow.canvas.clearConfirm') }))) {
    props.nodes.forEach(n => emit('node-removed', n.id));
    emit('node-selected', null);
  }
}

function autoLayout() {
  props.nodes.forEach((node, i) => {
    emit('node-moved', node.id, { x: 100 + (i % 3) * 300, y: 100 + Math.floor(i / 3) * 180 });
  });
}

/** Zoom clamp shared by every way of changing it — buttons, wheel, pinch. */
const ZOOM_MIN = 0.3;
const ZOOM_MAX = 2;
function clampZoom(value: number): number { return Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, value)); }

function zoomIn() { zoom.value = clampZoom(zoom.value + 0.1); }
function zoomOut() { zoom.value = clampZoom(zoom.value - 0.1); }
function resetZoom() { zoom.value = 1; pan.x = 50; pan.y = 50; }
function handleWheel(e: WheelEvent) { zoom.value = clampZoom(zoom.value + (e.deltaY > 0 ? -0.05 : 0.05)); }

/** Rescale from the pinch's starting distance/zoom — proportional, like `handleWheel`
 *  and the zoom buttons, none of which anchor around a point either (#14610). */
function applyPinchZoom(): void {
  const distance = pinchDistance();
  if (pinchStartDistance.value <= 0 || distance <= 0) return;
  zoom.value = clampZoom(pinchStartZoom.value * (distance / pinchStartDistance.value));
}

function startPan(e: PointerEvent) {
  movedThisGesture.value = false;
  activePointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
  capturePointer(e);
  if (activePointers.size >= 2) { beginPinch(); return; }

  // #14610: touch carries no shift key and no middle button, so a one-finger
  // press starting on empty canvas (or an org container, handed on below) is
  // always a pan — mirrors the mouse's shift/middle-click modifier.
  const isTouchPan = e.pointerType === 'touch';
  if (isTouchPan || e.button === 1 || e.shiftKey) { isPanning.value = true; panStart.x = e.clientX - pan.x; panStart.y = e.clientY - pan.y; }
}

/**
 * #13996: a press on a node used to stop dead here (`@mousedown.stop`), so it
 * never reached `startPan` on `.canvas-area`. An `org-group` container is
 * sized to its whole subtree and covers the drawing area, which left the
 * shift-drag pan the UI advertises working only in the canvas gutters. A pan
 * gesture is handed on; everything else still starts a node drag.
 *
 * #14610: a second finger landing on a node (rather than empty canvas) is
 * still a pinch — `activePointers` is tracked here too, before any of the
 * single-pointer branches below run.
 */
function onNodePointerDown(node: CanvasNode, e: PointerEvent) {
  // Reset here too: a plain press on a node stops propagation below, so
  // `startPan` never runs and would never clear the flag.
  movedThisGesture.value = false;
  activePointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
  capturePointer(e);
  if (activePointers.size >= 2) { beginPinch(); e.stopPropagation(); return; }

  if (e.shiftKey || e.button === 1) return;

  // #14610: `readonly` (Company OS) never drags a node — see below — so on
  // touch a one-finger press starting on a node has nothing else useful to
  // do there. Handing it on to `startPan` (by not stopping propagation) is
  // the touch equivalent of the shift/middle-click bubble above: without
  // this, every node — and every org-group container, the exact shape
  // #13996 already fixed for mouse — would be a dead zone for touch pan,
  // leaving only the canvas's bare gutters pannable on a tablet.
  if (e.pointerType === 'touch' && props.readonly) return;

  e.stopPropagation();
  // #14610: readonly (Company OS) must not let a press reposition a node —
  // the same rule `onNodeKeydown` already applies to the keyboard move
  // shortcut. A mouse press here is simply absorbed (unchanged pre-#14610
  // behaviour); the plain `click` that follows still reaches `selectNode`.
  if (props.readonly) return;
  startDrag(node, e);
}

function startDrag(node: CanvasNode, e: PointerEvent) {
  dragNode.value = node;
  dragOffset.x = e.clientX - node.position.x * zoom.value - pan.x;
  dragOffset.y = e.clientY - node.position.y * zoom.value - pan.y;
}

function startConnect(nodeId: string, port: string, e: PointerEvent) {
  drawingLine.value = true;
  const node = props.nodes.find(n => n.id === nodeId);
  if (node) {
    lineStart.nodeId = nodeId;
    lineStart.x = node.position.x + (port === 'out' ? 240 : 0);
    lineStart.y = node.position.y + 50;
  }
  mousePos.x = e.clientX; mousePos.y = e.clientY;
  capturePointer(e);
}

function onPointerMove(e: PointerEvent) {
  if (activePointers.has(e.pointerId)) activePointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
  if (activePointers.size >= 2) { applyPinchZoom(); return; }

  mousePos.x = e.clientX; mousePos.y = e.clientY;
  if (isPanning.value) {
    pan.x = e.clientX - panStart.x; pan.y = e.clientY - panStart.y;
    // Set on movement, not on press: a shift-click/tap that never moves is
    // still a selection, and suppressing it would break selecting with shift
    // held (mouse) or a plain tap (touch).
    movedThisGesture.value = true;
  }
  else if (dragNode.value) {
    const x = (e.clientX - dragOffset.x - pan.x) / zoom.value;
    const y = (e.clientY - dragOffset.y - pan.y) / zoom.value;
    emit('node-moved', dragNode.value.id, { x: Math.max(0, x), y: Math.max(0, y) });
    // #14610: a drag that actually moved the node must not also select it
    // when the gesture ends — the drag counterpart of the pan case above.
    movedThisGesture.value = true;
  }
}

function endInteraction(e: PointerEvent) {
  if (drawingLine.value) {
    const rect = canvasRef.value?.getBoundingClientRect();
    if (rect) {
      const x = (e.clientX - rect.left - pan.x) / zoom.value;
      const y = (e.clientY - rect.top - pan.y) / zoom.value;
      const target = props.nodes.find(n => x >= n.position.x && x <= n.position.x + 240 && y >= n.position.y && y <= n.position.y + 100);
      if (target && target.id !== lineStart.nodeId) emit('nodes-connected', lineStart.nodeId, target.id);
    }
  }
  // #14610: lifting one finger of a pinch leaves the other still down; it
  // does not resume as a one-finger pan — the user has to lift fully and
  // start a fresh gesture, same as releasing mid-drag does for a mouse.
  activePointers.delete(e.pointerId);
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
.badge-experimental { font-size: 9px; padding: var(--spacing-px) var(--spacing-1); background: var(--color-warning); color: var(--wfcanvas-on-warning); border-radius: var(--radius-default); font-weight: 700; text-transform: uppercase; line-height: 1; }
.toolbar-divider { width: 1px; height: var(--spacing-6); background: var(--border-default); margin: var(--spacing-0) var(--spacing-1); }

/* #14610: `touch-action: none` on every custom-gesture surface — without it, the
   browser's own touch scroll/pinch-zoom competes with our own pan/pinch/drag
   handling for the same one- and two-finger gestures. */
.canvas-area { flex: 1; position: relative; overflow: hidden; background: linear-gradient(var(--border-subtle) 1px, transparent 1px), linear-gradient(90deg, var(--border-subtle) 1px, transparent 1px); background-size: 20px 20px; cursor: grab; touch-action: none; }
.canvas-area:active { cursor: grabbing; }
.canvas-content { position: absolute; min-width: 100%; min-height: 100%; transform-origin: 0 0; }

.connections-svg { position: absolute; inset: 0; width: 3000px; height: 2000px; pointer-events: none; }
.connection-line { fill: none; stroke: var(--color-primary); stroke-width: 2; }
.drawing-line { fill: none; stroke: var(--color-primary); stroke-width: 2; stroke-dasharray: 5; opacity: 0.6; }

.workflow-node { position: absolute; width: 240px; background: var(--bg-secondary); border: 2px solid var(--border-default); border-radius: var(--radius-xl); box-shadow: var(--shadow-sm); cursor: move; user-select: none; touch-action: none; }
.workflow-node:hover { box-shadow: var(--shadow-md); }
.workflow-node.selected { border-color: var(--color-primary); box-shadow: 0 0 0 3px var(--color-primary-bg); }
/* #14609: keyboard focus indicator — nodes carry no native focus styling of
   their own (a styled `<div>`), so this is the only visible cue a keyboard
   user gets that a node is focused. */
.workflow-node:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 2px; }

/* #14609: visually hidden but readable by a screen reader — same rule as
   LoadingSpinner.vue's `.sr-only`, kept in sync rather than shared, since
   this file's styles are scoped. */
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: var(--spacing-0);
  margin: var(--spacing-neg-px);
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
.workflow-node.step .node-header { background: var(--color-primary); }
.workflow-node.condition .node-header { background: var(--color-warning); }
.workflow-node.switch .node-header { background: var(--wfcanvas-node-switch); }
.workflow-node[class*="vision-"] .node-header { background: linear-gradient(135deg, var(--wfcanvas-node-vision-from), var(--wfcanvas-node-vision-to)); }
.workflow-node.org-person .node-header { background: var(--color-info); }
.workflow-node.org-group { background: var(--color-info-bg); border-style: dashed; cursor: default; }
.workflow-node.org-group .node-header { background: transparent; color: var(--text-secondary); border-bottom: 1px dashed var(--border-default); }
.org-title { margin: var(--spacing-0); font-size: var(--text-xs); color: var(--text-secondary); }
.org-meta { display: flex; align-items: center; gap: var(--spacing-2); font-size: var(--text-xs); color: var(--text-tertiary); }

/* GH#13941: one swatch class per rule, each binding a single design token to
   --rule-accent. The node accent stripe and every marker read the accent from
   there, so a rule's colour is declared exactly once and never as a literal. */
.rule-status-active { --rule-accent: var(--color-success); }
.rule-status-idle { --rule-accent: var(--color-info); }
.rule-status-paused { --rule-accent: var(--color-warning); }
.rule-status-error { --rule-accent: var(--color-error); }
.rule-status-terminated { --rule-accent: var(--color-secondary); }
.rule-status-unknown { --rule-accent: var(--text-muted); }
.rule-owner-human { --rule-accent: var(--chart-blue); }
.rule-owner-agent { --rule-accent: var(--chart-purple); }
.rule-owner-unassigned { --rule-accent: var(--color-warning); }
.rule-tool-1 { --rule-accent: var(--chart-1); }
.rule-tool-2 { --rule-accent: var(--chart-2); }
.rule-tool-3 { --rule-accent: var(--chart-3); }
.rule-tool-4 { --rule-accent: var(--chart-4); }
.rule-tool-5 { --rule-accent: var(--chart-5); }
.rule-tool-6 { --rule-accent: var(--chart-6); }
.rule-tool-7 { --rule-accent: var(--chart-7); }
.rule-tool-8 { --rule-accent: var(--chart-8); }
.rule-tool-none { --rule-accent: var(--text-muted); }

/* The accent stripe. Selection still reads on the remaining three sides plus
   the focus ring, so a coloured node never hides which node is selected. */
/* Must stay AFTER `.workflow-node.selected`: equal specificity (0,2,0), so the
   inline-start accent wins on source order alone. Move this above it and the
   stripe silently vanishes on the selected node. */
.workflow-node.org-person { border-inline-start-width: 6px; border-inline-start-color: var(--rule-accent, var(--border-default)); }

.rule-chip { display: inline-flex; align-items: center; gap: var(--spacing-1-5); }
.rule-chip-label { white-space: nowrap; }
.rule-marker { flex: none; width: var(--spacing-2-5); height: var(--spacing-2-5); background: var(--rule-accent, var(--text-muted)); }
.rule-shape-disc .rule-marker { border-radius: 50%; }
.rule-shape-ring .rule-marker { border-radius: 50%; background: transparent; border: 2px solid var(--rule-accent, var(--text-muted)); }
.rule-shape-square .rule-marker { border-radius: var(--radius-default); }
.rule-shape-diamond .rule-marker { border-radius: var(--radius-default); transform: rotate(45deg); }
.rule-shape-triangle .rule-marker { background: transparent; width: 0; height: 0; border-inline: 5px solid transparent; border-bottom: 10px solid var(--rule-accent, var(--text-muted)); }
.rule-shape-bar .rule-marker { height: var(--spacing-1); border-radius: var(--radius-default); }

.rule-mode { display: flex; align-items: center; gap: var(--spacing-1); }
.rule-mode-label { font-size: var(--text-xs); color: var(--text-tertiary); }
.rule-mode-btn { padding: var(--spacing-1) var(--spacing-2); background: transparent; border: 1px solid var(--border-default); border-radius: var(--radius-md); color: var(--text-secondary); font-size: var(--text-xs); cursor: pointer; }
.rule-mode-btn:hover { background: var(--bg-hover); color: var(--text-primary); }
.rule-mode-btn.active { background: var(--bg-tertiary); border-color: var(--color-primary); color: var(--text-primary); }
.rule-mode-btn:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 2px; }

/* max-height: one legend entry per distinct value, so a large company would
   otherwise grow the box up over the nodes it is explaining. */
.canvas-legend { position: absolute; bottom: var(--spacing-3); inset-inline-start: var(--spacing-3); max-width: 240px; max-height: 220px; overflow-y: auto; padding: var(--spacing-2) var(--spacing-3); background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: var(--radius-md); box-shadow: var(--shadow-sm); }
.canvas-legend-title { display: block; font-size: var(--text-xs); font-weight: 600; color: var(--text-secondary); margin-bottom: var(--spacing-1); }
.canvas-legend-items { list-style: none; margin: var(--spacing-0); padding: var(--spacing-0); display: flex; flex-direction: column; gap: var(--spacing-1); }
.canvas-legend-item { display: flex; align-items: center; gap: var(--spacing-2); font-size: var(--text-xs); color: var(--text-secondary); }

.canvas-tabs { display: flex; align-items: center; gap: var(--spacing-1); }
.canvas-tab { padding: var(--spacing-1-5) var(--spacing-3); background: transparent; border: 1px solid transparent; border-radius: var(--radius-md); color: var(--text-secondary); font-size: var(--text-sm); cursor: pointer; }
.canvas-tab:hover { background: var(--bg-hover); color: var(--text-primary); }
.canvas-tab.active { background: var(--bg-tertiary); border-color: var(--color-primary); color: var(--text-primary); }

.branch-labels { display: flex; justify-content: space-between; font-size: var(--text-xs); margin-top: var(--spacing-1); }
.branch-true { color: var(--color-success); font-weight: 600; }
.branch-false { color: var(--color-error); font-weight: 600; }
.switch-cases { display: flex; flex-direction: column; gap: var(--spacing-1); }
.switch-case-row { display: flex; gap: var(--spacing-1); align-items: center; }
.switch-case-row input { flex: 1; }
.delete-case-btn { padding: 2px 6px; background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: var(--radius-default); color: var(--text-secondary); cursor: pointer; font-size: var(--text-xs); line-height: 1; }
.delete-case-btn:hover { color: var(--color-error); }
.add-case-btn { padding: var(--spacing-1) var(--spacing-2); background: transparent; border: 1px dashed var(--border-default); border-radius: var(--radius-default); color: var(--text-secondary); cursor: pointer; font-size: var(--text-xs); text-align: left; }
.add-case-btn:hover { border-color: var(--color-primary); color: var(--color-primary); }

.dropdown-container { position: relative; display: inline-block; }
.dropdown-menu { position: absolute; top: 100%; left: 0; z-index: 10; background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: var(--radius-md); padding: var(--spacing-1) var(--spacing-0); min-width: 180px; box-shadow: 0 4px 12px rgba(0,0,0,0.3); }
.dropdown-menu button { display: flex; align-items: center; gap: var(--spacing-2); width: 100%; padding: var(--spacing-2) var(--spacing-3); border: none; background: none; color: var(--text-primary); cursor: pointer; font-size: 0.85rem; }
.dropdown-menu button:hover { background: var(--bg-tertiary); }
.target-label { font-size: var(--text-xs); color: var(--text-secondary); }
.hint { font-size: var(--text-xs); color: var(--text-secondary); font-style: italic; }

.node-header { display: flex; align-items: center; gap: var(--spacing-2); padding: var(--spacing-2) var(--spacing-3); color: var(--text-on-primary); border-radius: var(--radius-lg) var(--radius-lg) 0 0; font-size: var(--text-sm); font-weight: 600; }
.node-header span { flex: 1; }
.delete-btn { position: relative; padding: var(--spacing-1); background: transparent; border: none; color: inherit; cursor: pointer; opacity: 0.7; border-radius: var(--radius-default); }
.delete-btn:hover { opacity: 1; background: rgba(255,255,255,0.2); }
/* #14610: same WCAG 2.5.5 touch-target widening as `.port`, for the same reason
   — the visible icon stays compact inside the node header on a mouse. */
@media (pointer: coarse) {
  .delete-btn::before {
    content: '';
    position: absolute;
    inset: 50% auto auto 50%;
    width: var(--spacing-12);
    height: var(--spacing-12);
    transform: translate(-50%, -50%);
  }
}

.node-body { padding: var(--spacing-3); display: flex; flex-direction: column; gap: var(--spacing-2); }
.node-body input, .node-body select { width: 100%; padding: var(--spacing-1-5) var(--spacing-2); background: var(--bg-primary); border: 1px solid var(--border-default); border-radius: var(--radius-default); color: var(--text-primary); font-size: var(--text-xs); }
.node-body input:focus, .node-body select:focus { outline: none; border-color: var(--color-primary); }
.node-body input:focus-visible, .node-body select:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 2px; }
.node-body input.mono { font-family: monospace; }
.node-row { display: flex; gap: var(--spacing-2); align-items: center; }
.node-row select { flex: 1; }
.checkbox { display: flex; align-items: center; gap: var(--spacing-1); font-size: var(--text-xs); color: var(--text-secondary); white-space: nowrap; }
.checkbox input { width: 14px; height: 14px; }

.port { position: absolute; width: var(--spacing-3); height: var(--spacing-3); background: var(--bg-secondary); border: 2px solid var(--color-primary); border-radius: 50%; cursor: crosshair; top: 50%; transform: translateY(-50%); touch-action: none; }
.port:hover { transform: translateY(-50%) scale(1.3); background: var(--color-primary); }
.port-in { left: -6px; }
.port-out { right: -6px; }

/* #14610: the visible port stays its usual small size (it sits right on the
   node's edge — growing it would overlap the body), but a coarse (touch)
   pointer gets an invisible `::before` overlay sized to the WCAG 2.5.5
   44x44px minimum, centred on the same point, so the port is still reliably
   tappable without changing how it looks to a mouse user. */
@media (pointer: coarse) {
  .port::before {
    content: '';
    position: absolute;
    inset: 50% auto auto 50%;
    /* #14610: no --spacing token lands on the WCAG 2.5.5 44px minimum exactly
       (--spacing-10 is 40px, --spacing-12 is 48px) — round up to the token
       that clears it rather than a bare literal. */
    width: var(--spacing-12);
    height: var(--spacing-12);
    transform: translate(-50%, -50%);
  }
}

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
.process-role {
  font-size: 0.75rem;
  color: var(--color-text-secondary);
  font-family: var(--font-family-mono, monospace);
}
.process-detach-btn {
  margin-inline-start: auto;
  padding: var(--spacing-1);
  background: transparent;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: var(--radius-default);
  line-height: 1;
}
.process-detach-btn:hover {
  color: var(--color-error);
  background: var(--bg-hover);
}
.process-detach-btn:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}
</style>
