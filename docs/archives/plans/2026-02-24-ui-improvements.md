# UI Improvements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Four focused UI improvements across two frontends: role assignment in SLM migration tab, fleet operations filter/expand/warn, preferences tabs in main frontend, and GUI Automation section in workflow builder.

**Architecture:** All changes are purely frontend — no new backend endpoints. Each task modifies one file. SLM frontend (`autobot-slm-frontend`) and main frontend (`autobot-frontend`) are separate Vue 3 + TypeScript apps.

**Tech Stack:** Vue 3 Composition API, TypeScript, Tailwind CSS (SLM), CSS design tokens (main frontend).

---

## Pre-flight

```bash
git branch --show-current   # must be Dev_new_gui
git status                  # must be clean
```

---

## Task 1: GitHub Issue

**Step 1: Create issue**

```bash
gh issue create \
  --title "feat(ui): orchestration role assignment, fleet filter/expand/warn, preferences tabs, GUI automation section" \
  --body "## Changes

### SLM Frontend (autobot-slm-frontend)
- /orchestration/migration: add direct role assignment card above migration wizard
- /orchestration/fleet: category filter chips, per-node expandable rows, restart confirmation with node list

### Main Frontend (autobot-frontend)
- /preferences: convert vertical sections to tabbed layout
- /automation: add GUI Automation section to workflow builder sidebar

## Acceptance Criteria
- [ ] Migration tab shows role assignment card; assign/remove calls work without running migration
- [ ] Fleet tab has AutoBot/System/All filter chips that filter the services table
- [ ] Fleet service rows expand to show per-node status and individual action buttons
- [ ] Fleet restart/stop/start shows confirmation dialog listing affected nodes by hostname
- [ ] Preferences page has Appearance and Voice tabs (no more single scroll)
- [ ] Automation sidebar has GUI Automation item that renders VisionAutomationPage" \
  --label enhancement
```

Note the issue number — use it in all commit messages as `(#NNN)`.

---

## Task 2: SLM — Migration Tab: Role Assignment Card

**File:** `autobot-slm-frontend/src/views/OrchestrationView.vue`

**Context:** The migration tab (Tab 4, `v-if="activeTab === 'migration'"`) currently shows role selection → migration wizard. We add a "Quick Role Assignment" card at the top.

### Step 1: Add state and helpers in the script section

Find the `// Tab 4: Migration State` block (~line 222). Add the following directly above it:

```typescript
// =============================================================================
// Tab 4: Role Assignment State (quick assign without full migration)
// =============================================================================

const assignNodeId = ref('')

function isRoleAssigned(nodeId: string, roleName: string): boolean {
  const cached = nodeRolesCache[nodeId]
  if (!cached) return false
  return cached.roles.some(
    (r) => r.role_name === roleName && r.status !== 'not_installed',
  )
}

async function assignRoleToNode(nodeId: string, roleName: string): Promise<void> {
  await roles.assignRole(nodeId, roleName)
  delete nodeRolesCache[nodeId]
  await loadRolesForNode(nodeId)
}

async function removeRoleFromNode(nodeId: string, roleName: string): Promise<void> {
  await roles.removeRole(nodeId, roleName)
  delete nodeRolesCache[nodeId]
  await loadRolesForNode(nodeId)
}
```

Also add a watcher for `assignNodeId` (place it near the other watches, after the `watch(() => route.params.tab, ...)` block):

```typescript
watch(assignNodeId, (nodeId) => {
  if (nodeId && !nodeRolesCache[nodeId]) {
    loadRolesForNode(nodeId)
  }
})
```

### Step 2: Add the role assignment card to the migration tab template

In the template, find the comment `<!-- Tab 4: Migration (role-based) -->` and the opening `<div v-if="activeTab === 'migration'" class="space-y-4">`.

The FIRST child of that div is `<!-- Step 1: Select a role -->`. Insert the following NEW card **before** that comment:

```html
<!-- Role Assignment Card -->
<div class="card p-4">
  <h3 class="font-medium text-gray-900 mb-1">Quick Role Assignment</h3>
  <p class="text-sm text-gray-600 mb-4">
    Assign or remove roles from nodes without running a full code sync.
  </p>

  <!-- Node selector -->
  <div class="mb-4">
    <label class="block text-sm font-medium text-gray-700 mb-1">Node</label>
    <select v-model="assignNodeId" class="w-full px-3 py-2 border rounded-lg text-sm">
      <option value="">Select a node...</option>
      <option
        v-for="node in orchestration.fleetStore.nodeList"
        :key="node.node_id"
        :value="node.node_id"
      >
        {{ node.hostname }} ({{ node.ip_address }})
      </option>
    </select>
  </div>

  <!-- Role matrix -->
  <div v-if="assignNodeId">
    <div v-if="loadingRolesForNode[assignNodeId]" class="text-sm text-gray-400 italic py-2">
      Loading roles...
    </div>
    <div v-else-if="roles.roles.length === 0" class="text-sm text-gray-500 py-2">
      No roles defined. Create roles in the Roles &amp; Deployment tab first.
    </div>
    <div v-else class="grid grid-cols-2 gap-2">
      <div
        v-for="role in roles.roles"
        :key="role.name"
        class="flex items-center justify-between border rounded-lg p-2.5 hover:bg-gray-50"
      >
        <div class="min-w-0 mr-2">
          <p class="text-sm font-medium text-gray-900 truncate">
            {{ role.display_name || role.name }}
          </p>
          <p class="text-xs text-gray-400 truncate">{{ role.systemd_service || role.name }}</p>
        </div>
        <div class="flex-shrink-0">
          <button
            v-if="!isRoleAssigned(assignNodeId, role.name)"
            @click="assignRoleToNode(assignNodeId, role.name)"
            class="px-2 py-1 text-xs bg-blue-100 text-blue-700 rounded hover:bg-blue-200 whitespace-nowrap"
          >
            Assign
          </button>
          <button
            v-else
            @click="removeRoleFromNode(assignNodeId, role.name)"
            class="px-2 py-1 text-xs bg-red-100 text-red-700 rounded hover:bg-red-200 whitespace-nowrap"
          >
            Remove
          </button>
        </div>
      </div>
    </div>
  </div>
  <p v-else class="text-sm text-gray-400 italic">Select a node above to manage its roles.</p>
</div>
```

### Step 3: Verify it compiles

```bash
cd /home/kali/Desktop/AutoBot/autobot-slm-frontend
npm run type-check 2>&1 | tail -20
```

Expected: no errors.

### Step 4: Commit

```bash
cd /home/kali/Desktop/AutoBot
git add autobot-slm-frontend/src/views/OrchestrationView.vue
git commit -m "feat(slm/orchestration): add quick role assignment card to migration tab (#NNN)"
```

---

## Task 3: SLM — Fleet Tab: Category Filter UI

**File:** `autobot-slm-frontend/src/views/OrchestrationView.vue`

**Context:** `fleetCategoryFilter` and `fleetSearchQuery` refs already exist in the script but have no UI in the fleet tab template. The per-node tab already has working filter chips — we replicate the same pattern here.

### Step 1: Add fleetCategoryCounts computed

Find the `categoryCounts` computed (~line 159). Add this directly after it:

```typescript
const fleetCategoryCounts = computed(() => {
  const counts = { autobot: 0, system: 0, all: 0 }
  if (Array.isArray(orchestration.fleetServices)) {
    for (const svc of orchestration.fleetServices) {
      counts[svc.category as 'autobot' | 'system']++
      counts.all++
    }
  }
  return counts
})
```

### Step 2: Add filter bar to fleet tab template

In the template, find the comment `<!-- Tab 2: Fleet Operations -->` and the opening `<div v-if="activeTab === 'fleet'" class="space-y-4">`.

The first child is the Fleet Role Health card (`v-if="roles.fleetHealth"`). After that health card and before `<!-- Fleet Actions -->`, insert:

```html
<!-- Fleet Filter Bar -->
<div class="card p-4">
  <div class="flex flex-wrap items-center gap-4">
    <div class="flex-1 min-w-52">
      <input
        v-model="fleetSearchQuery"
        type="text"
        placeholder="Search services..."
        class="w-full px-3 py-2 border rounded-lg text-sm"
      />
    </div>
    <div class="flex items-center gap-2">
      <button
        @click="fleetCategoryFilter = 'autobot'"
        :class="[
          'px-3 py-1.5 text-sm font-medium rounded-lg',
          fleetCategoryFilter === 'autobot'
            ? 'bg-primary-100 text-primary-700'
            : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
        ]"
      >
        AutoBot ({{ fleetCategoryCounts.autobot }})
      </button>
      <button
        @click="fleetCategoryFilter = 'system'"
        :class="[
          'px-3 py-1.5 text-sm font-medium rounded-lg',
          fleetCategoryFilter === 'system'
            ? 'bg-primary-100 text-primary-700'
            : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
        ]"
      >
        System ({{ fleetCategoryCounts.system }})
      </button>
      <button
        @click="fleetCategoryFilter = 'all'"
        :class="[
          'px-3 py-1.5 text-sm font-medium rounded-lg',
          fleetCategoryFilter === 'all'
            ? 'bg-primary-100 text-primary-700'
            : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
        ]"
      >
        All ({{ fleetCategoryCounts.all }})
      </button>
    </div>
  </div>
</div>
```

### Step 3: Type-check and commit

```bash
cd /home/kali/Desktop/AutoBot/autobot-slm-frontend
npm run type-check 2>&1 | tail -20
```

```bash
cd /home/kali/Desktop/AutoBot
git add autobot-slm-frontend/src/views/OrchestrationView.vue
git commit -m "feat(slm/orchestration): add category filter chips to fleet operations tab (#NNN)"
```

---

## Task 4: SLM — Fleet Tab: Per-Node Expandable Rows

**File:** `autobot-slm-frontend/src/views/OrchestrationView.vue`

**Context:** The fleet services table shows one row per service with aggregated counts. We add expand/collapse to show per-node status and individual action buttons.

### Step 1: Add expand state and helper

Find `// Tab 2: Fleet Operations State` section. Add after `fleetCategoryFilter`:

```typescript
const expandedFleetServices = ref<Set<string>>(new Set())

function toggleFleetService(serviceName: string): void {
  if (expandedFleetServices.value.has(serviceName)) {
    expandedFleetServices.value.delete(serviceName)
  } else {
    expandedFleetServices.value.add(serviceName)
  }
}

function getNodeHostname(nodeId: string): string {
  const node = orchestration.fleetStore.nodeList.find((n) => n.node_id === nodeId)
  return node?.hostname ?? nodeId
}
```

### Step 2: Replace the service rows in the fleet table

Find the `<tbody>` inside the Fleet Services table (inside `<!-- Fleet Services Table -->`). Currently it has one `<tr v-for="service in filteredFleetServices"`. Replace the entire `<tbody>` content with:

```html
<tbody>
  <template v-for="service in filteredFleetServices" :key="service.service_name">
    <!-- Summary row -->
    <tr class="border-t border-gray-50 hover:bg-gray-50">
      <td class="px-4 py-2">
        <div class="flex items-center gap-2">
          <button
            @click="toggleFleetService(service.service_name)"
            class="text-gray-400 hover:text-gray-600 flex-shrink-0"
            :title="expandedFleetServices.has(service.service_name) ? 'Collapse' : 'Expand nodes'"
          >
            <svg
              class="w-4 h-4 transition-transform"
              :class="expandedFleetServices.has(service.service_name) ? 'rotate-90' : ''"
              fill="none" stroke="currentColor" viewBox="0 0 24 24"
            >
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
            </svg>
          </button>
          <span class="font-medium text-gray-900">{{ service.service_name }}</span>
          <span class="text-xs text-gray-500">({{ service.total_nodes }} nodes)</span>
        </div>
      </td>
      <td class="px-4 py-2">
        <span
          :class="[
            'px-1.5 py-0.5 text-xs font-medium rounded',
            service.category === 'autobot'
              ? 'bg-blue-100 text-blue-700'
              : 'bg-gray-100 text-gray-700'
          ]"
        >
          {{ service.category === 'autobot' ? 'AutoBot' : 'System' }}
        </span>
      </td>
      <td class="px-4 py-2 text-center text-green-600 font-medium">{{ service.running_count }}</td>
      <td class="px-4 py-2 text-center text-gray-500 font-medium">{{ service.stopped_count }}</td>
      <td class="px-4 py-2 text-center text-red-600 font-medium">{{ service.failed_count }}</td>
      <td class="px-4 py-2">
        <div class="flex items-center justify-end gap-1">
          <button
            @click="handleFleetServiceAction(service.service_name, 'start')"
            class="px-2 py-1 text-xs bg-green-100 text-green-700 rounded hover:bg-green-200"
            title="Start on all nodes"
          >Start</button>
          <button
            @click="handleFleetServiceAction(service.service_name, 'stop')"
            class="px-2 py-1 text-xs bg-red-100 text-red-700 rounded hover:bg-red-200"
            title="Stop on all nodes"
          >Stop</button>
          <button
            @click="handleFleetServiceAction(service.service_name, 'restart')"
            class="px-2 py-1 text-xs bg-blue-100 text-blue-700 rounded hover:bg-blue-200"
            title="Restart on all nodes"
          >Restart</button>
        </div>
      </td>
    </tr>

    <!-- Expanded per-node rows -->
    <tr v-if="expandedFleetServices.has(service.service_name)" class="bg-gray-50">
      <td colspan="6" class="px-0 py-0">
        <table class="w-full">
          <tbody>
            <tr
              v-for="nodeStatus in service.nodes"
              :key="nodeStatus.node_id"
              class="border-t border-gray-100"
            >
              <td class="pl-12 pr-4 py-1.5 w-64">
                <span class="text-sm text-gray-700 font-medium">
                  {{ getNodeHostname(nodeStatus.node_id) }}
                </span>
                <span class="text-xs text-gray-400 ml-1.5 font-mono">{{ nodeStatus.node_id }}</span>
              </td>
              <td class="px-4 py-1.5 w-28">
                <ServiceStatusBadge :status="nodeStatus.status as any" />
              </td>
              <td class="px-4 py-1.5 text-right">
                <ServiceActionButtons
                  :serviceName="service.service_name"
                  :nodeId="nodeStatus.node_id"
                  :status="nodeStatus.status as any"
                  :isActionInProgress="orchestration.actionInProgress"
                  :activeAction="orchestration.activeAction"
                  @start="(nId, svc) => handleServiceAction(nId, svc, 'start')"
                  @stop="(nId, svc) => handleServiceAction(nId, svc, 'stop')"
                  @restart="(nId, svc) => handleServiceAction(nId, svc, 'restart')"
                />
              </td>
            </tr>
          </tbody>
        </table>
      </td>
    </tr>
  </template>
</tbody>
```

### Step 3: Type-check and commit

```bash
cd /home/kali/Desktop/AutoBot/autobot-slm-frontend
npm run type-check 2>&1 | tail -20
```

```bash
cd /home/kali/Desktop/AutoBot
git add autobot-slm-frontend/src/views/OrchestrationView.vue
git commit -m "feat(slm/orchestration): expandable per-node rows in fleet services table (#NNN)"
```

---

## Task 5: SLM — Fleet Tab: Restart Warning with Node List

**File:** `autobot-slm-frontend/src/views/OrchestrationView.vue`

**Context:** The existing `handleFleetAction` calls the API directly with no confirmation. The fleet-level bulk action already uses `RestartConfirmDialog`. We add the same pattern for per-service fleet actions, showing exactly which nodes will be affected.

### Step 1: Add confirmation state and wrapper function

Find `// Actions: Fleet Operations` section. Add this state near the top of that section (after `fleetCategoryFilter` area is fine, or near the bulk confirm state):

```typescript
// Per-service fleet action confirmation
const showFleetServiceConfirm = ref(false)
const pendingFleetServiceAction = ref<{
  serviceName: string
  action: 'start' | 'stop' | 'restart'
  affectedNodes: Array<{ nodeId: string; hostname: string }>
} | null>(null)

function handleFleetServiceAction(
  serviceName: string,
  action: 'start' | 'stop' | 'restart',
): void {
  const service = orchestration.fleetServices.find((s) => s.service_name === serviceName)
  const affectedNodes = (service?.nodes ?? []).map((n) => ({
    nodeId: n.node_id,
    hostname: getNodeHostname(n.node_id),
  }))
  pendingFleetServiceAction.value = { serviceName, action, affectedNodes }
  showFleetServiceConfirm.value = true
}

async function confirmFleetServiceAction(): Promise<void> {
  const pending = pendingFleetServiceAction.value
  showFleetServiceConfirm.value = false
  pendingFleetServiceAction.value = null
  if (!pending) return
  await handleFleetAction(pending.serviceName, pending.action)
}
```

### Step 2: Add confirmation dialog to template

At the bottom of the template, alongside the existing `RestartConfirmDialog` blocks, add:

```html
<!-- Per-service fleet action confirmation -->
<RestartConfirmDialog
  :show="showFleetServiceConfirm"
  :title="`${pendingFleetServiceAction?.action
    ? pendingFleetServiceAction.action.charAt(0).toUpperCase() + pendingFleetServiceAction.action.slice(1)
    : ''} Fleet Service`"
  :message="pendingFleetServiceAction
    ? `<strong>${pendingFleetServiceAction.action.charAt(0).toUpperCase() + pendingFleetServiceAction.action.slice(1)}</strong>
       <code>${pendingFleetServiceAction.serviceName}</code> on ${pendingFleetServiceAction.affectedNodes.length} node(s):<br><br>
       ${pendingFleetServiceAction.affectedNodes.map(n => `• ${n.hostname} <span class='text-gray-400'>(${n.nodeId})</span>`).join('<br>')}`
    : ''"
  :confirmButtonText="pendingFleetServiceAction?.action
    ? pendingFleetServiceAction.action.charAt(0).toUpperCase() + pendingFleetServiceAction.action.slice(1)
    : 'Confirm'"
  @confirm="confirmFleetServiceAction"
  @cancel="showFleetServiceConfirm = false"
/>
```

### Step 3: Type-check and commit

```bash
cd /home/kali/Desktop/AutoBot/autobot-slm-frontend
npm run type-check 2>&1 | tail -20
```

```bash
cd /home/kali/Desktop/AutoBot
git add autobot-slm-frontend/src/views/OrchestrationView.vue
git commit -m "feat(slm/orchestration): restart confirmation dialog with affected node list (#NNN)"
```

---

## Task 6: Main Frontend — Preferences Tabs

**File:** `autobot-frontend/src/views/SettingsView.vue`

**Context:** Currently `SettingsView.vue` renders Appearance and Voice as two stacked `<section>` blocks. Convert to a tab bar with the same two sections as tabs.

### Step 1: Add activeTab state to script

The current script section is minimal (just imports + logger). Add `ref` import and the activeTab state:

```typescript
import PreferencesPanel from '@/components/ui/PreferencesPanel.vue'
import VoiceSettingsPanel from '@/components/settings/VoiceSettingsPanel.vue'
import { ref } from 'vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('SettingsView')
logger.debug('Settings view initialized')

type PreferenceTab = 'appearance' | 'voice'
const activeTab = ref<PreferenceTab>('appearance')
```

### Step 2: Replace the template body

Replace the entire `<div class="settings-sections">` block (which currently contains the two `<section>` elements) with:

```html
<!-- Tab Bar -->
<div class="settings-tabs">
  <button
    @click="activeTab = 'appearance'"
    :class="['settings-tab', { active: activeTab === 'appearance' }]"
  >
    <i class="fas fa-paint-brush"></i>
    Appearance
  </button>
  <button
    @click="activeTab = 'voice'"
    :class="['settings-tab', { active: activeTab === 'voice' }]"
  >
    <i class="fas fa-microphone"></i>
    Voice
  </button>
</div>

<!-- Tab Content -->
<div class="settings-tab-content">
  <section v-if="activeTab === 'appearance'" class="settings-section">
    <div class="section-header">
      <h2 class="section-title">
        <i class="fas fa-paint-brush"></i>
        Appearance
      </h2>
      <p class="section-description">Customize the look and feel of your workspace</p>
    </div>
    <div class="section-content">
      <PreferencesPanel />
    </div>
  </section>

  <section v-if="activeTab === 'voice'" class="settings-section">
    <div class="section-header">
      <h2 class="section-title">
        <i class="fas fa-microphone"></i>
        Voice
      </h2>
      <p class="section-description">Configure text-to-speech voice and voice profiles</p>
    </div>
    <div class="section-content">
      <VoiceSettingsPanel />
    </div>
  </section>
</div>
```

### Step 3: Add tab styles to the scoped CSS

In the `<style scoped>` block, add after the existing rules:

```css
/* ============================================
 * TAB NAVIGATION
 * ============================================ */

.settings-tabs {
  display: flex;
  gap: var(--spacing-2);
  border-bottom: 2px solid var(--border-default);
  margin-bottom: var(--spacing-xl);
}

.settings-tab {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-3) var(--spacing-4);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--text-secondary);
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  margin-bottom: -2px;
  cursor: pointer;
  transition: color 0.15s, border-color 0.15s;
}

.settings-tab:hover {
  color: var(--text-primary);
}

.settings-tab.active {
  color: var(--color-primary);
  border-bottom-color: var(--color-primary);
}

.settings-tab-content {
  min-height: 300px;
}
```

### Step 4: Type-check and commit

```bash
cd /home/kali/Desktop/AutoBot/autobot-frontend
npm run type-check 2>&1 | tail -20
```

```bash
cd /home/kali/Desktop/AutoBot
git add autobot-frontend/src/views/SettingsView.vue
git commit -m "feat(ui/preferences): convert settings page to tabbed layout (#NNN)"
```

---

## Task 7: Main Frontend — GUI Automation in Workflow Builder

**File:** `autobot-frontend/src/views/WorkflowBuilderView.vue`

**Context:** `WorkflowBuilderView.vue` has a `SectionType` union and a sidebar with 8 sections. We add `'gui-automation'` as a 9th section using the existing `VisionAutomationPage` component.

### Step 1: Extend SectionType and add title/description

Find `type SectionType =` (~line 518). Add `| 'gui-automation'` to the union:

```typescript
type SectionType =
  | 'overview'
  | 'canvas'
  | 'templates'
  | 'natural-language'
  | 'runner'
  | 'history'
  | 'orchestration'
  | 'agents'
  | 'gui-automation';
```

Find `const titles: Record<SectionType, string>` (~line 613). Add the entry:
```typescript
'gui-automation': 'GUI Automation',
```

Find `const descriptions: Record<SectionType, string>` (~line 627). Add the entry:
```typescript
'gui-automation': 'Detect and execute GUI automation opportunities from screen capture',
```

### Step 2: Import VisionAutomationPage

At the top of the `<script setup>` block, add the import alongside other component imports:

```typescript
import VisionAutomationPage from '@/components/vision/VisionAutomationPage.vue'
```

### Step 3: Add sidebar nav item

In the template, find the sidebar `<div class="category-divider"><span>Execute</span></div>` section. The "Execute" group contains runner, history, orchestration, agents. Add the GUI Automation button after the agents button:

```html
<button
  class="category-item"
  :class="{ active: activeSection === 'gui-automation' }"
  @click="activeSection = 'gui-automation'"
  role="button"
  aria-label="GUI automation from screen capture"
  tabindex="0"
>
  <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
      d="M15 12a3 3 0 11-6 0 3 3 0 016 0z M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
  </svg>
  <span>GUI Automation</span>
</button>
```

### Step 4: Add content section

Find the agents section closing tag (`</section>` around line 490). Add a new section immediately after it:

```html
<section v-if="activeSection === 'gui-automation'" class="section-gui-automation">
  <VisionAutomationPage />
</section>
```

### Step 5: Type-check and commit

```bash
cd /home/kali/Desktop/AutoBot/autobot-frontend
npm run type-check 2>&1 | tail -20
```

```bash
cd /home/kali/Desktop/AutoBot
git add autobot-frontend/src/views/WorkflowBuilderView.vue
git commit -m "feat(ui/automation): add GUI Automation section to workflow builder sidebar (#NNN)"
```

---

## Task 8: Build and Verify

### SLM Frontend

```bash
cd /home/kali/Desktop/AutoBot/autobot-slm-frontend
npm run build 2>&1 | tail -30
```

Expected: `✓ built in Xs` with no errors.

### Main Frontend

```bash
cd /home/kali/Desktop/AutoBot/autobot-frontend
npm run build 2>&1 | tail -30
```

Expected: `✓ built in Xs` with no errors.

### Close issue

```bash
gh issue close NNN --comment "Implemented: role assignment card in migration tab, fleet category filter + per-node expand + restart warning, preferences tabs, GUI automation in workflow builder. All type-checks and builds pass."
gh issue view NNN
```

---

## Deployment (optional, run separately)

After builds pass, sync to VMs:

**SLM frontend → .19:**
```bash
# (check existing sync script for SLM frontend path)
ssh autobot@172.16.168.19 "sudo systemctl restart autobot-slm-frontend 2>/dev/null || true"
```

**Main frontend → .21:**
```bash
cd /home/kali/Desktop/AutoBot/autobot-frontend
npm run build
./autobot-infrastructure/shared/scripts/utilities/sync-to-vm.sh 172.16.168.21 dist/ /opt/autobot/autobot-frontend/dist/
```
