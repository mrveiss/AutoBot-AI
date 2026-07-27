<template>
  <div class="scheduler-toggles">
    <div class="section-header">
      <div class="header-info">
        <h3><Icon name="clock" /> {{ $t('schedulers.title') }}</h3>
        <p class="description">{{ $t('schedulers.description') }}</p>
      </div>
      <button @click="load" class="btn-refresh" :disabled="loading">
        <Icon name="refresh" /> {{ $t('schedulers.refresh') }}
      </button>
    </div>

    <div v-if="loading" class="state-message">{{ $t('schedulers.loading') }}</div>

    <div v-else-if="error" class="state-message error">
      <Icon name="exclamation-triangle" /> {{ error }}
    </div>

    <div v-else-if="schedulers.length === 0" class="state-message">
      {{ $t('schedulers.empty') }}
    </div>

    <div v-else class="scheduler-list">
      <div v-for="job in schedulers" :key="job.name" class="scheduler-item">
        <div class="scheduler-info">
          <div class="scheduler-name">
            {{ job.name }}
            <span v-if="job.override_active" class="badge-override">
              {{ $t('schedulers.overridden') }}
            </span>
          </div>
          <p class="scheduler-description">{{ job.description }}</p>
          <p class="scheduler-meta">
            {{ $t('schedulers.defaultLabel') }}:
            <strong>{{ job.default_enabled ? $t('schedulers.on') : $t('schedulers.off') }}</strong>
            &middot; {{ $t('schedulers.runtimeLabel') }}: <strong>{{ job.runtime }}</strong>
          </p>
          <p v-if="job.inert_reason" class="scheduler-inert">
            <Icon name="info-circle" /> {{ job.inert_reason }}
          </p>
        </div>

        <div class="scheduler-actions">
          <label class="toggle" :title="toggleTitle(job)">
            <input
              type="checkbox"
              :checked="job.enabled"
              :disabled="busy === job.name"
              :aria-label="$t('schedulers.toggleAria', { name: job.name })"
              @change="onToggle(job, ($event.target as HTMLInputElement).checked)"
            />
            <span class="toggle-slider"></span>
          </label>
          <button
            v-if="job.override_active"
            class="btn-reset"
            :disabled="busy === job.name"
            @click="onReset(job)"
          >
            {{ $t('schedulers.revertToDefault') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import Icon from '@/components/ui/Icon.vue';
import { createLogger } from '@/utils/debugUtils';
import {
  listSchedulers,
  setScheduler,
  resetScheduler,
  type SchedulerState,
} from '@/utils/SchedulerTogglesApiClient';

// Options-API-style global $t is used in the template; this component only needs
// the imperative t() for the error strings it builds in script.
import { useI18n } from 'vue-i18n';

const { t } = useI18n();
const logger = createLogger('SchedulerToggles');

const schedulers = ref<SchedulerState[]>([]);
const loading = ref(false);
const busy = ref<string | null>(null);
const error = ref<string | null>(null);

function toggleTitle(job: SchedulerState): string {
  return job.enabled ? t('schedulers.disableTitle') : t('schedulers.enableTitle');
}

async function load(): Promise<void> {
  loading.value = true;
  error.value = null;
  try {
    const data = await listSchedulers();
    schedulers.value = data.schedulers ?? [];
  } catch (err) {
    logger.error('Failed to load schedulers:', err);
    error.value = t('schedulers.loadFailed');
  } finally {
    loading.value = false;
  }
}

async function onToggle(job: SchedulerState, enabled: boolean): Promise<void> {
  busy.value = job.name;
  error.value = null;
  try {
    const result = await setScheduler(job.name, enabled);
    job.enabled = result.enabled;
    job.override_active = result.override_active;
  } catch (err) {
    logger.error('Failed to toggle scheduler:', err);
    error.value = t('schedulers.toggleFailed', { name: job.name });
    // Re-read rather than trust the optimistic value: the checkbox already moved,
    // so leaving it there would misreport what the backend actually holds.
    await load();
  } finally {
    busy.value = null;
  }
}

async function onReset(job: SchedulerState): Promise<void> {
  busy.value = job.name;
  error.value = null;
  try {
    const result = await resetScheduler(job.name);
    job.enabled = result.enabled;
    job.override_active = result.override_active;
  } catch (err) {
    logger.error('Failed to reset scheduler:', err);
    error.value = t('schedulers.resetFailed', { name: job.name });
    await load();
  } finally {
    busy.value = null;
  }
}

onMounted(load);
</script>

<style scoped>
.scheduler-toggles {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
}

.header-info h3 {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin: 0;
}

.description {
  margin: 0.25rem 0 0;
  color: var(--text-muted);
  font-size: 0.9rem;
}

.state-message {
  padding: 1rem;
  color: var(--text-muted);
}

.state-message.error {
  color: var(--color-error);
}

.scheduler-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.scheduler-item {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
  padding: 0.85rem 1rem;
  border: 1px solid var(--border-default);
  border-radius: 8px;
  background: var(--bg-secondary);
}

.scheduler-name {
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.badge-override {
  font-size: 0.7rem;
  font-weight: 500;
  padding: 0.1rem 0.45rem;
  border-radius: 999px;
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.scheduler-description,
.scheduler-meta,
.scheduler-inert {
  margin: 0.3rem 0 0;
  font-size: 0.82rem;
  color: var(--text-muted);
}

.scheduler-inert {
  color: var(--color-warning);
}

.scheduler-actions {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 0.4rem;
  flex-shrink: 0;
}

.toggle {
  position: relative;
  display: inline-block;
  width: 44px;
  height: 24px;
}

.toggle input {
  opacity: 0;
  width: 0;
  height: 0;
}

.toggle-slider {
  position: absolute;
  cursor: pointer;
  inset: 0;
  background: var(--border-default);
  border-radius: 999px;
  transition: background 0.2s;
}

.toggle-slider::before {
  content: '';
  position: absolute;
  height: 18px;
  width: 18px;
  left: 3px;
  bottom: 3px;
  background: var(--text-inverse);
  border-radius: 50%;
  transition: transform 0.2s;
}

.toggle input:checked + .toggle-slider {
  background: var(--color-primary);
}

.toggle input:checked + .toggle-slider::before {
  transform: translateX(20px);
}

.toggle input:disabled + .toggle-slider {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-refresh,
.btn-reset {
  padding: 0.3rem 0.6rem;
  font-size: 0.78rem;
  border: 1px solid var(--border-default);
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
}

.btn-refresh:disabled,
.btn-reset:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
