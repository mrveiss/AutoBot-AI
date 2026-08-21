<template>
  <div class="workflow-canvas-container">
    <!-- Toolbar -->
    <div class="canvas-toolbar">
      <div class="toolbar-left">
        <!-- #14611: canvas search — reachable by keyboard, screen-reader
             announced via the live region below, never gated on `readonly`:
             finding a node is a view concern on every canvas this component
             draws, not an authoring one. -->
        <div v-if="nodes.length > 0" class="canvas-search" role="search">
          <div class="canvas-search-field">
            <Icon name="search" class="canvas-search-icon" />
            <input
              ref="searchInputEl"
              v-model="searchQuery"
              type="text"
              class="canvas-search-input"
              role="combobox"
              aria-autocomplete="list"
              :aria-expanded="searchHasQuery"
              aria-controls="canvas-search-listbox"
              :aria-activedescendant="searchActiveOptionId"
              :aria-label="$t('workflow.canvas.searchLabel')"
              :placeholder="$t('workflow.canvas.searchPlaceholder')"
              data-testid="canvas-search-input"
              @keydown="onSearchKeydown"
            />
            <button
              v-if="searchHasQuery"
              type="button"
              class="canvas-search-clear"
              :aria-label="$t('workflow.canvas.searchClear')"
              data-testid="canvas-search-clear"
              @click="clearSearch"
            >
              <Icon name="times" />
            </button>
          </div>
          <!-- #14611: absence must be stated, never left to read as an empty
               canvas (#14064/#13617/#14556's repeat conflation) — the live
               region carries it to a screen reader, `canvas-search-no-results`
               carries it to a sighted one. -->
          <p aria-live="polite" class="sr-only" data-testid="canvas-search-status">{{ searchStatusText }}</p>
          <ul
            v-if="searchHasQuery"
            id="canvas-search-listbox"
            class="canvas-search-results"
            role="listbox"
            :aria-label="$t('workflow.canvas.searchLabel')"
          >
            <li
              v-for="(result, index) in searchResults"
              :id="searchOptionId(index)"
              :key="result.id"
              role="option"
              class="canvas-search-result"
              :class="{ active: index === searchActiveIndex }"
              :aria-selected="index === searchActiveIndex"
              data-testid="canvas-search-result"
              @click="selectSearchResult(result)"
            >
              {{ nodeSearchLabel(result) }}
            </li>
            <li v-if="searchResults.length === 0" class="canvas-search-empty" data-testid="canvas-search-no-results">
              {{ $t('workflow.canvas.searchNoResults', { query: searchQuery.trim() }) }}
            </li>
          </ul>
        </div>
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
        <!-- #14612: multi-select status + clear control. The nodes themselves
             already carry a visual cue for WHICH ones are selected
             (`.multi-selected`, #13941-compliant — shape, not just hue), but
             nothing said HOW MANY until this. Shown only once a second node
             joins the selection: a lone selection is exactly what
             `selectedNodeId`'s own `.selected` styling already communicates,
             so a size-1 chip would only duplicate it. `role="status"` is an
             implicit polite live region — a screen-reader user hears the
             count change as the marquee/shift-click selection grows. -->
        <div v-if="selectedIds.size > 1" class="canvas-selection-status" role="status" data-testid="canvas-selection-status">
          <span>{{ $t('workflow.canvas.selectionStatus', { count: selectedIds.size }) }}</span>
          <button type="button" class="canvas-selection-clear" data-testid="canvas-selection-clear" @click="clearSelection">
            {{ $t('common.deselectAll') }}
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
        <!-- #14611: "fit to selection or filter" — a *second* control, the
             fixed-reset button above stays exactly as it was. -->
        <button class="tool-btn" @click="fitToSelectionOrView" :aria-label="$t('workflow.canvas.fitToSelection')" data-testid="canvas-fit-view"><Icon name="expand-arrows-alt" /></button>
        <div class="toolbar-divider"></div>
        <!-- #14612: undo/redo — never gated on `readonly` (same reasoning as
             zoom/fit above it): the disabled state IS the scope statement —
             a user who presses Undo and sees nothing happen would learn not
             to trust it, so the button is only ever enabled when there is a
             tracked mutation to reverse. `title` puts the boundary in front
             of a sighted mouse user on hover; `aria-describedby` gives a
             screen reader the same text every time either button is
             announced. -->
        <button
          type="button"
          class="tool-btn"
          data-testid="canvas-undo"
          :disabled="!canUndo"
          :aria-label="$t('workflow.canvas.undo')"
          :aria-describedby="undoScopeId"
          :title="$t('workflow.canvas.undoScope')"
          @click="undo"
        >
          <Icon name="undo" />
        </button>
        <button
          type="button"
          class="tool-btn"
          data-testid="canvas-redo"
          :disabled="!canRedo"
          :aria-label="$t('workflow.canvas.redo')"
          :aria-describedby="undoScopeId"
          :title="$t('workflow.canvas.undoScope')"
          @click="redo"
        >
          <Icon name="redo" />
        </button>
        <p :id="undoScopeId" class="sr-only">{{ $t('workflow.canvas.undoScope') }}</p>
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
             :class="[node.type, { selected: selectedNodeId === node.id, 'multi-selected': isMultiOnlySelected(node) }, ...ruleClasses(node)]"
             :data-rule-id="nodeRuleId(node)"
             :data-group-kind="groupKind(node)"
             :data-node-id="node.id"
             :style="nodeStyle(node)"
             role="button"
             :tabindex="rovingTabStopId === node.id ? 0 : -1"
             :aria-label="nodeAriaLabel(node)"
             :aria-pressed="isNodeSelected(node)"
             :aria-describedby="instructionsId"
             @pointerdown="onNodePointerDown(node, $event)"
             @click.stop="selectNode(node.id, $event)"
             @contextmenu.prevent.stop="onNodeContextMenu(node, $event)"
             @focus="focusedNodeId = node.id"
             @keydown="onNodeKeydown(node, $event)">
          <div class="node-header">
            <!-- #14612: shape+icon signal for multi-selection, not colour
                 alone (#13941) — deliberately distinct from `.selected`'s own
                 solid ring so the two states never read as the same thing. -->
            <span v-if="isMultiOnlySelected(node)" class="multi-select-badge" data-testid="node-multi-badge" aria-hidden="true">
              <Icon name="check-circle" />
            </span>
            <Icon :name="nodeIcons[node.type]" />
            <span>{{ nodeTitle(node) }}</span>
            <!-- #14612: context menu's pointer/touch/keyboard-tab entry point
                 — right-click and the ContextMenu/Shift+F10 key (see
                 `onNodeKeydown`) reach the same menu, but neither is
                 discoverable by touch or by a keyboard user who has not
                 memorised the shortcut. A real `<button>` is reachable by Tab
                 and activated by Enter/Space like any other control. -->
            <button
              type="button"
              class="node-menu-btn"
              data-testid="node-menu-btn"
              :aria-label="$t('workflow.canvas.contextMenuButtonLabel', { name: nodeTitle(node) })"
              @click.stop="onNodeContextMenu(node, $event)"
            >
              <Icon name="ellipsis-h" />
            </button>
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
            <!-- #14597: a tool one or more roles carry. `roles` is empty
                 for the moment a node exists with zero roles left, which
                 cannot happen from the API today (a tool node is only ever
                 built from at least one attachment) but is handled the same
                 defensive way `org-group`'s size guard is: no crash, just an
                 empty list. -->
            <template v-else-if="node.type === 'org-tool'">
              <p class="org-title">{{ nodeText(node, 'tool_name') }}</p>
              <ul v-if="toolRoles(node).length > 0" class="tool-roles">
                <li
                  v-for="role in toolRoles(node)"
                  :key="role.role_id"
                  class="tool-role-chip"
                >
                  <span class="tool-role-name">{{ role.role_name }}</span>
                  <!-- #14597: mirrors the org-process detach control — `.stop`
                       keeps the click from also selecting the tool node. -->
                  <button
                    type="button"
                    class="tool-detach-btn"
                    data-testid="tool-detach-btn"
                    :aria-label="toolDetachLabel(node, role)"
                    @click.stop="emit('tool-detached', role.role_id, nodeText(node, 'tool_name'))"
                  >
                    <Icon name="times" />
                  </button>
                </li>
              </ul>
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

      <!-- #14612: marquee (rubber-band) selection — a screen-space rectangle
           drawn over whatever the viewport currently shows, so it lives
           outside `.canvas-content` next to the legend/minimap rather than
           inside it (it must never inherit the pan/zoom transform). -->
      <div v-if="marqueeActive" class="canvas-marquee" :style="marqueeStyle" data-testid="canvas-marquee"></div>

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

      <!-- #14611: overview of a canvas larger than the viewport — sits
           outside `.canvas-content` like the legend, so panning/zooming the
           main view never moves it. Decorative (not itself an authoring
           surface): it never gates on `readonly`, a click pans the main view
           to the point clicked, and the dots/viewport rect are `aria-hidden`
           since search + keyboard navigation are the actual way in for a
           screen-reader user, not this overview. -->
      <div
        v-if="minimapGeometry"
        class="canvas-minimap"
        role="img"
        :aria-label="$t('workflow.canvas.minimapLabel')"
        data-testid="canvas-minimap"
        @pointerdown="onMinimapPointerDown"
      >
        <div
          v-for="node in nodes"
          :key="`minimap-${node.id}`"
          class="canvas-minimap-node"
          :style="minimapNodeStyle(node)"
          aria-hidden="true"
        ></div>
        <div
          v-if="minimapViewportStyle"
          class="canvas-minimap-viewport"
          :style="minimapViewportStyle"
          data-testid="canvas-minimap-viewport"
          aria-hidden="true"
        ></div>
      </div>
    </div>

    <!-- #14612: context menu. Every action re-invokes a handler that already
         exists elsewhere on this card (select, zoom, fit, detach, delete) —
         see `contextMenuActions` — so the menu can never drift from what the
         card/sidebar themselves offer. The backdrop closes it on any outside
         press or right-click; the menu itself closes on Escape and restores
         focus to the node it was opened on. -->
    <div
      v-if="contextMenu.open"
      class="context-menu-backdrop"
      data-testid="canvas-context-menu-backdrop"
      @pointerdown="closeContextMenu"
      @contextmenu.prevent="closeContextMenu"
    ></div>
    <ul
      v-if="contextMenu.open"
      ref="contextMenuEl"
      class="canvas-context-menu"
      role="menu"
      tabindex="-1"
      :aria-label="$t('workflow.canvas.contextMenuLabel')"
      :style="contextMenuStyle"
      data-testid="canvas-context-menu"
      @keydown.esc="closeContextMenuAndRestoreFocus"
    >
      <li v-for="action in contextMenuActions" :key="action.id" role="none">
        <button
          type="button"
          role="menuitem"
          class="canvas-context-menu-item"
          :data-testid="`canvas-context-menu-item-${action.id}`"
          @click="runContextMenuAction(action)"
        >
          {{ action.label }}
        </button>
      </li>
    </ul>

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
import { ref, reactive, computed, nextTick, useId, watch, toRaw } from 'vue';
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
    // #14611: the inbound deep link's target — `OrgChart.vue` sets this once
    // it has resolved `?node=<id>` (`canvasNodeDeepLink.ts`) to a node that
    // actually exists in `nodes`. Optional and defaulted to null so every
    // existing mount (WorkflowBuilderView included) is unaffected.
    focusNodeId?: string | null;
  }>(),
  { readonly: false, tabs: () => [], activeTabId: null, focusNodeId: null },
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
  // #14597: an org-tool node's own per-role detach control, same reasoning —
  // this component only ever emits the LLC mutation, never performs it.
  (e: 'tool-detached', roleId: string, toolName: string): void;
  // #14612: undo's inverse of `nodes-connected` — wires `useWorkflowBuilder`'s
  // `disconnectNodes`, exported since it was written but never called from
  // anywhere, in for the first time.
  (e: 'nodes-disconnected', sourceId: string, targetId: string): void;
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
  // #14597: distinct from 'project-diagram' (org-process) — colour is never
  // the only signal a node type carries (#13941), so a tool also gets its
  // own icon rather than only a caption.
  'org-tool': 'wrench',
};
const nodeLabels = computed(() => ({
  'org-process': t('llc.orgChart.processNodeLabel'),
  'org-tool': t('llc.orgChart.toolNodeLabel'),
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
 * The "{kind}: {name}" text shared by a node's accessible name and the
 * canvas search result label (#14611) — one construction of it, not two.
 *
 * #14657: `name` is `nodeDisplayName`, not `nodeTitle` — for org-process and
 * org-tool, `nodeTitle` is the generic type caption (the same string `kind`
 * already carries), which announced e.g. "Process: Process" with nothing
 * identifying which node it was.
 */
function nodeKindAndName(node: CanvasNode): string {
  const kind = nodeKindLabel(node);
  const name = nodeDisplayName(node);
  return kind ? t('workflow.canvas.nodeAriaLabel', { kind, name }) : name;
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
  const state = nodeStatusLabel(node);
  if (!state) return nodeKindAndName(node);
  return t('workflow.canvas.nodeAriaLabelWithState', {
    kind: nodeKindLabel(node),
    name: nodeDisplayName(node),
    state,
  });
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

/** An org-tool node's roles, off its untyped `data` bag (#14597). */
function toolRoles(node: CanvasNode): { role_id: string; role_name: string }[] {
  const roles = (node.data as Record<string, unknown>).roles;
  return Array.isArray(roles)
    ? roles.filter(
        (role): role is { role_id: string; role_name: string } =>
          typeof role?.role_id === 'string' && typeof role?.role_name === 'string',
      )
    : [];
}

/**
 * Accessible name for a tool node's per-role detach control (#14597).
 *
 * Mirrors `processDetachLabel`: the visible chip carries only a role name, so
 * a screen reader landing on its bare "×" would not know what it detaches or
 * from which tool — this node can list several roles, so the role has to be
 * named explicitly rather than assumed from context.
 */
function toolDetachLabel(node: CanvasNode, role: { role_name: string }): string {
  return t('llc.orgChart.toolDetach', {
    tool: nodeText(node, 'tool_name'),
    role: role.role_name,
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

/**
 * Which kind of container an `org-group` node is — team or reporting unit (#14596).
 *
 * `undefined` for every other node type, so the attribute is absent rather
 * than empty: an empty attribute still matches `[data-group-kind]` in CSS and
 * would style nodes that are not containers at all.
 */
function groupKind(node: CanvasNode): string | undefined {
  if (node.type !== 'org-group') return undefined;
  const kind = (node.data as { kind?: unknown } | undefined)?.kind;
  return typeof kind === 'string' ? kind : undefined;
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

/**
 * Client-space position and pointer type recorded at the start of the
 * current gesture (#14625) — the fixed baseline `onPointerMove` measures
 * against to decide whether the gesture has become a pan/drag, rather than
 * a click/tap that merely jittered.
 *
 * Comparing against this fixed start point on every move (not the previous
 * `pointermove`, and not setting the flag on any single move) is what makes
 * a slow drag built from many 1px steps still count as a drag, while a
 * jittery click that never leaves a small radius around its start does not.
 */
const gestureStart = reactive({ x: 0, y: 0, pointerType: 'mouse' as PointerEvent['pointerType'] });

/**
 * Minimum on-screen movement, in CSS px, before a mouse/pen gesture counts
 * as a pan/drag rather than a click/tap (#14625). 4px matches the drag-start
 * "slop" browsers themselves use before turning a press into a native drag
 * (e.g. Chromium/Firefox default to a small handful of px) — big enough to
 * absorb the jitter of an unsteady hand or a noisy optical mouse, small
 * enough that a deliberate pan is never mistaken for a click.
 */
const MOVE_THRESHOLD_MOUSE_PX = 4;

/**
 * Touch tolerance (#14625): a fingertip covers a far larger contact area
 * than a mouse cursor and drifts more for the same intended tap, so touch
 * (and pen) gestures get a taller threshold than mouse — otherwise the same
 * false-drag bug this issue fixes for mouse just reappears, at a smaller
 * radius, for touch.
 */
const MOVE_THRESHOLD_TOUCH_PX = 10;

/**
 * Whether `e` has moved far enough from `gestureStart` to count as a
 * pan/drag rather than a click/tap that merely jittered (#14625).
 */
function exceedsMoveThreshold(e: PointerEvent): boolean {
  const threshold = gestureStart.pointerType === 'touch' ? MOVE_THRESHOLD_TOUCH_PX : MOVE_THRESHOLD_MOUSE_PX;
  return Math.hypot(e.clientX - gestureStart.x, e.clientY - gestureStart.y) > threshold;
}

const panStart = reactive({ x: 0, y: 0 });
const dragNode = ref<CanvasNode | null>(null);
const dragOffset = reactive({ x: 0, y: 0 });
/**
 * #14612: per-node starting position for the drag gesture in progress —
 * populated once in `startDrag`, read (and cleared) in `endInteraction` so a
 * whole drag collapses into ONE undo entry instead of one per `pointermove`
 * tick. More than one entry only when the dragged node is part of a
 * multi-selection (a bulk drag); a lone drag has exactly one.
 */
const dragStartPositions = new Map<string, { x: number; y: number }>();
/** The latest position emitted for each node this drag — read alongside
 *  `dragStartPositions` at gesture end to build the history entry's 'after'
 *  side without re-deriving it from `props.nodes`, which a synchronous test
 *  may not have caught up with yet. */
const dragLatestPositions = new Map<string, { x: number; y: number }>();
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
 * #14612: marquee (rubber-band) multi-select.
 *
 * A left-press starting on genuinely empty canvas drags out a selection
 * rectangle (`startPan` hands off to `startMarquee` below). Mouse only: a
 * one-finger touch press is already claimed for pan (#14610), and
 * shift/middle-click are already claimed for pan too (#13996) — this only
 * ever starts in the one gesture slot nothing else uses. It therefore always
 * REPLACES the current selection rather than adding to it — there is no
 * modifier key left to spell "additive marquee" that pan has not already
 * claimed.
 * ------------------------------------------------------------------ */

const marqueeAnchor = reactive({ x: 0, y: 0 });
const marqueeCurrent = reactive({ x: 0, y: 0 });
/** True from the press until either the gesture ends or it turns into an
 *  active marquee — distinct from `marqueeActive` so a plain click (press,
 *  no movement, release) never draws a rectangle or touches the selection,
 *  the same "decide at the threshold, not on pointerdown" rule #14625
 *  already established for pan/drag. */
const marqueePending = ref(false);
const marqueeActive = ref(false);

function startMarquee(e: PointerEvent): void {
  marqueePending.value = true;
  marqueeAnchor.x = e.clientX;
  marqueeAnchor.y = e.clientY;
  marqueeCurrent.x = e.clientX;
  marqueeCurrent.y = e.clientY;
}

/** The marquee rectangle in screen space, relative to the canvas area's own
 *  box — deliberately never converted into canvas-content space: the
 *  rectangle is a lasso drawn over whatever the viewport currently shows,
 *  independent of pan/zoom, which is also why it is rendered as a sibling of
 *  `.canvas-content` rather than inside it. */
const marqueeStyle = computed(() => {
  const rect = canvasRef.value?.getBoundingClientRect();
  const originX = rect?.left ?? 0;
  const originY = rect?.top ?? 0;
  const left = Math.min(marqueeAnchor.x, marqueeCurrent.x) - originX;
  const top = Math.min(marqueeAnchor.y, marqueeCurrent.y) - originY;
  return {
    left: `${left}px`,
    top: `${top}px`,
    width: `${Math.abs(marqueeCurrent.x - marqueeAnchor.x)}px`,
    height: `${Math.abs(marqueeCurrent.y - marqueeAnchor.y)}px`,
  };
});

interface ScreenRect { left: number; top: number; right: number; bottom: number }

/** `node`'s bounding box in the SAME screen space `marqueeStyle` draws in —
 *  canvas-space position/extent transformed by the current pan/zoom, then
 *  offset by the canvas area's own on-screen position. */
function nodeScreenRect(node: CanvasNode): ScreenRect {
  const rect = canvasRef.value?.getBoundingClientRect();
  const originX = rect?.left ?? 0;
  const originY = rect?.top ?? 0;
  const { width, height } = nodeExtent(node);
  const left = originX + pan.x + node.position.x * zoom.value;
  const top = originY + pan.y + node.position.y * zoom.value;
  return { left, top, right: left + width * zoom.value, bottom: top + height * zoom.value };
}

function rectsIntersect(a: ScreenRect, b: ScreenRect): boolean {
  return a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
}

/** Recomputed on every marquee move so the selection previews live, the same
 *  way a desktop file manager's own rubber-band select does. */
function applyMarqueeSelection(): void {
  const box: ScreenRect = {
    left: Math.min(marqueeAnchor.x, marqueeCurrent.x),
    top: Math.min(marqueeAnchor.y, marqueeCurrent.y),
    right: Math.max(marqueeAnchor.x, marqueeCurrent.x),
    bottom: Math.max(marqueeAnchor.y, marqueeCurrent.y),
  };
  const next = new Set<string>();
  for (const node of props.nodes) {
    if (rectsIntersect(nodeScreenRect(node), box)) next.add(node.id);
  }
  selectedIds.value = next;
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

/* ------------------------------------------------------------------ *
 * #14612: multi-select.
 *
 * `selectedNodeId` (the prop) keeps its exact pre-#14612 meaning — "the one
 * node whose detail drawer/edit state is open" — and is never repurposed:
 * `OrgChart.vue` still reads it for `CanvasNodeSidebar`, `WorkflowBuilderView`
 * still reads it to know which node's inline fields to treat as active, and
 * neither had to change for this to land. Multi-selection is new, purely
 * local state (`selectedIds`) that coexists alongside it:
 *   - a plain click/Enter replaces both — `selectedIds` becomes a size-1 set
 *     containing the same id `node-selected` carries, so the two never
 *     disagree for the single-selection case every existing consumer already
 *     handles.
 *   - a shift-click/shift-Enter/marquee only ever touches `selectedIds`. When
 *     that leaves exactly one id, `node-selected` is re-emitted with it (a
 *     shift-click down to a single survivor still opens its drawer, matching
 *     plain-click semantics); otherwise `node-selected(null)` is emitted —
 *     every existing consumer already treats `null` as "no single node is
 *     open" (`OrgChart.closeDrawer`, `WorkflowBuilderView`'s own null branch),
 *     so a multi-selection reads as "nothing to show a detail drawer for"
 *     rather than requiring either consumer to learn a new shape.
 * ------------------------------------------------------------------ */

const selectedIds = ref<Set<string>>(new Set());

/** Every mutation to `selectedIds` goes through here — `ref<Set>` does not
 *  make Set mutation itself reactive, so every change replaces the value
 *  with a new Set rather than calling `.add`/`.delete` on the existing one. */
function mutateSelection(mutator: (ids: Set<string>) => void): void {
  const next = new Set(selectedIds.value);
  mutator(next);
  selectedIds.value = next;
}

function clearSelection(): void {
  selectedIds.value = new Set();
}

/** True when `node` is selected by either mechanism — the union `aria-pressed`
 *  announces, so a screen-reader user gets one consistent "selected" signal
 *  regardless of which one put it there. */
function isNodeSelected(node: CanvasNode): boolean {
  return props.selectedNodeId === node.id || selectedIds.value.has(node.id);
}

/** Multi-select-only membership — the visual badge/outline must stay visually
 *  distinct from `.selected`'s own solid ring (#13941: colour is never the
 *  only signal), so it is driven by this rather than by `isNodeSelected`,
 *  which would double the treatment on a node that is both. */
function isMultiOnlySelected(node: CanvasNode): boolean {
  return selectedIds.value.has(node.id) && props.selectedNodeId !== node.id;
}

/** A click/Enter/Space's selection intent — shared by the pointer and
 *  keyboard paths (#14609's own "every mouse action needs a keyboard
 *  equivalent" rule, extended to multi-select). `additive` toggles `id` into
 *  or out of `selectedIds` (shift-click / shift-Enter); otherwise the
 *  selection is replaced with just `id` (a plain click/Enter). */
function applySelectionIntent(id: string, additive: boolean): void {
  if (additive) {
    mutateSelection((ids) => {
      if (ids.has(id)) ids.delete(id);
      else ids.add(id);
    });
    const ids = selectedIds.value;
    emit('node-selected', ids.size === 1 ? [...ids][0] : null);
    return;
  }
  selectedIds.value = new Set([id]);
  emit('node-selected', id);
}

/* ------------------------------------------------------------------ *
 * #14612: undo/redo.
 *
 * Scope (stated in the UI via `undoScope`/`title`/`aria-describedby` on the
 * Undo/Redo buttons, not only here in code — a user who presses Undo and
 * sees nothing happen learns not to trust it, so the buttons are disabled
 * whenever there is nothing tracked to reverse): moving, adding, removing and
 * connecting a node on THIS canvas. Nothing else ever reaches
 * `pushHistory` — an edit inside a node's own inline fields (`node.data.*`
 * via `v-model`) is not a canvas mutation, and neither is anything that
 * reaches the server (`save-workflow`, `process-detached`, `tool-detached`):
 * the server has already committed those by the time this component could
 * react, so "undoing" them here would show a reverted card while the backend
 * disagreed with it.
 *
 * This component never owns `nodes` — it's a prop — so undo/redo works by
 * re-emitting the same intents `deleteNode`/`addStepNode`/a drag/a connect
 * already emit (or their inverse), never by mutating anything locally.
 * ------------------------------------------------------------------ */

type CanvasAtomicAction =
  | { kind: 'move'; nodeId: string; before: { x: number; y: number }; after: { x: number; y: number } }
  | { kind: 'add'; node: CanvasNode }
  | { kind: 'remove'; node: CanvasNode }
  | { kind: 'connect'; sourceId: string; targetId: string };

interface CanvasHistoryEntry {
  actions: CanvasAtomicAction[];
}

/** A session-long, unbounded stack is a memory leak nobody asked for — each
 *  entry is already one whole user gesture (a drag, an add, a bulk delete),
 *  so 100 of them is a deep history in practice. */
const MAX_HISTORY_ENTRIES = 100;

const undoStack = ref<CanvasHistoryEntry[]>([]);
const redoStack = ref<CanvasHistoryEntry[]>([]);
const canUndo = computed(() => undoStack.value.length > 0);
const canRedo = computed(() => redoStack.value.length > 0);

/** Records one user gesture as a single undo step. A gesture that produced no
 *  tracked action (e.g. `clearCanvas` on an already-empty canvas) pushes
 *  nothing, so `canUndo` never lies about there being something to reverse. */
function pushHistory(actions: CanvasAtomicAction[]): void {
  if (actions.length === 0) return;
  undoStack.value.push({ actions });
  if (undoStack.value.length > MAX_HISTORY_ENTRIES) undoStack.value.shift();
  // A fresh mutation invalidates whatever redo branch existed — the same rule
  // a browser text field's own undo stack already follows.
  redoStack.value = [];
}

/**
 * A fresh plain copy of a node held in the history stack (#14612).
 *
 * `toRaw` first, and that is the whole point. The stacks are plain `ref`s, so
 * Vue deeply proxies whatever is pushed into them — the plain object cloned at
 * record time comes back out as a reactive Proxy, and `structuredClone`
 * refuses a Proxy with `DataCloneError`. Thrown inside a click handler, that
 * exception swallowed the emit: undo appeared to do nothing, while the history
 * entry itself was correctly recorded and the button correctly enabled.
 *
 * Cloning (rather than handing back the raw object) keeps the stored snapshot
 * independent of whatever the parent does to the node it receives.
 */
function cloneStoredNode(node: CanvasNode): WorkflowNode {
  return structuredClone(toRaw(node)) as unknown as WorkflowNode;
}

function applyAtomicAction(action: CanvasAtomicAction, direction: 'undo' | 'redo'): void {
  if (action.kind === 'move') {
    emit('node-moved', action.nodeId, direction === 'undo' ? action.before : action.after);
  } else if (action.kind === 'add') {
    if (direction === 'undo') emit('node-removed', action.node.id);
    else emit('node-added', cloneStoredNode(action.node));
  } else if (action.kind === 'remove') {
    if (direction === 'undo') emit('node-added', cloneStoredNode(action.node));
    else emit('node-removed', action.node.id);
  } else {
    if (direction === 'undo') emit('nodes-disconnected', action.sourceId, action.targetId);
    else emit('nodes-connected', action.sourceId, action.targetId);
  }
}

function undo(): void {
  const entry = undoStack.value.pop();
  if (!entry) return;
  for (let i = entry.actions.length - 1; i >= 0; i -= 1) applyAtomicAction(entry.actions[i], 'undo');
  redoStack.value.push(entry);
}

function redo(): void {
  const entry = redoStack.value.pop();
  if (!entry) return;
  for (const action of entry.actions) applyAtomicAction(action, 'redo');
  undoStack.value.push(entry);
}

/** Reuses the same `_uid` `navInstructionsId`/`moveInstructionsId` are keyed
 *  off (declared above, in the #14609 keyboard-operation section) — one
 *  mount-unique id source for the whole component, not a second `useId()`
 *  call for a single new string. */
const undoScopeId = `workflow-canvas-undo-scope-${_uid}`;

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
  pushHistory([{ kind: 'add', node: structuredClone(node) }]);
}

function addConditionNode() {
  const node: WorkflowNode = {
    id: genId(), type: 'condition',
    position: { x: 100 + props.nodes.length * 40, y: 100 + props.nodes.length * 30 },
    data: { condition: '' }, connections: []
  };
  emit('node-added', node);
  emit('node-selected', node.id);
  pushHistory([{ kind: 'add', node: structuredClone(node) }]);
}

function addSwitchNode() {
  const node: WorkflowNode = {
    id: genId(), type: 'switch',
    position: { x: 100 + props.nodes.length * 40, y: 100 + props.nodes.length * 30 },
    data: { switch_on: '', cases: [''] }, connections: []
  };
  emit('node-added', node);
  emit('node-selected', node.id);
  pushHistory([{ kind: 'add', node: structuredClone(node) }]);
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
  pushHistory([{ kind: 'add', node: structuredClone(node) }]);
  showVisionDropdown.value = false;
}

function deleteNode(id: string) {
  const node = props.nodes.find((n) => n.id === id);
  emit('node-removed', id);
  if (props.selectedNodeId === id) emit('node-selected', null);
  if (selectedIds.value.has(id)) mutateSelection((ids) => ids.delete(id));
  if (node) pushHistory([{ kind: 'remove', node: structuredClone(toRaw(node)) }]);
}

/**
 * A click/tap's selection intent (#14079's pan-click suppression still
 * applies first). `event` is optional — the context menu's own "select"
 * action calls this with none, meaning "a plain selection" exactly like a
 * modifier-free click.
 */
function selectNode(id: string, event?: MouseEvent) {
  // The click/tap that closes a pan or a node drag is not a selection
  // (#14079, generalised for touch drag by #14610).
  if (movedThisGesture.value) return;
  applySelectionIntent(id, event?.shiftKey ?? false);
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
  // #14612: a Ctrl+arrow on a node that is part of a >1 multi-selection moves
  // the whole selection together — the keyboard counterpart of a bulk drag
  // (`startDrag` below), keyboard parity requiring it for the same reason
  // #14609/#14610 already established for single-node move and touch.
  const group = selectedIds.value.has(node.id) && selectedIds.value.size > 1
    ? selectedIds.value
    : new Set([node.id]);
  const moves: CanvasAtomicAction[] = [];
  for (const id of group) {
    const n = props.nodes.find((candidate) => candidate.id === id);
    if (!n) continue;
    const before = { x: n.position.x, y: n.position.y };
    const after = { x: Math.max(0, n.position.x + dx), y: Math.max(0, n.position.y + dy) };
    emit('node-moved', id, after);
    moves.push({ kind: 'move', nodeId: id, before, after });
  }
  pushHistory(moves);
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

  // #14612: Shift+Enter/Shift+Space is shift-click's keyboard equivalent —
  // toggles `node` into/out of the multi-selection instead of replacing it.
  if (e.key === 'Enter' || e.key === ' ' || e.key === 'Spacebar') {
    e.preventDefault();
    applySelectionIntent(node.id, e.shiftKey);
    return;
  }
  if (e.key === 'Escape') {
    e.preventDefault();
    clearSelection();
    emit('node-selected', null);
    return;
  }
  // #14612: the ContextMenu key (and Shift+F10, the pre-ContextMenu-key
  // convention many keyboards and screen readers still send) is the
  // keyboard's own way to open a context menu — anchored on the node's own
  // element, since a keyboard gesture carries no pointer position.
  if (e.key === 'ContextMenu' || (e.shiftKey && e.key === 'F10')) {
    e.preventDefault();
    const rect = nodeEls.get(node.id)?.getBoundingClientRect();
    openContextMenuAt(node.id, rect ? rect.left + rect.width / 2 : 0, rect ? rect.top + rect.height / 2 : 0);
    return;
  }

  const direction = resolveArrowDirection(e.key);
  if (!direction) return;
  e.preventDefault();

  if (e.ctrlKey || e.metaKey) {
    // Not gated on `readonly`, for the same reason the pointer drag is not:
    // moving a node rearranges the *view* and persists nothing. Gating it here
    // while a mouse could drag freely left keyboard users able to do strictly
    // less on the same canvas — the inequity #14609 existed to remove.
    moveNodeByKeyboard(node, direction);
    return;
  }
  focusNodeInDirection(node, direction);
}

async function clearCanvas() {
  if (props.nodes.length && (await confirm({ title: t('common.confirm'), message: t('workflow.canvas.clearConfirm') }))) {
    const removed: CanvasAtomicAction[] = props.nodes.map((n) => ({ kind: 'remove', node: structuredClone(toRaw(n)) }));
    props.nodes.forEach(n => emit('node-removed', n.id));
    emit('node-selected', null);
    clearSelection();
    pushHistory(removed);
  }
}

function autoLayout() {
  const moves: CanvasAtomicAction[] = [];
  props.nodes.forEach((node, i) => {
    const after = { x: 100 + (i % 3) * 300, y: 100 + Math.floor(i / 3) * 180 };
    if (node.position.x !== after.x || node.position.y !== after.y) {
      moves.push({ kind: 'move', nodeId: node.id, before: { x: node.position.x, y: node.position.y }, after });
    }
    emit('node-moved', node.id, after);
  });
  pushHistory(moves);
}

/** Zoom clamp shared by every way of changing it — buttons, wheel, pinch. */
const ZOOM_MIN = 0.3;
const ZOOM_MAX = 2;
function clampZoom(value: number): number { return Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, value)); }

function zoomIn() { zoom.value = clampZoom(zoom.value + 0.1); }
function zoomOut() { zoom.value = clampZoom(zoom.value - 0.1); }
function resetZoom() { zoom.value = 1; pan.x = 50; pan.y = 50; }
function handleWheel(e: WheelEvent) { zoom.value = clampZoom(zoom.value + (e.deltaY > 0 ? -0.05 : 0.05)); }

/* ------------------------------------------------------------------ *
 * GH#14611: canvas search — a large Company OS canvas has no other way to
 * find a node than panning until it scrolls into view.
 *
 * Never gated on `readonly`: searching persists nothing, the same reasoning
 * #14610's own doc comment already gives for dragging a node — and gating a
 * view gesture on it would make the *read-only* canvas, the one this issue is
 * actually about, the one canvas that cannot use it.
 * ------------------------------------------------------------------ */

const searchQuery = ref('');
const searchActiveIndex = ref(-1);
const searchInputEl = ref<HTMLInputElement | null>(null);

/** A stale highlight from a previous search must not survive into a new one. */
watch(searchQuery, () => { searchActiveIndex.value = -1; });

/**
 * A node's own name, independent of its type's generic caption.
 *
 * `nodeTitle` returns the *type* label ("Process", "Tool") for an org-process
 * or org-tool node — correct for the node's header, wrong for search and for
 * the accessible name (#14657), both of which need something identifying
 * *which* node this is: the workflow (and role) a process runs, or the tool
 * name (and the roles carrying it).
 */
function nodeDisplayName(node: CanvasNode): string {
  const label = nodeText(node, 'label');
  if (label) return label;
  if (node.type === 'org-process') {
    const workflow = nodeText(node, 'workflow_id');
    const role = nodeText(node, 'role_name');
    return role ? t('llc.orgChart.processDisplayName', { workflow, role }) : workflow;
  }
  if (node.type === 'org-tool') {
    const tool = nodeText(node, 'tool_name');
    const roles = toolRoles(node).map((role) => role.role_name).join(', ');
    return roles ? t('llc.orgChart.toolDisplayName', { tool, roles }) : tool;
  }
  return nodeTitle(node);
}

/** Every string a search for `node` should match against. */
function nodeSearchText(node: CanvasNode): string {
  const parts = [nodeDisplayName(node), nodeText(node, 'workflow_id')];
  if (node.type === 'org-tool') {
    for (const role of toolRoles(node)) parts.push(role.role_name);
  }
  return parts.filter(Boolean).join(' ');
}

/** The result list's visible (and screen-reader-read) label for `node` —
 *  the same "{kind}: {name}" text as the node's own accessible name (#14657),
 *  not a second construction of it. */
function nodeSearchLabel(node: CanvasNode): string {
  return nodeKindAndName(node);
}

const searchHasQuery = computed(() => searchQuery.value.trim().length > 0);

/** Nodes matching the current query, across every node kind (#14611
 *  acceptance: person, group/team, process, tool). Never itself filters what
 *  the canvas draws, only what the dropdown lists — a search must not be
 *  confusable with the role lens. */
const searchResults = computed<CanvasNode[]>(() => {
  const q = searchQuery.value.trim().toLowerCase();
  if (!q) return [];
  return props.nodes.filter((node) => nodeSearchText(node).toLowerCase().includes(q));
});

function searchOptionId(index: number): string {
  return `${_uid}-search-option-${index}`;
}
const searchActiveOptionId = computed<string | undefined>(() =>
  searchActiveIndex.value >= 0 && searchActiveIndex.value < searchResults.value.length
    ? searchOptionId(searchActiveIndex.value)
    : undefined,
);

/** Announced to a screen reader via the live region, and shown to a sighted
 *  reader in the dropdown (#14611: absence must read as "no match", never as
 *  an empty canvas — #14064/#13617/#14556's repeat conflation). */
const searchStatusText = computed(() => {
  if (!searchHasQuery.value) return '';
  const query = searchQuery.value.trim();
  return searchResults.value.length > 0
    ? t('workflow.canvas.searchResultsStatus', { count: searchResults.value.length, query })
    : t('workflow.canvas.searchNoResults', { query });
});

function clearSearch(): void {
  searchQuery.value = '';
  searchActiveIndex.value = -1;
}

/** Move the viewport to a search hit (#14611 acceptance: "search finds nodes
 *  and moves the viewport to a hit"). Keeps the query so Up/Down/Enter can
 *  keep stepping through the remaining hits without retyping. */
function selectSearchResult(node: CanvasNode): void {
  zoomToNode(node.id);
  searchActiveIndex.value = searchResults.value.findIndex((n) => n.id === node.id);
}

/** Keyboard operation of the results list from the search input itself —
 *  ArrowUp/ArrowDown cycle the highlight, Enter jumps to it (or to the first
 *  result when nothing is highlighted yet), Escape clears the search. */
function onSearchKeydown(e: KeyboardEvent): void {
  if (e.key === 'Escape') {
    e.preventDefault();
    clearSearch();
    return;
  }
  const results = searchResults.value;
  if (results.length === 0) return;
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    searchActiveIndex.value = (searchActiveIndex.value + 1) % results.length;
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    searchActiveIndex.value = searchActiveIndex.value <= 0 ? results.length - 1 : searchActiveIndex.value - 1;
  } else if (e.key === 'Enter') {
    e.preventDefault();
    const index = searchActiveIndex.value >= 0 ? searchActiveIndex.value : 0;
    selectSearchResult(results[index]);
  }
}

/* ------------------------------------------------------------------ *
 * GH#14611: zoom-to-node, fit-to-selection/filter, and the inbound deep
 * link's own viewport jump — all three share the same centring/fitting math.
 * ------------------------------------------------------------------ */

/** Node footprint the layout builders assume, for a node type that carries no
 *  size of its own — the same 100px row `endInteraction` below already uses
 *  for its connection-drop hit test, and `org-group`'s own `data.width`/
 *  `data.height` (`nodeStyle` above) when the node IS sized. */
const NODE_APPROX_HEIGHT = 100;

/** A zoom level comfortable for looking at one node up close — fixed, rather
 *  than a maximal fit, so repeatedly jumping between search hits or deep
 *  links only recentres the view and never also snaps the zoom level around
 *  (#14611: "zoom to a node"). */
const FOCUS_ZOOM = 1;

/** Padding, in canvas px, kept around a fitted bounding box so a fitted node
 *  or selection is never drawn flush against the canvas edge. */
const FIT_PADDING = 60;

/** The width/height a node occupies for bounding-box math (fit, minimap) —
 *  `org-group` carries its own from `data`, every other type is the fixed
 *  240x100 footprint every layout builder in `orgCanvasGraph.ts` assumes. */
function nodeExtent(node: CanvasNode): { width: number; height: number } {
  if (node.type === 'org-group') {
    const data = node.data as Record<string, unknown>;
    const width = typeof data.width === 'number' ? data.width : CANVAS_NODE_WIDTH;
    const height = typeof data.height === 'number' ? data.height : NODE_APPROX_HEIGHT;
    return { width, height };
  }
  return { width: CANVAS_NODE_WIDTH, height: NODE_APPROX_HEIGHT };
}

/** Move the viewport so `node`'s centre lands in the middle of the visible
 *  canvas area, without changing zoom. */
function centerOnNode(node: CanvasNode): void {
  const rect = canvasRef.value?.getBoundingClientRect();
  const viewWidth = rect?.width ?? 0;
  const viewHeight = rect?.height ?? 0;
  const center = nodeCenter(node);
  pan.x = viewWidth / 2 - center.x * zoom.value;
  pan.y = viewHeight / 2 - center.y * zoom.value;
}

/**
 * Zoom to a comfortable level and centre on `nodeId` (#14611 "zoom to a
 * node") — the jump a search hit or the inbound deep link performs. A no-op
 * when the id names nothing currently drawn, so a stale search result or a
 * link to a node the active filter hides cannot move the viewport to
 * nowhere; `zoom`/`pan` are left exactly as they were.
 */
function zoomToNode(nodeId: string): void {
  const node = props.nodes.find((n) => n.id === nodeId);
  if (!node) return;
  zoom.value = clampZoom(FOCUS_ZOOM);
  centerOnNode(node);
  // Same roving-tabindex move `focusNodeInDirection` (#14609) already
  // performs — a jump should leave keyboard focus (and the next Tab stop)
  // where the viewport now is, not wherever it happened to be before.
  focusedNodeId.value = nodeId;
  void nextTick(() => nodeEls.get(nodeId)?.focus());
}

/**
 * Zoom + pan so every node in `nodesToFit` is visible (#14611 "fit to the
 * current selection or filter"). Respects `clampZoom`'s bounds like every
 * other way of changing zoom on this canvas (buttons, wheel, pinch) — a
 * selection or filter spanning more of the canvas than `ZOOM_MIN` can show at
 * once is shown as small as the clamp allows, not zoomed out further. A no-op
 * on an empty list, leaving the caller's fallback (if any) as the last word.
 */
function fitToNodes(nodesToFit: CanvasNode[]): void {
  if (nodesToFit.length === 0) return;
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const node of nodesToFit) {
    const { width, height } = nodeExtent(node);
    minX = Math.min(minX, node.position.x);
    minY = Math.min(minY, node.position.y);
    maxX = Math.max(maxX, node.position.x + width);
    maxY = Math.max(maxY, node.position.y + height);
  }
  const rect = canvasRef.value?.getBoundingClientRect();
  const viewWidth = rect?.width ?? 0;
  const viewHeight = rect?.height ?? 0;
  const boxWidth = Math.max(1, maxX - minX);
  const boxHeight = Math.max(1, maxY - minY);
  zoom.value = clampZoom(
    Math.min((viewWidth - FIT_PADDING * 2) / boxWidth, (viewHeight - FIT_PADDING * 2) / boxHeight),
  );
  pan.x = viewWidth / 2 - ((minX + maxX) / 2) * zoom.value;
  pan.y = viewHeight / 2 - ((minY + maxY) / 2) * zoom.value;
}

/**
 * The reset button's sibling for "fit to selection or filter" (#14611) —
 * deliberately a *second* control, not a change to `resetZoom`: that button's
 * fixed pan(50,50)/zoom(1) stays exactly as it was.
 *
 * #14612 extended this rather than duplicating it: a multi-selection
 * (`selectedIds`) is now preferred over the single `selectedNodeId` prop when
 * one exists, so "fit to selection" means the whole bulk selection once one
 * exists. Falls back to the prop-driven single selection (unchanged from
 * #14611, and still how a fresh mount with no local multi-select behaves —
 * see the zoomFit tests), then to every node `props.nodes` currently
 * carries. That last case IS "fit to the active filter" for free — a role
 * lens or a unit tab narrows `props.nodes` itself (`OrgChart.vue`'s
 * `lensedCanvasNodes`/`visibleRoots`), so fitting to whatever is actually
 * drawn can never disagree with what the filter shows.
 */
function fitToSelectionOrView(): void {
  if (selectedIds.value.size > 0) {
    fitToNodes(props.nodes.filter((n) => selectedIds.value.has(n.id)));
    return;
  }
  const selected = props.nodes.filter((n) => n.id === props.selectedNodeId);
  fitToNodes(selected.length > 0 ? selected : props.nodes);
}

/**
 * The inbound counterpart to a search jump: `focusNodeId` names a node to
 * open the canvas already centred on (#14611's deep link). `OrgChart.vue`
 * only ever sets it once it has confirmed the id names a node already present
 * in `nodes` (`lensedCanvasNodes`, the exact array this prop receives), so a
 * single `zoomToNode` attempt per id — no retry loop watching `nodes` too —
 * is enough; watching `nodes` as well would re-centre the view every time an
 * unrelated node moves, fighting whatever the user panned to since.
 *
 * `nextTick` defers past the initial mount: an `immediate` watcher runs
 * during `setup()`, before `canvasRef` is attached to anything, so a
 * synchronous `zoomToNode` here would measure a null canvas area.
 */
watch(
  () => props.focusNodeId,
  (nodeId) => {
    if (!nodeId) return;
    void nextTick(() => zoomToNode(nodeId));
  },
  { immediate: true },
);

/* ------------------------------------------------------------------ *
 * GH#14611: minimap — an overview of a canvas larger than the viewport.
 * ------------------------------------------------------------------ */

/** Minimap panel size, in CSS px — fixed, unlike the canvas itself, since the
 *  whole point is a stable overview regardless of how far the user has
 *  zoomed or panned the main view. */
const MINIMAP_WIDTH = 160;
const MINIMAP_HEIGHT = 120;
/** Inner padding so a node at the very edge of the graph is not drawn flush
 *  against the minimap's own border. */
const MINIMAP_PADDING = 8;

interface MinimapGeometry {
  scale: number;
  minX: number;
  minY: number;
}

/** Bounding box of every node currently drawn, scaled to fit the minimap
 *  panel — `null` when there is nothing to show an overview of. */
const minimapGeometry = computed<MinimapGeometry | null>(() => {
  if (props.nodes.length === 0) return null;
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const node of props.nodes) {
    const { width, height } = nodeExtent(node);
    minX = Math.min(minX, node.position.x);
    minY = Math.min(minY, node.position.y);
    maxX = Math.max(maxX, node.position.x + width);
    maxY = Math.max(maxY, node.position.y + height);
  }
  const boxWidth = Math.max(1, maxX - minX);
  const boxHeight = Math.max(1, maxY - minY);
  const scale = Math.min(
    (MINIMAP_WIDTH - MINIMAP_PADDING * 2) / boxWidth,
    (MINIMAP_HEIGHT - MINIMAP_PADDING * 2) / boxHeight,
  );
  return { scale, minX, minY };
});

/** A canvas-space point, mapped into the minimap panel's own coordinates. */
function minimapPoint(x: number, y: number): { left: string; top: string } {
  const geo = minimapGeometry.value;
  if (!geo) return { left: '0px', top: '0px' };
  return {
    left: `${MINIMAP_PADDING + (x - geo.minX) * geo.scale}px`,
    top: `${MINIMAP_PADDING + (y - geo.minY) * geo.scale}px`,
  };
}

function minimapNodeStyle(node: CanvasNode): Record<string, string> {
  const { width, height } = nodeExtent(node);
  return minimapPoint(node.position.x + width / 2, node.position.y + height / 2);
}

/** The "you are here" rectangle: the visible canvas area's current bounds, in
 *  canvas-content space, mapped the same way the node dots are. `null` when
 *  there is no overview to draw it on. */
const minimapViewportStyle = computed<Record<string, string> | null>(() => {
  const geo = minimapGeometry.value;
  if (!geo) return null;
  const rect = canvasRef.value?.getBoundingClientRect();
  const viewWidth = rect?.width ?? 0;
  const viewHeight = rect?.height ?? 0;
  const point = minimapPoint(-pan.x / zoom.value, -pan.y / zoom.value);
  return {
    left: point.left,
    top: point.top,
    width: `${Math.max(0, (viewWidth / zoom.value) * geo.scale)}px`,
    height: `${Math.max(0, (viewHeight / zoom.value) * geo.scale)}px`,
  };
});

/**
 * A click/tap on the minimap pans the main view to that point (#14611) — a
 * view gesture like the pan/drag/zoom above it, so it is never gated on
 * `readonly` either. Zoom is left untouched: the minimap only ever answers
 * "where", never "how close".
 */
function onMinimapPointerDown(e: PointerEvent): void {
  const geo = minimapGeometry.value;
  const panel = e.currentTarget as HTMLElement | null;
  if (!geo || !panel) return;
  const panelRect = panel.getBoundingClientRect();
  const canvasX = geo.minX + (e.clientX - panelRect.left - MINIMAP_PADDING) / geo.scale;
  const canvasY = geo.minY + (e.clientY - panelRect.top - MINIMAP_PADDING) / geo.scale;
  const rect = canvasRef.value?.getBoundingClientRect();
  const viewWidth = rect?.width ?? 0;
  const viewHeight = rect?.height ?? 0;
  pan.x = viewWidth / 2 - canvasX * zoom.value;
  pan.y = viewHeight / 2 - canvasY * zoom.value;
}

/** Rescale from the pinch's starting distance/zoom — proportional, like `handleWheel`
 *  and the zoom buttons, none of which anchor around a point either (#14610). */
function applyPinchZoom(): void {
  const distance = pinchDistance();
  if (pinchStartDistance.value <= 0 || distance <= 0) return;
  zoom.value = clampZoom(pinchStartZoom.value * (distance / pinchStartDistance.value));
}

function startPan(e: PointerEvent) {
  movedThisGesture.value = false;
  gestureStart.x = e.clientX;
  gestureStart.y = e.clientY;
  gestureStart.pointerType = e.pointerType;
  activePointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
  capturePointer(e);
  if (activePointers.size >= 2) { beginPinch(); return; }

  // #14610: touch carries no shift key and no middle button, so a one-finger
  // press starting on empty canvas (or an org container, handed on below) is
  // always a pan — mirrors the mouse's shift/middle-click modifier.
  const isTouchPan = e.pointerType === 'touch';
  if (isTouchPan || e.button === 1 || e.shiftKey) {
    isPanning.value = true; panStart.x = e.clientX - pan.x; panStart.y = e.clientY - pan.y;
    return;
  }
  // #14612: a plain left-press reaching here started on genuinely empty
  // canvas — a node's own `onNodePointerDown` always stops propagation for a
  // plain press (only shift/middle-click bubble here instead, both handled
  // above) — so this is the one gesture slot marquee-select can claim
  // without taking anything away from pan, drag or touch.
  if (e.button === 0) startMarquee(e);
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
  gestureStart.x = e.clientX;
  gestureStart.y = e.clientY;
  gestureStart.pointerType = e.pointerType;
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
  e.stopPropagation();
  // Dragging a node is NOT gated on `readonly`, and that is deliberate.
  //
  // `readonly` means "cannot author the workflow" — no add, delete, connect or
  // save. Rearranging where a node sits is a *view* gesture, not a change to
  // anything stored: `OrgChart.onCanvasNodeMoved` writes the new position into
  // its in-memory node list and nothing is persisted.
  //
  // It is also a feature the org chart deliberately supports. `OrgChart.vue`
  // holds `canvasNodes` as a ref rather than a computed specifically so that
  // "node drags stay put", and re-layout is avoided so "a drag survives
  // pause/resume". Gating this on `readonly` would delete that, and would make
  // `onCanvasNodeMoved` dead code on the only canvas that mounts read-only.
  //
  // Touch therefore behaves exactly as the mouse does: a press that starts on
  // a node drags it, and a pan starts on empty canvas or a container.
  startDrag(node, e);
}

function startDrag(node: CanvasNode, e: PointerEvent) {
  dragNode.value = node;
  dragOffset.x = e.clientX - node.position.x * zoom.value - pan.x;
  dragOffset.y = e.clientY - node.position.y * zoom.value - pan.y;
  // #14612: dragging a node that is part of a >1 multi-selection moves the
  // whole selection together — every other selected node's own position is
  // derived from the SAME pointer delta as the node the gesture grabbed (see
  // `onPointerMove`'s `dragNode` branch). Captured once, here, rather than
  // read fresh on every `pointermove`, so the 'before' side of the eventual
  // undo entry is the position each node had when the gesture STARTED, not
  // wherever it happened to be on the last tick.
  dragStartPositions.clear();
  dragLatestPositions.clear();
  const group = selectedIds.value.has(node.id) && selectedIds.value.size > 1
    ? selectedIds.value
    : new Set([node.id]);
  for (const id of group) {
    const n = props.nodes.find((candidate) => candidate.id === id);
    if (n) dragStartPositions.set(id, { x: n.position.x, y: n.position.y });
  }
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
    // Set once the gesture has moved past the threshold from its start
    // point, not on the first pointermove (#14625) — a shift-click/tap that
    // never leaves that small radius is still a selection, and suppressing
    // it on any single move would break selecting with shift held (mouse)
    // or a plain tap (touch).
    if (exceedsMoveThreshold(e)) movedThisGesture.value = true;
  }
  else if (dragNode.value) {
    const x = (e.clientX - dragOffset.x - pan.x) / zoom.value;
    const y = (e.clientY - dragOffset.y - pan.y) / zoom.value;
    const primary = { x: Math.max(0, x), y: Math.max(0, y) };
    // #14612: every other node in `dragStartPositions` (the rest of a
    // multi-selection, if any — a lone drag has exactly one entry, itself,
    // making this loop identical to the pre-#14612 single-emit behaviour)
    // moves by the SAME delta the primary dragged node just moved, from ITS
    // OWN start position, each still clamped to stay on-canvas individually.
    const start = dragStartPositions.get(dragNode.value.id);
    const dx = start ? primary.x - start.x : 0;
    const dy = start ? primary.y - start.y : 0;
    for (const [id, startPos] of dragStartPositions) {
      const pos = id === dragNode.value.id
        ? primary
        : { x: Math.max(0, startPos.x + dx), y: Math.max(0, startPos.y + dy) };
      emit('node-moved', id, pos);
      dragLatestPositions.set(id, pos);
    }
    // #14610/#14625: a drag that actually moved the node past the threshold
    // must not also select it when the gesture ends — the drag counterpart
    // of the pan case above.
    if (exceedsMoveThreshold(e)) movedThisGesture.value = true;
  }
  else if (marqueePending.value) {
    marqueeCurrent.x = e.clientX;
    marqueeCurrent.y = e.clientY;
    if (!marqueeActive.value && exceedsMoveThreshold(e)) marqueeActive.value = true;
    if (marqueeActive.value) {
      applyMarqueeSelection();
      // #14612: mirrors the pan/drag suppression above (#14079/#14610/#14625)
      // — `capturePointer` retargets `pointerup` to `.canvas-area`, but not
      // the browser's synthesized `click`, which still hit-tests normally
      // and can land on whichever node the marquee happened to end over.
      // Without this, that click reached `selectNode` with `movedThisGesture`
      // still false and collapsed the whole marquee selection down to just
      // that one node.
      movedThisGesture.value = true;
    }
  }
}

function endInteraction(e: PointerEvent) {
  if (drawingLine.value) {
    const rect = canvasRef.value?.getBoundingClientRect();
    if (rect) {
      const x = (e.clientX - rect.left - pan.x) / zoom.value;
      const y = (e.clientY - rect.top - pan.y) / zoom.value;
      const target = props.nodes.find(n => x >= n.position.x && x <= n.position.x + 240 && y >= n.position.y && y <= n.position.y + 100);
      if (target && target.id !== lineStart.nodeId) {
        emit('nodes-connected', lineStart.nodeId, target.id);
        pushHistory([{ kind: 'connect', sourceId: lineStart.nodeId, targetId: target.id }]);
      }
    }
  }
  // #14612: one undo step per drag GESTURE, not per `pointermove` tick —
  // `dragStartPositions`/`dragLatestPositions` were populated once at
  // `startDrag` and kept in step on every move; only a node that actually
  // ended up somewhere different becomes a history entry.
  if (dragNode.value && movedThisGesture.value && dragStartPositions.size > 0) {
    const moves: CanvasAtomicAction[] = [];
    for (const [id, before] of dragStartPositions) {
      const after = dragLatestPositions.get(id) ?? before;
      if (after.x !== before.x || after.y !== before.y) moves.push({ kind: 'move', nodeId: id, before, after });
    }
    pushHistory(moves);
  }
  dragStartPositions.clear();
  dragLatestPositions.clear();
  // #14612: the marquee's selection was already applied live in
  // `onPointerMove` as the rectangle grew — this just ends the gesture and
  // (unlike a plain click on empty canvas, which stays a no-op) tells the
  // consumer about the selection it just built, mirroring what a click or
  // shift-click already does when it leaves exactly one id selected.
  if (marqueeActive.value) {
    const ids = selectedIds.value;
    emit('node-selected', ids.size === 1 ? [...ids][0] : null);
  }
  marqueePending.value = false;
  marqueeActive.value = false;
  // #14610: lifting one finger of a pinch leaves the other still down; it
  // does not resume as a one-finger pan — the user has to lift fully and
  // start a fresh gesture, same as releasing mid-drag does for a mouse.
  activePointers.delete(e.pointerId);
  isPanning.value = false; dragNode.value = null; drawingLine.value = false;
}

function saveWorkflow() { showSaveDialog.value = true; }
function confirmSave() { emit('save-workflow', saveName.value, saveDesc.value); showSaveDialog.value = false; saveName.value = ''; saveDesc.value = ''; }

/* ------------------------------------------------------------------ *
 * #14612: context menu.
 *
 * Every action below re-invokes a handler that already exists elsewhere on
 * this card — `selectNode`, `zoomToNode`, `fitToNodes`, the `process-detached`
 * /`tool-detached` emits the card's own detach buttons already use, and
 * `deleteNode` — rather than a second implementation of any of them. That is
 * what keeps the menu from ever drifting from the sidebar/card's own action
 * set: there is only ever one function that performs each action, and the
 * menu is one more caller of it.
 * ------------------------------------------------------------------ */

interface CanvasContextMenuAction {
  id: string;
  label: string;
  run: () => void;
}

const contextMenu = reactive<{ open: boolean; x: number; y: number; nodeId: string | null }>({
  open: false,
  x: 0,
  y: 0,
  nodeId: null,
});
const contextMenuEl = ref<HTMLElement | null>(null);

/** Matches the menu's own `min-width`/`max-height` below — used only to keep
 *  the menu on-screen, so an approximation is enough; a real measurement
 *  would need a render pass between "open" and "position" for no visible
 *  benefit. */
const CONTEXT_MENU_WIDTH = 220;
const CONTEXT_MENU_MAX_HEIGHT = 280;

/**
 * Opens the menu anchored at `(clientX, clientY)`, clamped to stay fully
 * on-screen. Deliberately direction-agnostic (#14612 RTL requirement): the
 * clamp is against `window.innerWidth`/`innerHeight`, physical viewport
 * bounds that mean the same thing regardless of document direction, rather
 * than any LTR/RTL-specific offset math — a menu opened near the trailing
 * edge in either direction simply flips to stay inside the same physical
 * bounds either way.
 */
function openContextMenuAt(nodeId: string, clientX: number, clientY: number): void {
  const maxX = Math.max(8, window.innerWidth - CONTEXT_MENU_WIDTH - 8);
  const maxY = Math.max(8, window.innerHeight - CONTEXT_MENU_MAX_HEIGHT - 8);
  contextMenu.x = Math.max(8, Math.min(clientX, maxX));
  contextMenu.y = Math.max(8, Math.min(clientY, maxY));
  contextMenu.nodeId = nodeId;
  contextMenu.open = true;
  void nextTick(() => contextMenuEl.value?.focus());
}

function closeContextMenu(): void {
  contextMenu.open = false;
  contextMenu.nodeId = null;
}

/** Escape's own close path — also returns keyboard focus to the node the
 *  menu was opened on, so a keyboard user is not dropped onto the document
 *  body. Not used by the backdrop/action-selected paths: those already have
 *  an obvious next focus target (whatever the user clicked, or the action's
 *  own effect), and forcing focus back to the node there would fight it. */
function closeContextMenuAndRestoreFocus(): void {
  const nodeId = contextMenu.nodeId;
  closeContextMenu();
  if (nodeId) void nextTick(() => nodeEls.get(nodeId)?.focus());
}

const contextMenuStyle = computed(() => ({ left: `${contextMenu.x}px`, top: `${contextMenu.y}px` }));

/**
 * Right-click (`@contextmenu`) or the node's own "…" button
 * (`.node-menu-btn`, for touch/keyboard-tab users who cannot right-click) —
 * both reach this. A node not already part of the multi-selection has the
 * selection replaced with just itself first (the same convention a file
 * manager or spreadsheet uses), so the menu always acts on a selection that
 * includes the node it was opened on.
 */
function onNodeContextMenu(node: CanvasNode, e: MouseEvent): void {
  if (!selectedIds.value.has(node.id)) {
    selectedIds.value = new Set([node.id]);
    emit('node-selected', node.id);
  }
  openContextMenuAt(node.id, e.clientX, e.clientY);
}

/**
 * The action set for whichever node the menu is currently open on — never a
 * hand-maintained list that could drift from what the card/sidebar actually
 * offer (#14612 acceptance). `select`/`open-workflow` are omitted for
 * `org-group`/`org-tool`: selecting either is already a dead click today
 * (`OrgChart.onCanvasNodeSelected` finds no matching tree node for either
 * id), and a menu item that does nothing is worse than an absent one.
 */
const contextMenuActions = computed<CanvasContextMenuAction[]>(() => {
  const nodeId = contextMenu.nodeId;
  if (!nodeId) return [];
  const node = props.nodes.find((n) => n.id === nodeId);
  if (!node) return [];
  const bulk = selectedIds.value.has(nodeId) && selectedIds.value.size > 1;
  const actions: CanvasContextMenuAction[] = [];

  if (node.type === 'org-process') {
    actions.push({
      id: 'open-workflow',
      label: t('workflow.canvas.contextMenuOpenWorkflow'),
      run: () => selectNode(node.id),
    });
  } else if (node.type !== 'org-group' && node.type !== 'org-tool') {
    actions.push({ id: 'select', label: t('common.select'), run: () => selectNode(node.id) });
  }

  actions.push({
    id: 'zoom',
    label: t('workflow.canvas.contextMenuZoomToNode'),
    run: () => zoomToNode(node.id),
  });

  if (bulk) {
    actions.push({
      id: 'fit-selection',
      label: t('workflow.canvas.contextMenuFitSelection'),
      run: () => fitToNodes(props.nodes.filter((n) => selectedIds.value.has(n.id))),
    });
  }

  if (node.type === 'org-process') {
    actions.push({
      id: 'detach-process',
      label: processDetachLabel(node),
      run: () => emit('process-detached', nodeText(node, 'role_id'), nodeText(node, 'workflow_id')),
    });
  }
  if (node.type === 'org-tool') {
    for (const role of toolRoles(node)) {
      actions.push({
        id: `detach-tool-${role.role_id}`,
        label: toolDetachLabel(node, role),
        run: () => emit('tool-detached', role.role_id, nodeText(node, 'tool_name')),
      });
    }
  }

  if (!props.readonly && node.type !== 'org-group') {
    actions.push({
      id: 'delete',
      label: bulk
        ? t('workflow.canvas.contextMenuDeleteSelection', { count: selectedIds.value.size })
        : t('common.delete'),
      run: () => {
        for (const id of bulk ? [...selectedIds.value] : [node.id]) deleteNode(id);
      },
    });
  }

  return actions;
});

function runContextMenuAction(action: CanvasContextMenuAction): void {
  action.run();
  closeContextMenu();
}
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
/* #14596: a team is not a reporting unit. The dashed info-coloured box above
   stands for a reporting line; a team roster is drawn solid in the warning
   accent so the two are told apart at a glance rather than only by reading
   their captions. Colour is not the only signal — the border STYLE differs
   too (solid vs dashed), so the distinction survives for a reader who cannot
   separate the hues, which is the rule #13941 established on this canvas. */
.workflow-node.org-group[data-group-kind='team'] { background: var(--color-warning-bg); border-style: solid; }
.workflow-node.org-group[data-group-kind='team'] .node-header { border-bottom: 1px solid var(--color-warning); }
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

/* #14611: canvas search — a text field plus a listbox dropdown, following
   the same combobox pattern the rest of the toolbar's dropdown already uses
   (`.dropdown-container`/`.dropdown-menu` below), styled to match. */
.canvas-search { position: relative; }
.canvas-search-field { display: flex; align-items: center; gap: var(--spacing-1-5); padding: var(--spacing-1-5) var(--spacing-2); background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: var(--radius-md); }
.canvas-search-field:focus-within { border-color: var(--color-primary); }
.canvas-search-icon { color: var(--text-tertiary); flex: none; }
.canvas-search-input { border: none; background: transparent; color: var(--text-primary); font-size: var(--text-sm); width: 160px; }
.canvas-search-input:focus { outline: none; }
.canvas-search-clear { display: flex; align-items: center; padding: var(--spacing-0); background: transparent; border: none; color: var(--text-tertiary); cursor: pointer; }
.canvas-search-clear:hover { color: var(--text-primary); }
.canvas-search-clear:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 2px; }
.canvas-search-results { position: absolute; top: 100%; inset-inline-start: 0; z-index: 10; margin-top: var(--spacing-1); width: 260px; max-height: 260px; overflow-y: auto; list-style: none; padding: var(--spacing-1) var(--spacing-0); background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: var(--radius-md); box-shadow: 0 4px 12px rgba(0,0,0,0.3); }
.canvas-search-result { padding: var(--spacing-2) var(--spacing-3); font-size: var(--text-sm); color: var(--text-primary); cursor: pointer; }
.canvas-search-result:hover, .canvas-search-result.active { background: var(--bg-tertiary); }
.canvas-search-empty { padding: var(--spacing-2) var(--spacing-3); font-size: var(--text-sm); color: var(--text-tertiary); font-style: italic; }

/* #14611: overview panel — fixed size regardless of canvas zoom/pan, opposite
   corner from `.canvas-legend` so the two never overlap. */
.canvas-minimap { position: absolute; top: var(--spacing-3); inset-inline-end: var(--spacing-3); width: 160px; height: 120px; background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: var(--radius-md); box-shadow: var(--shadow-sm); overflow: hidden; cursor: pointer; touch-action: none; }
.canvas-minimap-node { position: absolute; width: 4px; height: 4px; border-radius: 50%; background: var(--text-muted); transform: translate(-50%, -50%); pointer-events: none; }
.canvas-minimap-viewport { position: absolute; border: 1px solid var(--color-primary); background: var(--color-primary-bg); pointer-events: none; }

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
/* #14597: a tool node must not read as "another process node" — colour is
   never the only signal (#13941), so the header background AND the border
   style both differ from every other org node type (solid info for
   org-person, dashed/solid info-warning for org-group, unstyled default for
   org-process). The dotted inline-start border pairs with the distinct
   'wrench' icon and 'Tool' caption set in nodeIcons/nodeLabels above. */
.workflow-node.org-tool {
  border-inline-start-width: 6px;
  border-inline-start-style: dotted;
  border-inline-start-color: var(--color-secondary);
}
.workflow-node.org-tool .node-header {
  background: var(--color-secondary);
}
.tool-roles {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
  margin: var(--spacing-0);
  padding: var(--spacing-0);
  list-style: none;
}
.tool-role-chip {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-size: var(--text-xs);
  color: var(--text-secondary);
}
.tool-role-name {
  flex: 1;
  font-family: var(--font-family-mono, monospace);
}
.tool-detach-btn {
  padding: var(--spacing-1);
  background: transparent;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: var(--radius-default);
  line-height: 1;
}
.tool-detach-btn:hover {
  color: var(--color-error);
  background: var(--bg-hover);
}
.tool-detach-btn:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

/* #14612: multi-select status chip — mirrors `.rule-mode`'s existing
   toolbar-left status-readout styling. */
.canvas-selection-status { display: flex; align-items: center; gap: var(--spacing-2); padding: var(--spacing-1) var(--spacing-2); background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: var(--radius-md); font-size: var(--text-xs); color: var(--text-secondary); }
.canvas-selection-clear { padding: var(--spacing-0-5) var(--spacing-2); background: transparent; border: 1px solid var(--border-default); border-radius: var(--radius-default); color: var(--text-secondary); cursor: pointer; font-size: var(--text-xs); }
.canvas-selection-clear:hover { background: var(--bg-hover); color: var(--text-primary); }
.canvas-selection-clear:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 2px; }

/* #14612: a multi-selected node must differ by more than hue (#13941) — a
   dashed double outline (shape) plus a corner badge (icon), never colour
   alone, and deliberately distinct from `.selected`'s own solid ring so the
   two states never look identical on the same node. */
.workflow-node.multi-selected { outline: 2px dashed var(--color-info); outline-offset: 2px; }
.multi-select-badge { display: inline-flex; color: var(--color-info); }

/* #14612: the node's own context-menu trigger — mirrors `.delete-btn`'s
   existing header-icon-button styling. */
.node-menu-btn { padding: var(--spacing-1); background: transparent; border: none; color: inherit; cursor: pointer; opacity: 0.7; border-radius: var(--radius-default); }
.node-menu-btn:hover { opacity: 1; background: rgba(255,255,255,0.2); }
.node-menu-btn:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 2px; }

/* #14612: marquee — screen-space, a sibling of `.canvas-content` so it never
   inherits the pan/zoom transform (see the template comment above it). */
.canvas-marquee { position: absolute; border: 1px dashed var(--color-primary); background: var(--color-primary-bg); pointer-events: none; z-index: 5; }

/* #14612: context menu — fixed-position, clamped to the viewport in script.
   The clamp works identically in LTR and RTL (it is measured against
   `window.innerWidth`, a physical bound with no notion of direction), so no
   direction-specific CSS is needed here for the "opens on the correct side"
   requirement. */
.context-menu-backdrop { position: fixed; inset: 0; z-index: var(--z-modal-backdrop); background: transparent; }
.canvas-context-menu { position: fixed; z-index: var(--z-modal); min-width: 200px; max-width: 280px; margin: var(--spacing-0); padding: var(--spacing-1) var(--spacing-0); list-style: none; background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: var(--radius-md); box-shadow: 0 4px 12px rgba(0,0,0,0.3); }
.canvas-context-menu:focus-visible { outline: none; }
.canvas-context-menu-item { display: block; width: 100%; padding: var(--spacing-2) var(--spacing-3); background: none; border: none; color: var(--text-primary); text-align: start; cursor: pointer; font-size: var(--text-sm); }
.canvas-context-menu-item:hover { background: var(--bg-tertiary); }
.canvas-context-menu-item:focus-visible { outline: 2px solid var(--color-primary); outline-offset: -2px; }
</style>
