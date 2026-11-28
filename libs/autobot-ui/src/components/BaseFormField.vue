<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0
  BaseFormField — a labelled form field (#14780 group 4).
  Replaces the `form-group` / `label` utility classes (29 files across both apps): a label tied
  to its control, an optional hint, and an error that the control is described by. The
  control is the default slot, which receives what it must bind to be accessible:
    { id, describedBy, invalid, required }  ->  :id, :aria-describedby, :aria-invalid, :required
  Pair `error` with useFormValidation: `:error="errors[name]"`.
    props : label, id (generated when omitted), hint, error, required
    slots : default (the control), label (rich label content)
-->
<script setup lang="ts">
import { computed, useId } from 'vue'

const props = withDefaults(
  defineProps<{
    label: string
    id?: string
    hint?: string
    error?: string | null
    required?: boolean
  }>(),
  { id: undefined, hint: undefined, error: null, required: false },
)

const generatedId = useId()
const fieldId = computed(() => props.id ?? `aui-field-${generatedId}`)
const hintId = computed(() => `${fieldId.value}-hint`)
const errorId = computed(() => `${fieldId.value}-error`)
const describedBy = computed(() => {
  const ids = [props.hint ? hintId.value : '', props.error ? errorId.value : ''].filter(Boolean)
  return ids.length ? ids.join(' ') : undefined
})
</script>

<template>
  <div class="aui-field" :class="{ 'aui-field--invalid': !!error }">
    <label :for="fieldId" class="aui-field__label">
      <slot name="label">{{ label }}</slot>
      <span v-if="required" class="aui-field__required" aria-hidden="true">*</span>
    </label>
    <slot :id="fieldId" :described-by="describedBy" :invalid="!!error" :required="required" />
    <p v-if="hint" :id="hintId" class="aui-field__hint">{{ hint }}</p>
    <p v-if="error" :id="errorId" class="aui-field__error" role="alert">{{ error }}</p>
  </div>
</template>

<style scoped>
.aui-field {
  display: flex;
  flex-direction: column;
  gap: var(--aui-space-1);
  margin-bottom: var(--aui-space-4);
}

.aui-field__label {
  display: flex;
  gap: var(--aui-space-1);
  color: var(--aui-color-text);
  font-size: var(--aui-text-sm);
  font-weight: var(--aui-font-weight-medium);
}

.aui-field__required {
  color: var(--aui-color-error);
}

.aui-field__hint {
  margin: 0;
  color: var(--aui-color-text-muted);
  font-size: var(--aui-text-xs);
}

.aui-field__error {
  margin: 0;
  color: var(--aui-color-error);
  font-size: var(--aui-text-xs);
}
</style>
