<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  BaseInput — the one single-line text input for both apps (#14778).

  Rules it follows (see BaseButton):
    - styled ONLY via `--aui-*` tokens (no literal colors, no shadows); the
      focus ring is an outline, as for BaseButton;
    - no text of its own: label, helper, error and the clear-button label all
      come from the consuming app (the kit has no i18n catalog for it);
    - accessible by default: a real <label for> tied to a generated id,
      aria-invalid on error, aria-describedby pointing at the helper/error text;
      a caller's own aria-describedby ids are kept (the generated id is appended)
      and its aria-invalid stands whenever `error` is not set;
    - the clear button is icon-only, so it renders only with a non-empty
      `clearLabel` (its accessible name); `clearable` without one warns in dev.
    - class, style and data-* attrs land on the outer wrapper; every other attr
      (aria-label, aria-labelledby, name, maxlength, inputmode, listeners) lands on
      the native <input>, so a field with no visible label can still be named.
-->
<script setup lang="ts">
import { computed, ref, useAttrs, useId, warn, watchEffect } from 'vue'

defineOptions({ inheritAttrs: false })

export type InputSize = 'sm' | 'md' | 'lg'
export type InputType = 'text' | 'email' | 'password' | 'search' | 'tel' | 'url'

const props = withDefaults(
  defineProps<{
    modelValue?: string
    type?: InputType
    label?: string
    placeholder?: string
    helperText?: string
    error?: string
    size?: InputSize
    disabled?: boolean
    readonly?: boolean
    required?: boolean
    clearable?: boolean
    /** Accessible name of the clear button; without it `clearable` shows no button (and warns). */
    clearLabel?: string
    /** Overrides the generated id, for a form that targets the field itself. */
    id?: string
    /** Passed to the native input, e.g. 'email' or 'current-password'. */
    autocomplete?: string
  }>(),
  {
    modelValue: '',
    type: 'text',
    size: 'md',
    disabled: false,
    readonly: false,
    required: false,
    clearable: false,
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: string]
  clear: []
}>()

const attrs = useAttrs()
const WRAPPER_ATTR = /^(class|style|data-.+)$/
// Plain functions, not computed: attrs is not reactive, the render re-reads it on every update.
const pickAttrs = (onWrapper: boolean) =>
  Object.fromEntries(Object.entries(attrs).filter(([key]) => WRAPPER_ATTR.test(key) === onWrapper))

const uid = useId()
const inputId = computed(() => props.id || `${uid}-input`)
const helperId = `${uid}-helper`
const errorId = `${uid}-error`
const inputRef = ref<HTMLInputElement>()

// Plain functions for the same reason as pickAttrs: both read the caller's attrs.
const describedBy = () => {
  const own = props.error ? errorId : props.helperText ? helperId : undefined
  return [attrs['aria-describedby'], own].filter(Boolean).join(' ') || undefined
}
const ariaInvalid = () => (props.error ? 'true' : (attrs['aria-invalid'] as string | boolean | undefined))

const clearName = computed(() => props.clearLabel?.trim() ?? '')
// An icon-only button with no name is announced as just "button": better no button at all.
const showClear = computed(() => props.clearable && !!clearName.value && !!props.modelValue && !props.disabled && !props.readonly)
watchEffect(() => {
  if (props.clearable && !clearName.value) {
    warn('BaseInput: `clearable` needs `clearLabel`, or its icon-only clear button has no accessible name.')
  }
})

function onInput(event: Event) {
  emit('update:modelValue', (event.target as HTMLInputElement).value)
}

function onClear() {
  emit('update:modelValue', '')
  emit('clear')
  inputRef.value?.focus()
}

defineExpose({ focus: () => inputRef.value?.focus(), blur: () => inputRef.value?.blur() })
</script>

<template>
  <div class="aui-input" :class="`aui-input--${size}`" v-bind="pickAttrs(true)">
    <label v-if="label" :for="inputId" class="aui-input__label">
      {{ label }}<span v-if="required" class="aui-input__asterisk" aria-hidden="true">*</span>
    </label>

    <div
      class="aui-input__control"
      :class="{ 'aui-input__control--error': !!error, 'aui-input__control--disabled': disabled }"
    >
      <span v-if="$slots.prefix" class="aui-input__affix"><slot name="prefix" /></span>
      <input
        v-bind="pickAttrs(false)"
        :id="inputId"
        ref="inputRef"
        class="aui-input__field"
        :type="type"
        :value="modelValue"
        :placeholder="placeholder"
        :disabled="disabled"
        :readonly="readonly"
        :required="required"
        :autocomplete="autocomplete"
        :aria-invalid="ariaInvalid()"
        :aria-describedby="describedBy()"
        @input="onInput"
      />
      <span v-if="$slots.suffix || showClear" class="aui-input__affix">
        <button
          v-if="showClear"
          type="button"
          class="aui-input__clear"
          :aria-label="clearName"
          @click="onClear"
        >
          <span aria-hidden="true">&times;</span>
        </button>
        <slot name="suffix" />
      </span>
    </div>

    <p v-if="error" :id="errorId" class="aui-input__error" role="alert">{{ error }}</p>
    <p v-else-if="helperText" :id="helperId" class="aui-input__helper">{{ helperText }}</p>
  </div>
</template>

<style scoped>
.aui-input {
  display: flex;
  flex-direction: column;
  gap: var(--aui-space-1);
  font-family: var(--aui-font-sans);
}

.aui-input__label {
  font-size: var(--aui-text-sm);
  font-weight: var(--aui-font-weight-medium);
  color: var(--aui-color-text);
}

.aui-input__asterisk {
  margin-left: var(--aui-space-1);
  color: var(--aui-color-error);
}

.aui-input__control {
  display: flex;
  align-items: center;
  gap: var(--aui-space-2);
  height: var(--aui-input-height-md);
  padding: 0 var(--aui-input-padding-x);
  background-color: var(--aui-input-bg);
  border: 1px solid var(--aui-input-border);
  border-radius: var(--aui-radius-md);
  transition: border-color var(--aui-transition);
}

.aui-input--sm .aui-input__control {
  height: var(--aui-input-height-sm);
}
.aui-input--lg .aui-input__control {
  height: var(--aui-input-height-lg);
}

.aui-input__control:focus-within {
  border-color: var(--aui-color-primary);
  outline: var(--aui-focus-ring-width) solid var(--aui-color-focus-ring);
  outline-offset: 1px;
}

.aui-input__control--error,
.aui-input__control--error:focus-within {
  border-color: var(--aui-color-error);
}

.aui-input__control--disabled {
  background-color: var(--aui-color-surface-sunken);
  opacity: 0.6;
  cursor: not-allowed;
}

.aui-input__field {
  flex: 1;
  min-width: 0;
  width: 100%;
  background: transparent;
  border: none;
  outline: none;
  color: var(--aui-color-text);
  font-family: inherit;
  font-size: var(--aui-text-sm);
}
.aui-input--lg .aui-input__field {
  font-size: var(--aui-text-base);
}
.aui-input__field::placeholder {
  color: var(--aui-color-text-muted);
}
.aui-input__field:disabled {
  cursor: not-allowed;
}

.aui-input__affix {
  display: flex;
  align-items: center;
  gap: var(--aui-space-1);
  color: var(--aui-color-text-muted);
}

.aui-input__clear {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 var(--aui-space-1);
  background: transparent;
  border: none;
  border-radius: var(--aui-radius-sm);
  color: var(--aui-color-text-muted);
  font-size: var(--aui-text-lg);
  line-height: 1;
  cursor: pointer;
}
.aui-input__clear:hover {
  color: var(--aui-color-text);
}
.aui-input__clear:focus-visible {
  outline: var(--aui-focus-ring-width) solid var(--aui-color-focus-ring);
}

.aui-input__helper,
.aui-input__error {
  margin: 0;
  font-size: var(--aui-text-xs);
}
.aui-input__helper {
  color: var(--aui-color-text-muted);
}
.aui-input__error {
  color: var(--aui-color-error);
  font-weight: var(--aui-font-weight-medium);
}
</style>
