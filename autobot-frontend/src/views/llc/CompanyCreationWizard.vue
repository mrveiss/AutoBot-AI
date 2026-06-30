<template>
  <div class="company-creation-wizard">
    <!-- Step Indicator -->
    <div class="wizard-header">
      <div class="steps-indicator">
        <div
          v-for="(s, i) in STEPS"
          :key="s.n"
          class="step-item"
          :class="{ active: step === s.n, completed: step > s.n }"
        >
          <div class="step-circle">
            <Icon v-if="step > s.n" name="check" />
            <span v-else>{{ s.n }}</span>
          </div>
          <span class="step-label">{{ s.label }}</span>
          <div v-if="i < STEPS.length - 1" class="step-connector"></div>
        </div>
      </div>
    </div>

    <!-- Wizard Content -->
    <div class="wizard-content">
      <!-- Step 1: Choose Template -->
      <div v-if="step === 1" class="wizard-step">
        <div class="step-header">
          <h2>{{ $t('llc.wizard.step1.title') }}</h2>
          <p>{{ $t('llc.wizard.step1.description') }}</p>
        </div>

        <div class="template-choice">
          <button
            class="choice-card"
            :class="{ active: !useTemplate }"
            @click="useTemplate = false"
          >
            <Icon name="plus-circle" class="choice-icon" />
            <h3>{{ $t('llc.wizard.step1.startFromScratch') }}</h3>
            <p>{{ $t('llc.wizard.step1.startFromScratchDesc') }}</p>
          </button>
          <button
            class="choice-card"
            :class="{ active: useTemplate }"
            @click="useTemplate = true"
          >
            <Icon name="clone" class="choice-icon" />
            <h3>{{ $t('llc.wizard.step1.useTemplate') }}</h3>
            <p>{{ $t('llc.wizard.step1.useTemplateDesc') }}</p>
          </button>
        </div>

        <div v-if="useTemplate" class="template-browser-container">
          <TemplateBrowser v-model="selectedTemplate" />
        </div>
      </div>

      <!-- Step 2: Configure Company -->
      <div v-if="step === 2" class="wizard-step">
        <div class="step-header">
          <h2>{{ $t('llc.wizard.step2.title') }}</h2>
          <p>{{ $t('llc.wizard.step2.description') }}</p>
        </div>

        <div class="company-form">
          <div class="form-group">
            <label for="companyName" class="form-label">
              <span>{{ $t('llc.wizard.step2.companyName') }}</span>
              <span class="required">*</span>
            </label>
            <input
              id="companyName"
              v-model="companyConfig.name"
              type="text"
              class="form-input"
              :placeholder="$t('llc.wizard.step2.companyNamePlaceholder')"
              required
            />
          </div>

          <div class="form-group">
            <label for="issuePrefix" class="form-label">
              <span>{{ $t('llc.wizard.step2.issuePrefix') }}</span>
              <span class="required">*</span>
            </label>
            <input
              id="issuePrefix"
              v-model="companyConfig.issue_prefix"
              type="text"
              class="form-input"
              :placeholder="$t('llc.wizard.step2.issuePrefixPlaceholder')"
              maxlength="10"
              pattern="[A-Z]{2,10}"
              required
            />
            <span class="form-hint">{{ $t('llc.wizard.step2.issuePrefixHint') }}</span>
          </div>

          <div class="form-group">
            <label for="mission" class="form-label">
              <span>{{ $t('llc.wizard.step2.mission') }}</span>
            </label>
            <textarea
              id="mission"
              v-model="companyConfig.mission"
              class="form-textarea"
              :placeholder="$t('llc.wizard.step2.missionPlaceholder')"
              rows="4"
            ></textarea>
          </div>

          <div class="form-group">
            <label for="monthlyBudget" class="form-label">
              <span>{{ $t('llc.wizard.step2.monthlyBudget') }}</span>
            </label>
            <div class="budget-input">
              <span class="budget-currency">$</span>
              <input
                id="monthlyBudget"
                v-model.number="budgetDollars"
                type="number"
                class="form-input"
                min="0"
                step="10"
                :placeholder="$t('llc.wizard.step2.monthlyBudgetPlaceholder')"
              />
              <span class="budget-unit">/month</span>
            </div>
            <span v-if="selectedTemplate?.estimated_monthly_cost_cents" class="form-hint">
              {{ $t('llc.wizard.step2.estimatedCost') }}:
              ${{ (selectedTemplate.estimated_monthly_cost_cents / 100).toFixed(0) }}/mo
            </span>
          </div>

          <div class="form-group">
            <label for="brandColor" class="form-label">
              <span>{{ $t('llc.wizard.step2.brandColor') }}</span>
            </label>
            <div class="color-input">
              <input
                id="brandColor"
                v-model="companyConfig.brand_color"
                type="color"
                class="form-color"
              />
              <input
                v-model="companyConfig.brand_color"
                type="text"
                class="form-input"
                :placeholder="$t('llc.wizard.step2.brandColorPlaceholder')"
                pattern="#[0-9A-Fa-f]{6}"
              />
            </div>
          </div>

          <!-- Template Variables (if using template) -->
          <div v-if="selectedTemplate?.variables" class="form-section">
            <h3>{{ $t('llc.wizard.step2.templateVariables') }}</h3>
            <div
              v-for="(varMeta, varKey) in selectedTemplate.variables"
              :key="varKey"
              class="form-group"
            >
              <label :for="`var-${varKey}`" class="form-label">
                <span>{{ varMeta.description || varKey }}</span>
                <span v-if="varMeta.required" class="required">*</span>
              </label>
              <input
                :id="`var-${varKey}`"
                v-model="templateVariables[varKey]"
                type="text"
                class="form-input"
                :placeholder="varMeta.default"
                :required="varMeta.required"
              />
            </div>
          </div>
        </div>
      </div>

      <!-- Step 3: Review & Create -->
      <div v-if="step === 3" class="wizard-step">
        <div class="step-header">
          <h2>{{ $t('llc.wizard.step3.title') }}</h2>
          <p>{{ $t('llc.wizard.step3.description') }}</p>
        </div>

        <div class="review-summary">
          <div class="summary-section">
            <h3>{{ $t('llc.wizard.step3.companyDetails') }}</h3>
            <dl class="summary-list">
              <div class="summary-item">
                <dt>{{ $t('llc.wizard.step2.companyName') }}</dt>
                <dd>{{ companyConfig.name }}</dd>
              </div>
              <div class="summary-item">
                <dt>{{ $t('llc.wizard.step2.issuePrefix') }}</dt>
                <dd>{{ companyConfig.issue_prefix }}</dd>
              </div>
              <div v-if="companyConfig.mission" class="summary-item">
                <dt>{{ $t('llc.wizard.step2.mission') }}</dt>
                <dd>{{ companyConfig.mission }}</dd>
              </div>
              <div class="summary-item">
                <dt>{{ $t('llc.wizard.step2.monthlyBudget') }}</dt>
                <dd>${{ budgetDollars }}/month</dd>
              </div>
              <div class="summary-item">
                <dt>{{ $t('llc.wizard.step2.brandColor') }}</dt>
                <dd>
                  <div class="color-preview">
                    <span
                      class="color-swatch"
                      :style="{ background: companyConfig.brand_color }"
                    ></span>
                    {{ companyConfig.brand_color }}
                  </div>
                </dd>
              </div>
            </dl>
          </div>

          <div v-if="selectedTemplate" class="summary-section">
            <h3>{{ $t('llc.wizard.step3.template') }}</h3>
            <div class="template-summary">
              <div class="template-summary-header">
                <div
                  class="template-icon"
                  :class="`category-${selectedTemplate.category}`"
                >
                  <Icon
                    :name="
                      (selectedTemplate.icon as any) || getDefaultIcon(selectedTemplate.category)
                    "
                  />
                </div>
                <div>
                  <h4>{{ selectedTemplate.name }}</h4>
                  <p>{{ selectedTemplate.description }}</p>
                </div>
              </div>
              <dl class="summary-list">
                <div v-if="selectedTemplate.agents?.length" class="summary-item">
                  <dt>{{ $t('llc.wizard.step3.agents') }}</dt>
                  <dd>{{ selectedTemplate.agents.length }} agents</dd>
                </div>
                <div v-if="selectedTemplate.goals?.length" class="summary-item">
                  <dt>{{ $t('llc.wizard.step3.goals') }}</dt>
                  <dd>{{ selectedTemplate.goals.length }} goals</dd>
                </div>
                <div v-if="selectedTemplate.work_items?.length" class="summary-item">
                  <dt>{{ $t('llc.wizard.step3.workItems') }}</dt>
                  <dd>{{ selectedTemplate.work_items.length }} work items</dd>
                </div>
                <div v-if="selectedTemplate.kb_collections?.length" class="summary-item">
                  <dt>{{ $t('llc.wizard.step3.kbCollections') }}</dt>
                  <dd>{{ selectedTemplate.kb_collections.length }} KB collections</dd>
                </div>
              </dl>
            </div>
          </div>
        </div>

        <!-- Error -->
        <div v-if="error" class="error-banner">
          <Icon name="exclamation-triangle" />
          <span>{{ error }}</span>
        </div>
      </div>
    </div>

    <!-- Wizard Actions -->
    <div class="wizard-actions">
      <button
        v-if="step > 1"
        class="btn-secondary"
        @click="previousStep"
        :disabled="loading"
      >
        <Icon name="arrow-left" /> {{ $t('common.back') }}
      </button>
      <button v-else class="btn-secondary" @click="$router.push('/llc/dashboard')">
        <Icon name="times" /> {{ $t('common.cancel') }}
      </button>

      <button
        v-if="step < 3"
        class="btn-primary"
        @click="nextStep"
        :disabled="!canProceed"
      >
        {{ $t('common.next') }} <Icon name="arrow-right" />
      </button>
      <button v-else class="btn-primary" @click="createCompany" :disabled="loading">
        <Icon v-if="loading" name="spinner" spin />
        <Icon v-else name="check" />
        {{ $t('llc.wizard.step3.createCompany') }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
// GH#9164 - Company Creation Wizard with Template Browser

import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'
import { useCompanyTemplates, type CompanyTemplate, type TemplateCategory } from '@/composables/llc/useCompanyTemplates'
import TemplateBrowser from '@/components/llc/TemplateBrowser.vue'
import Icon from '@/components/ui/Icon.vue'

const logger = createLogger('CompanyCreationWizard')
const router = useRouter()
const api = useApiClient()
const { importTemplate } = useCompanyTemplates()

const STEPS = [
  { n: 1, label: 'Choose Template' },
  { n: 2, label: 'Configure' },
  { n: 3, label: 'Review' },
]

const step = ref(1)
const useTemplate = ref(false)
const selectedTemplate = ref<CompanyTemplate | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)

interface CompanyConfig {
  name: string
  issue_prefix: string
  mission: string
  monthly_budget_cents: number
  brand_color: string
}

const companyConfig = ref<CompanyConfig>({
  name: '',
  issue_prefix: '',
  mission: '',
  monthly_budget_cents: 10000, // $100 default
  brand_color: '#667eea',
})

const budgetDollars = computed({
  get: () => companyConfig.value.monthly_budget_cents / 100,
  set: (val: number) => {
    companyConfig.value.monthly_budget_cents = Math.round(val * 100)
  },
})

const templateVariables = ref<Record<string, string>>({})

const canProceed = computed(() => {
  if (step.value === 1) {
    return !useTemplate.value || selectedTemplate.value !== null
  }
  if (step.value === 2) {
    const hasName = companyConfig.value.name.trim().length > 0
    const hasPrefix = /^[A-Z]{2,10}$/.test(companyConfig.value.issue_prefix)
    const hasRequiredVars =
      !selectedTemplate.value?.variables ||
      Object.entries(selectedTemplate.value.variables).every(
        ([key, meta]) => !meta.required || templateVariables.value[key]?.trim()
      )
    return hasName && hasPrefix && hasRequiredVars
  }
  return true
})

function nextStep() {
  if (canProceed.value && step.value < 3) {
    step.value++
  }
}

function previousStep() {
  if (step.value > 1) {
    step.value--
    error.value = null
  }
}

function getDefaultIcon(cat: TemplateCategory): string {
  const icons: Record<TemplateCategory, string> = {
    'software-team': 'code',
    'marketing-agency': 'bullhorn',
    'consulting-firm': 'briefcase',
    'research-lab': 'flask',
    startup: 'rocket',
    custom: 'wrench',
  }
  return icons[cat] || 'building'
}

/**
 * Derive a backend-valid company slug from the company name.
 * Backend requires slug matching ^[a-z0-9-]+$ (CompanyBase). We lowercase,
 * collapse runs of non-alphanumeric chars to a single dash, and strip
 * leading/trailing dashes. Falls back to a timestamp-based slug if empty.
 */
function slugify(name: string): string {
  const slug = name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
  return slug || `company-${Date.now()}`
}

async function createCompany() {
  loading.value = true
  error.value = null

  try {
    // Step 1: Create the company.
    // Field names must match the backend CompanyCreate/CompanyBase schema
    // (autobot-backend/llc/models/company.py): slug is required, the budget key
    // is budget_monthly_cents, the mission maps to description, and llc_status
    // is left to the backend default (ONBOARDING) — do not send a bogus status.
    const companyPayload = {
      name: companyConfig.value.name,
      slug: slugify(companyConfig.value.name),
      issue_prefix: companyConfig.value.issue_prefix,
      description: companyConfig.value.mission || undefined,
      budget_monthly_cents: companyConfig.value.monthly_budget_cents,
      brand_color: companyConfig.value.brand_color,
    }

    logger.info('Creating company', companyPayload)
    const createdCompany = await api.post<{ id: string }>('/api/llc/companies', companyPayload)

    // Step 2: If template selected, import it
    if (selectedTemplate.value) {
      logger.info('Importing template', {
        templateKey: selectedTemplate.value.key,
        companyId: createdCompany.id,
      })

      const importPayload = {
        target_company_id: createdCompany.id,
        variable_values: templateVariables.value,
      }

      // For built-in templates, use the key as the template ID
      await importTemplate(selectedTemplate.value.key, importPayload)
    }

    logger.info('Company created successfully', { companyId: createdCompany.id })

    // Redirect into the new company's PM workspace (LlcCompanyLayout → backlog,
    // boards, sprints, etc. with the sidebar) rather than the sidebar-less
    // standalone /llc/dashboard, which left all PM features unreachable.
    await router.push(`/llc/companies/${createdCompany.id}`)
  } catch (err: any) {
    logger.error('Failed to create company', err)
    error.value = err?.response?.data?.detail || err?.message || 'Failed to create company'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.company-creation-wizard {
  /* Fill the available space provided by the app layout's <main> element
     (App.vue: main.flex-1.min-h-0 + router-view.h-full). Using 100vh here
     overflowed past the viewport by the header height and pushed the footer
     action buttons (Back/Next/Create) out of view. */
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: var(--bg-primary);
}

.wizard-header {
  flex-shrink: 0;
  padding: var(--spacing-6) var(--spacing-4);
  border-bottom: 1px solid var(--border-color);
  background: var(--bg-elevated);
}

.steps-indicator {
  display: flex;
  align-items: center;
  justify-content: center;
  max-width: 600px;
  margin: 0 auto;
}

.step-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  position: relative;
  flex: 1;
}

.step-circle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: var(--bg-tertiary);
  color: var(--text-muted);
  font-weight: 600;
  margin-bottom: var(--spacing-2);
  transition: all var(--duration-300);
  z-index: 1;
}

.step-item.active .step-circle {
  background: var(--color-primary);
  color: white;
  transform: scale(1.1);
}

.step-item.completed .step-circle {
  background: var(--color-success);
  color: white;
}

.step-label {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  text-align: center;
}

.step-item.active .step-label {
  color: var(--text-primary);
  font-weight: 500;
}

.step-connector {
  position: absolute;
  top: 20px;
  left: 50%;
  width: 100%;
  height: 2px;
  background: var(--border-color);
  z-index: 0;
}

.wizard-content {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: var(--spacing-6) var(--spacing-4);
}

.wizard-step {
  max-width: 800px;
  margin: 0 auto;
}

.step-header {
  text-align: center;
  margin-bottom: var(--spacing-6);
}

.step-header h2 {
  font-size: var(--text-3xl);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 var(--spacing-2);
}

.step-header p {
  font-size: var(--text-base);
  color: var(--text-secondary);
  margin: 0;
}

.template-choice {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-6);
}

.choice-card {
  padding: var(--spacing-6);
  background: var(--bg-secondary);
  border: 2px solid var(--border-color);
  border-radius: var(--radius-lg);
  text-align: center;
  cursor: pointer;
  transition: all var(--duration-200);
}

.choice-card:hover {
  border-color: var(--color-primary);
  transform: translateY(-2px);
}

.choice-card.active {
  border-color: var(--color-primary);
  background: var(--bg-tertiary);
}

.choice-icon {
  font-size: 48px;
  color: var(--color-primary);
  margin-bottom: var(--spacing-3);
}

.choice-card h3 {
  font-size: var(--text-xl);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 var(--spacing-2);
}

.choice-card p {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: 0;
}

.template-browser-container {
  height: 600px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.company-form {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-4);
}

.form-section {
  padding-top: var(--spacing-4);
  border-top: 1px solid var(--border-color);
}

.form-section h3 {
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 var(--spacing-4);
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1-5);
}

.form-label {
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-primary);
}

.required {
  color: var(--color-error);
}

.form-input,
.form-textarea {
  padding: var(--spacing-2-5) var(--spacing-3);
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-size: var(--text-sm);
  outline: none;
  transition: all var(--duration-200);
}

.form-input:focus,
.form-textarea:focus {
  border-color: var(--color-primary);
  background: var(--bg-tertiary);
}

.form-textarea {
  resize: vertical;
  font-family: inherit;
}

.form-hint {
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.budget-input,
.color-input {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.budget-currency,
.budget-unit {
  color: var(--text-secondary);
  font-size: var(--text-sm);
}

.form-color {
  width: 48px;
  height: 48px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  cursor: pointer;
}

.review-summary {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-6);
}

.summary-section {
  padding: var(--spacing-4);
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
}

.summary-section h3 {
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 var(--spacing-4);
}

.summary-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
  margin: 0;
}

.summary-item {
  display: grid;
  grid-template-columns: 140px 1fr;
  gap: var(--spacing-3);
}

.summary-item dt {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  font-weight: 500;
}

.summary-item dd {
  font-size: var(--text-sm);
  color: var(--text-primary);
  margin: 0;
}

.color-preview {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.color-swatch {
  display: inline-block;
  width: 20px;
  height: 20px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
}

.template-summary-header {
  display: flex;
  align-items: start;
  gap: var(--spacing-3);
  margin-bottom: var(--spacing-4);
  padding-bottom: var(--spacing-4);
  border-bottom: 1px solid var(--border-color);
}

.template-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 56px;
  height: 56px;
  border-radius: var(--radius-md);
  font-size: var(--text-2xl);
  flex-shrink: 0;
}

.template-summary-header h4 {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 var(--spacing-1);
}

.template-summary-header p {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: 0;
}

.error-banner {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-3);
  background: var(--color-error-bg);
  border: 1px solid var(--color-error);
  border-radius: var(--radius-md);
  color: var(--color-error);
  font-size: var(--text-sm);
  margin-top: var(--spacing-4);
}

.wizard-actions {
  flex-shrink: 0;
  display: flex;
  justify-content: space-between;
  gap: var(--spacing-3);
  padding: var(--spacing-4);
  border-top: 1px solid var(--border-color);
  background: var(--bg-elevated);
}

.btn-secondary,
.btn-primary {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-2);
  padding: var(--spacing-3) var(--spacing-6);
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
  border: 1px solid var(--border-color);
}

.btn-secondary:hover:not(:disabled) {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.btn-primary {
  background: var(--color-primary);
  color: white;
}

.btn-primary:hover:not(:disabled) {
  opacity: 0.9;
}

.btn-primary:disabled,
.btn-secondary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Template Icon Categories */
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
</style>
