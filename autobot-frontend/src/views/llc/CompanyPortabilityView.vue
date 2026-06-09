<template>
  <div class="portability-view">
    <!-- Header -->
    <div class="page-header">
      <div class="page-header-content">
        <h2 class="page-title">Company Portability</h2>
        <p class="page-subtitle">Export your company as a reusable template or snapshot, or import from a template file.</p>
      </div>
    </div>

    <!-- Error banner -->
    <div v-if="globalError" class="error-banner">
      <span>{{ globalError }}</span>
      <button class="btn-dismiss" @click="globalError = null">✕</button>
    </div>

    <div class="portability-sections">
      <!-- ═══════════════════════════════════════════════════
           EXPORT SECTION
      ════════════════════════════════════════════════════ -->
      <section class="portability-card">
        <h3 class="card-title">Export</h3>
        <p class="card-desc">
          Download your company structure as a portable JSON file.
          Secrets are never included — only placeholder names are exported.
        </p>

        <div class="export-buttons">
          <button
            class="btn-primary"
            :disabled="exportingTemplate || !effectiveCompanyId"
            @click="exportTemplate"
          >
            <span v-if="exportingTemplate" class="spinner" />
            <span v-else>⬇ Export Template</span>
          </button>

          <button
            class="btn-secondary"
            :disabled="exportingSnapshot || !effectiveCompanyId"
            @click="exportSnapshot"
          >
            <span v-if="exportingSnapshot" class="spinner" />
            <span v-else>⬇ Export Snapshot</span>
          </button>
        </div>

        <p v-if="!effectiveCompanyId" class="export-hint">
          Select a company to enable exporting.
        </p>
        <p class="export-hint">
          <strong>Template</strong> — agents, goals, routines, seed tasks (no sprint history, no secrets).<br />
          <strong>Snapshot</strong> — full backup including all work items and sprint history.
        </p>

      </section>

      <!-- ═══════════════════════════════════════════════════
           IMPORT SECTION
      ════════════════════════════════════════════════════ -->
      <section class="portability-card">
        <h3 class="card-title">Import</h3>
        <p class="card-desc">Upload a JSON template file to preview and execute an import.</p>

        <!-- File drop zone -->
        <div
          class="drop-zone"
          :class="{ 'drop-zone--over': isDragOver, 'drop-zone--loaded': !!importFile }"
          @dragover.prevent="isDragOver = true"
          @dragleave="onDragLeave"
          @drop.prevent="onDrop"
          @click="fileInputRef?.click()"
        >
          <input
            ref="fileInputRef"
            type="file"
            accept=".json,application/json"
            class="file-input-hidden"
            @change="onFileChange"
          />
          <template v-if="importFile">
            <span class="drop-zone-icon">📄</span>
            <span class="drop-zone-label">{{ importFile.name }}</span>
            <button class="btn-clear-file" @click.stop="clearFile">✕ Clear</button>
          </template>
          <template v-else>
            <span class="drop-zone-icon">📁</span>
            <span class="drop-zone-label">Drag &amp; drop or click to upload a JSON template</span>
          </template>
        </div>

        <!-- Preview button -->
        <div class="import-actions">
          <button
            class="btn-primary"
            :disabled="!importFile || loadingPreview"
            @click="runPreview"
          >
            <span v-if="loadingPreview" class="spinner" />
            <span v-else>🔍 Preview Import</span>
          </button>
        </div>

        <!-- Preview results -->
        <div v-if="importPreview" class="preview-panel">
          <h4 class="subsection-title">Import Preview</h4>

          <!-- Warnings -->
          <div v-if="importPreview.warnings.length > 0" class="preview-warnings">
            <h5>⚠ Warnings</h5>
            <ul>
              <li v-for="(w, i) in importPreview.warnings" :key="i">{{ w }}</li>
            </ul>
          </div>

          <!-- Collisions -->
          <div v-if="importPreview.collisions.length > 0" class="preview-collisions">
            <h5>Collisions detected</h5>
            <table class="preview-table">
              <thead>
                <tr><th>Type</th><th>Name</th><th>Resolution</th></tr>
              </thead>
              <tbody>
                <tr
                  v-for="(c, i) in importPreview.collisions"
                  :key="i"
                  class="row-collision"
                >
                  <td>{{ c.type }}</td>
                  <td>{{ c.name }}</td>
                  <td>{{ c.resolution }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- Will create summary -->
          <div class="preview-summary">
            <h5>Entities to create</h5>
            <ul class="create-list">
              <li>Agents: <strong>{{ importPreview.will_create.agents }}</strong></li>
              <li>Goals: <strong>{{ importPreview.will_create.goals }}</strong></li>
              <li>Projects: <strong>{{ importPreview.will_create.projects }}</strong></li>
              <li>Work items: <strong>{{ importPreview.will_create.work_items }}</strong></li>
            </ul>
          </div>

          <!-- Secret mapping -->
          <div v-if="secretPlaceholders.length > 0" class="secret-mapping">
            <h5>Secret Mapping</h5>
            <p class="secret-hint">
              The template references the following secrets. Provide the actual values or secret binding names.
            </p>
            <div
              v-for="placeholder in secretPlaceholders"
              :key="placeholder"
              class="secret-row"
            >
              <label class="secret-label">{{ placeholder }}</label>
              <input
                v-model="secretMapping[placeholder]"
                type="text"
                class="secret-input"
                :placeholder="`Value or binding for ${placeholder}`"
              />
            </div>
          </div>

          <!-- Execute button -->
          <div class="execute-actions">
            <button
              class="btn-danger"
              :disabled="executingImport || secretMappingIncomplete"
              @click="executeImport"
            >
              <span v-if="executingImport" class="spinner" />
              <span v-else>▶ Execute Import</span>
            </button>
            <span v-if="secretMappingIncomplete" class="hint-text">
              Fill in all secret values above before importing.
            </span>
          </div>
        </div>

        <!-- Import result -->
        <div v-if="importResult" class="import-result" :class="importResult.ok ? 'result-success' : 'result-error'">
          <template v-if="importResult.ok">
            ✅ Import successful — company ID: <strong>{{ importResult.company_id }}</strong>
            <ul v-if="importResult.created_entities" class="result-counts">
              <li v-for="(v, k) in importResult.created_entities" :key="k">{{ k }}: {{ v }}</li>
            </ul>
            <div v-if="importResult.warnings.length > 0">
              <p>Warnings:</p>
              <ul><li v-for="(w, i) in importResult.warnings" :key="i">{{ w }}</li></ul>
            </div>
          </template>
          <template v-else>
            ❌ Import failed: {{ importResult.error }}
          </template>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import { getApiBase } from '@/config/ssot-config'
import { useNotificationBus } from '@/composables/useNotificationBus'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('CompanyPortabilityView')
const { showToast } = useNotificationBus()
const route = useRoute()

// ── props ────────────────────────────────────────────────────────────────────
const props = defineProps<{ companyId?: string }>()
const effectiveCompanyId = computed(() => (route.params.companyId as string) ?? props.companyId ?? '')

// ── state ────────────────────────────────────────────────────────────────────
const globalError = ref<string | null>(null)

// Export
const exportingTemplate = ref(false)
const exportingSnapshot = ref(false)

// Import
const fileInputRef = ref<HTMLInputElement | null>(null)
const importFile = ref<File | null>(null)
const isDragOver = ref(false)
const loadingPreview = ref(false)
const importPreview = ref<ImportPreview | null>(null)
const previewPayload = ref<unknown>(null)
const secretMapping = ref<Record<string, string>>({})
const executingImport = ref(false)
const importResult = ref<ImportResultDisplay | null>(null)

// ── types ─────────────────────────────────────────────────────────────────────
interface Collision {
  type: string
  name: string
  resolution: string
}

interface WillCreate {
  agents: number
  goals: number
  projects: number
  work_items: number
}

interface ImportPreview {
  collisions: Collision[]
  will_create: WillCreate
  warnings: string[]
}

interface ImportResultDisplay {
  ok: boolean
  company_id?: string
  created_entities?: Record<string, number>
  warnings: string[]
  error?: string
}

// ── computed ──────────────────────────────────────────────────────────────────
const secretPlaceholders = ref<string[]>([])

const secretMappingIncomplete = computed(() =>
  secretPlaceholders.value.some((p: string) => !secretMapping.value[p]?.trim())
)

// ── helpers ───────────────────────────────────────────────────────────────────
async function triggerDownload(res: Response, defaultFilename: string): Promise<void> {
  const disposition = res.headers.get('content-disposition') ?? ''
  const match = disposition.match(/filename="?([^";\n]+)"?/)
  const filename = match?.[1] ?? defaultFilename
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 100)
}

function extractSecretPlaceholders(json: unknown): string[] {
  const str = JSON.stringify(json)
  const matches = str.match(/\{\{([A-Z0-9_]+)\}\}/g) ?? []
  return [...new Set(matches.map(m => m.replace(/^\{\{|\}\}$/g, '')))]
}

// ── export ────────────────────────────────────────────────────────────────────
async function exportTemplate(): Promise<void> {
  if (!effectiveCompanyId.value) return
  exportingTemplate.value = true
  try {
    const res = await fetchWithAuth(
      `${getApiBase()}/llc/companies/${effectiveCompanyId.value}/export/template`,
      { method: 'POST' }
    )
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
    await triggerDownload(res, `company_${effectiveCompanyId.value}_template.json`)
    showToast('Template exported successfully', 'success')
  } catch (e) {
    logger.error('Template export failed:', e)
    showToast('Template export failed', 'error')
  } finally {
    exportingTemplate.value = false
  }
}

async function exportSnapshot(): Promise<void> {
  if (!effectiveCompanyId.value) return
  exportingSnapshot.value = true
  try {
    const res = await fetchWithAuth(
      `${getApiBase()}/llc/companies/${effectiveCompanyId.value}/export/snapshot`,
      { method: 'POST' }
    )
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
    await triggerDownload(res, `company_${effectiveCompanyId.value}_snapshot.json`)
    showToast('Snapshot exported successfully', 'success')
  } catch (e) {
    logger.error('Snapshot export failed:', e)
    showToast('Snapshot export failed', 'error')
  } finally {
    exportingSnapshot.value = false
  }
}

// ── file handling ─────────────────────────────────────────────────────────────
function onDrop(e: DragEvent): void {
  isDragOver.value = false
  const file = e.dataTransfer?.files?.[0]
  if (file) loadFile(file)
}

// GH#8562: guard against dragleave firing on child elements (flicker fix)
function onDragLeave(e: DragEvent): void {
  if ((e.currentTarget as Element).contains(e.relatedTarget as Node)) return
  isDragOver.value = false
}

function onFileChange(e: Event): void {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file) loadFile(file)
}

function loadFile(file: File): void {
  if (!file.name.endsWith('.json') || file.type !== 'application/json') {
    showToast('Only JSON files are supported', 'error')
    return
  }
  importFile.value = file
  importPreview.value = null
  previewPayload.value = null
  importResult.value = null
  secretMapping.value = {}
  secretPlaceholders.value = []
}

function clearFile(): void {
  importFile.value = null
  importPreview.value = null
  previewPayload.value = null
  importResult.value = null
  secretMapping.value = {}
  secretPlaceholders.value = []
  if (fileInputRef.value) fileInputRef.value.value = ''
}

// ── preview ───────────────────────────────────────────────────────────────────
async function runPreview(): Promise<void> {
  if (!importFile.value) return
  loadingPreview.value = true
  importPreview.value = null
  previewPayload.value = null
  importResult.value = null
  try {
    const text = await importFile.value.text()
    const parsed: unknown = JSON.parse(text)
    const res = await fetchWithAuth(`${getApiBase()}/llc/import/preview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(parsed),
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({})) as Record<string, unknown>
      throw new Error((body.detail as string) ?? `${res.status} ${res.statusText}`)
    }
    const preview = await res.json() as ImportPreview
    // Populate placeholder state before showing preview so the guard is ready
    const placeholders = extractSecretPlaceholders(parsed)
    secretPlaceholders.value = placeholders
    for (const p of placeholders) {
      if (!secretMapping.value[p]) secretMapping.value[p] = ''
    }
    // GH#8561: store parsed payload to avoid re-reading file on execute (TOCTOU fix)
    previewPayload.value = parsed
    importPreview.value = preview
  } catch (e) {
    const msg = e instanceof Error ? e.message : 'Preview failed'
    logger.error('Import preview failed:', e)
    showToast(`Preview failed: ${msg}`, 'error')
  } finally {
    loadingPreview.value = false
  }
}

// ── execute ───────────────────────────────────────────────────────────────────
async function executeImport(): Promise<void> {
  if (!importPreview.value || !previewPayload.value) return
  executingImport.value = true
  importResult.value = null
  try {
    // GH#8561: reuse the payload captured during preview instead of re-reading file
    const parsed: unknown = previewPayload.value
    const res = await fetchWithAuth(`${getApiBase()}/llc/import/execute`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        template: parsed,
        remapping_options: {
          secret_mapping: { ...secretMapping.value },
          target_company_id: null,
        },
      }),
    })
    if (!res.ok) {
      const errBody = await res.json().catch(() => ({})) as Record<string, unknown>
      importResult.value = {
        ok: false,
        warnings: [],
        error: (errBody.detail as string) ?? `${res.status} ${res.statusText}`,
      }
      showToast('Import failed', 'error')
      return
    }
    const body = await res.json() as Record<string, unknown>
    importResult.value = {
      ok: true,
      company_id: body.company_id as string,
      created_entities: body.created_entities as Record<string, number>,
      warnings: (body.warnings as string[]) ?? [],
    }
    showToast('Import completed successfully', 'success')
  } catch (e) {
    const msg = e instanceof Error ? e.message : 'Import failed'
    logger.error('Import execute failed:', e)
    importResult.value = { ok: false, warnings: [], error: msg }
    showToast(`Import failed: ${msg}`, 'error')
  } finally {
    executingImport.value = false
  }
}
</script>

<style scoped>
@reference "../../assets/tailwind.css";

.portability-view {
  padding: var(--spacing-md) var(--spacing-md) var(--spacing-xl);
  max-width: 900px;
}

.page-header {
  margin-bottom: var(--spacing-xl);
}

.page-title {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
  color: var(--color-text-primary);
  margin: 0 0 var(--spacing-xs);
}

.page-subtitle {
  color: var(--color-text-secondary);
  margin: 0;
}

.error-banner {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  background: var(--color-error-bg, #fee2e2);
  border: 1px solid var(--color-error-border, #fca5a5);
  border-radius: var(--radius-md);
  padding: var(--spacing-sm) var(--spacing-md);
  margin-bottom: var(--spacing-md);
  color: var(--color-error-text, #991b1b);
}

.btn-dismiss {
  margin-left: auto;
  background: none;
  border: none;
  cursor: pointer;
  color: inherit;
}

.portability-sections {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xl);
}

.portability-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--spacing-lg);
}

.card-title {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  margin: 0 0 var(--spacing-xs);
  color: var(--color-text-primary);
}

.card-desc {
  color: var(--color-text-secondary);
  margin: 0 0 var(--spacing-md);
}

/* Export buttons */
.export-buttons {
  display: flex;
  gap: var(--spacing-sm);
  flex-wrap: wrap;
  margin-bottom: var(--spacing-sm);
}

.btn-primary {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-primary);
  color: #fff;
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-secondary {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-surface);
  color: var(--color-text-primary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
}

.btn-secondary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-danger {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-error, #dc2626);
  color: #fff;
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
}

.btn-danger:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.export-hint {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary, var(--color-text-secondary));
  margin: 0 0 var(--spacing-md);
}

/* Recent exports */
.recent-exports {
  margin-top: var(--spacing-md);
  border-top: 1px solid var(--color-border);
  padding-top: var(--spacing-md);
}

.subsection-title {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  margin: 0 0 var(--spacing-sm);
  color: var(--color-text-primary);
}

.export-table,
.preview-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-sm);
}

.export-table th,
.export-table td,
.preview-table th,
.preview-table td {
  text-align: left;
  padding: var(--spacing-xs) var(--spacing-sm);
  border-bottom: 1px solid var(--color-border);
}

.export-table th,
.preview-table th {
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-secondary);
}

.download-link {
  color: var(--color-primary);
  text-decoration: underline;
  cursor: pointer;
}

/* Drop zone */
.drop-zone {
  border: 2px dashed var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--spacing-xl) var(--spacing-md);
  text-align: center;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-xs);
  margin-bottom: var(--spacing-md);
}

.drop-zone:hover,
.drop-zone--over {
  border-color: var(--color-primary);
  background: var(--color-primary-bg, rgba(99, 102, 241, 0.05));
}

.drop-zone--loaded {
  border-color: var(--color-success, #16a34a);
  background: var(--color-success-bg, rgba(22, 163, 74, 0.05));
}

.file-input-hidden {
  display: none;
}

.drop-zone-icon {
  font-size: 2rem;
}

.drop-zone-label {
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
}

.btn-clear-file {
  background: none;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: 2px var(--spacing-xs);
  cursor: pointer;
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  margin-top: var(--spacing-xs);
}

/* Import actions */
.import-actions {
  display: flex;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-md);
}

/* Preview panel */
.preview-panel {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--spacing-md);
  background: var(--color-background, var(--color-surface));
  margin-top: var(--spacing-md);
}

.preview-warnings {
  background: var(--color-warning-bg, #fef9c3);
  border: 1px solid var(--color-warning-border, #fde047);
  border-radius: var(--radius-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  margin-bottom: var(--spacing-md);
  font-size: var(--font-size-sm);
}

.preview-warnings h5,
.preview-collisions h5,
.preview-summary h5 {
  font-weight: var(--font-weight-semibold);
  margin: 0 0 var(--spacing-xs);
}

.preview-warnings ul,
.preview-summary ul {
  margin: 0;
  padding-left: var(--spacing-md);
}

.preview-collisions {
  margin-bottom: var(--spacing-md);
}

.row-collision {
  background: var(--color-warning-bg, #fef9c3);
}

.preview-summary {
  margin-bottom: var(--spacing-md);
}

.create-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-sm) var(--spacing-md);
  font-size: var(--font-size-sm);
}

/* Secret mapping */
.secret-mapping {
  border-top: 1px solid var(--color-border);
  padding-top: var(--spacing-md);
  margin-top: var(--spacing-md);
  margin-bottom: var(--spacing-md);
}

.secret-hint {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  margin: 0 0 var(--spacing-sm);
}

.secret-row {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-xs);
}

.secret-label {
  font-family: var(--font-family-mono, monospace);
  font-size: var(--font-size-sm);
  color: var(--color-text-primary);
  min-width: 180px;
}

.secret-input {
  flex: 1;
  padding: var(--spacing-xs) var(--spacing-sm);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  background: var(--color-surface);
  color: var(--color-text-primary);
}

/* Execute */
.execute-actions {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  flex-wrap: wrap;
}

.hint-text {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}

/* Import result */
.import-result {
  margin-top: var(--spacing-md);
  border-radius: var(--radius-md);
  padding: var(--spacing-md);
  font-size: var(--font-size-sm);
}

.result-success {
  background: var(--color-success-bg, #dcfce7);
  border: 1px solid var(--color-success-border, #86efac);
  color: var(--color-success-text, #166534);
}

.result-error {
  background: var(--color-error-bg, #fee2e2);
  border: 1px solid var(--color-error-border, #fca5a5);
  color: var(--color-error-text, #991b1b);
}

.result-counts {
  list-style: none;
  padding: 0;
  margin: var(--spacing-xs) 0 0;
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-xs) var(--spacing-md);
}

/* Spinner */
.spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.4);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
