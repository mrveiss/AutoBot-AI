// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Form Validation Composable
 *
 * Centralized form validation to eliminate duplicate validation logic across 12+ forms.
 * Supports field-level validation, real-time validation, async validators, and more.
 *
 * @see analysis/frontend-refactoring/FRONTEND_REFACTORING_EXAMPLES.md
 *
 * Features:
 * - Built-in validation rules (required, minLength, maxLength, pattern, email, url, etc.)
 * - Custom validators with async support
 * - Real-time validation on change/blur
 * - Touch and dirty state tracking
 * - Form-level validation status
 * - Cross-field validation
 * - Custom error messages
 * - TypeScript type safety
 *
 * Usage:
 * ```typescript
 * import { useFormValidation } from '@/composables/useFormValidation'
 *
 * const { fields, errors, isValid, validate, validateField, touch, reset } = useFormValidation({
 *   username: {
 *     value: '',
 *     rules: [
 *       { rule: 'required', message: 'Username is required' },
 *       { rule: 'minLength', value: 3, message: 'At least 3 characters' }
 *     ]
 *   },
 *   email: {
 *     value: '',
 *     rules: [
 *       { rule: 'required' },
 *       { rule: 'email', message: 'Invalid email format' }
 *     ]
 *   }
 * })
 *
 * // In template
 * <input v-model="fields.username" @blur="touch('username')" />
 * <span v-if="errors.username">{{ errors.username }}</span>
 * <button :disabled="!isValid">Submit</button>
 * ```
 */

import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { createLogger } from '@/utils/debugUtils'

// Create scoped logger for useFormValidation
const logger = createLogger('useFormValidation')

// ========================================
// Types & Interfaces
// ========================================

/** Form field values can be string, number, boolean, array, etc. */
type FormFieldValue = string | number | boolean | null | undefined | unknown[] | Record<string, unknown>

export type ValidationRule =
  | 'required'
  | 'minLength'
  | 'maxLength'
  | 'min'
  | 'max'
  | 'pattern'
  | 'email'
  | 'url'
  | 'number'
  | 'integer'
  | 'alpha'
  | 'alphanumeric'
  | 'custom'

export interface ValidationRuleConfig {
  rule: ValidationRule
  value?: string | number | boolean | RegExp
  message?: string
  validator?: (fieldValue: FormFieldValue, allFields: Record<string, FormFieldValue>) => boolean | string | Promise<boolean | string>
}

export interface FieldConfig {
  value: FormFieldValue
  rules?: ValidationRuleConfig[]
  validateOnChange?: boolean
  validateOnBlur?: boolean
  debounce?: number
}

export interface UseFormValidationReturn {
  fields: Record<string, Ref<FormFieldValue>>
  errors: Record<string, Ref<string>>
  touched: Record<string, Ref<boolean>>
  dirty: Record<string, Ref<boolean>>
  isValid: ComputedRef<boolean>
  isDirty: ComputedRef<boolean>
  isTouched: ComputedRef<boolean>
  validateField: (fieldName: string) => Promise<boolean>
  validate: () => Promise<boolean>
  touch: (fieldName: string) => void
  touchAll: () => void
  reset: () => void
  resetField: (fieldName: string) => void
  setFieldValue: (fieldName: string, value: FormFieldValue) => void
  setFieldError: (fieldName: string, error: string) => void
  clearErrors: () => void
  clearFieldError: (fieldName: string) => void
}

// ========================================
// Built-in Validators
// ========================================

const validators: Record<ValidationRule, (value: FormFieldValue, ruleValue?: string | number | boolean | RegExp) => boolean | string> = {
  required: (value) => {
    if (value === null || value === undefined) return 'This field is required'
    if (typeof value === 'string' && value.trim() === '') return 'This field is required'
    if (Array.isArray(value) && value.length === 0) return 'This field is required'
    return true
  },

  minLength: (value, min) => {
    if (!value) return true // Skip if empty (use 'required' rule for that)
    const length = String(value).length
    return length >= Number(min) || `Must be at least ${min} characters`
  },

  maxLength: (value, max) => {
    if (!value) return true
    const length = String(value).length
    return length <= Number(max) || `Must be at most ${max} characters`
  },

  min: (value, min) => {
    if (!value && value !== 0) return true
    const num = Number(value)
    return !isNaN(num) && num >= Number(min) || `Must be at least ${min}`
  },

  max: (value, max) => {
    if (!value && value !== 0) return true
    const num = Number(value)
    return !isNaN(num) && num <= Number(max) || `Must be at most ${max}`
  },

  pattern: (value, pattern) => {
    if (!value) return true
    return (pattern instanceof RegExp ? pattern : new RegExp(String(pattern))).test(String(value)) || 'Invalid format'
  },

  email: (value) => {
    if (!value) return true
    const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    return emailPattern.test(String(value)) || 'Invalid email address'
  },

  url: (value) => {
    if (!value) return true
    try {
      new URL(String(value))
      return true
    } catch {
      return 'Invalid URL format'
    }
  },

  number: (value) => {
    if (!value && value !== 0) return true
    return !isNaN(Number(value)) || 'Must be a valid number'
  },

  integer: (value) => {
    if (!value && value !== 0) return true
    const num = Number(value)
    return !isNaN(num) && Number.isInteger(num) || 'Must be a whole number'
  },

  alpha: (value) => {
    if (!value) return true
    return /^[a-zA-Z]+$/.test(String(value)) || 'Only letters allowed'
  },

  alphanumeric: (value) => {
    if (!value) return true
    return /^[a-zA-Z0-9]+$/.test(String(value)) || 'Only letters and numbers allowed'
  },

  custom: () => true // Handled by custom validator function
}

// ========================================
// Main Composable
// ========================================

export function useFormValidation(
  config: Record<string, FieldConfig>
): UseFormValidationReturn {
  // Store initial values for reset
  const initialValues: Record<string, FormFieldValue> = {}

  // Create reactive state for each field
  const fields: Record<string, Ref<FormFieldValue>> = {}
  const errors: Record<string, Ref<string>> = {}
  const touched: Record<string, Ref<boolean>> = {}
  const dirty: Record<string, Ref<boolean>> = {}

  // Validation debounce timers
  const debounceTimers: Record<string, NodeJS.Timeout> = {}

  // Initialize fields
  for (const [fieldName, fieldConfig] of Object.entries(config)) {
    initialValues[fieldName] = fieldConfig.value
    fields[fieldName] = ref(fieldConfig.value)
    errors[fieldName] = ref('')
    touched[fieldName] = ref(false)
    dirty[fieldName] = ref(false)

    // Watch for changes to track dirty state
    watch(fields[fieldName], (newValue) => {
      dirty[fieldName].value = newValue !== initialValues[fieldName]

      // Auto-validate on change if configured
      if (fieldConfig.validateOnChange) {
        if (fieldConfig.debounce) {
          clearTimeout(debounceTimers[fieldName])
          debounceTimers[fieldName] = setTimeout(() => {
            validateField(fieldName)
          }, fieldConfig.debounce)
        } else {
          validateField(fieldName)
        }
      }
    })
  }

  const validateField = async (fieldName: string): Promise<boolean> => {
    const fieldConfig = config[fieldName]
    if (!fieldConfig || !fieldConfig.rules) return true

    const fieldValue = fields[fieldName].value
    const allFieldValues = Object.entries(fields).reduce((acc, [key, fieldRef]) => {
      acc[key] = fieldRef.value
      return acc
    }, {} as Record<string, FormFieldValue>)

    // Clear previous error
    errors[fieldName].value = ''

    // Run validation rules
    for (const ruleConfig of fieldConfig.rules) {
      let result: boolean | string

      if (ruleConfig.rule === 'custom' && ruleConfig.validator) {
        // Custom validator
        result = await ruleConfig.validator(fieldValue, allFieldValues)
      } else {
        // Built-in validator
        const validator = validators[ruleConfig.rule]
        if (!validator) {
          logger.warn(`[useFormValidation] Unknown rule: ${ruleConfig.rule}`)
          continue
        }
        result = validator(fieldValue, ruleConfig.value)
      }

      // Handle validation result
      if (result !== true) {
        errors[fieldName].value = ruleConfig.message || (typeof result === 'string' ? result : 'Invalid value')
        return false
      }
    }

    return true
  }

  const validate = async (): Promise<boolean> => {
    const results = await Promise.all(
      Object.keys(fields).map(fieldName => validateField(fieldName))
    )
    return results.every(result => result)
  }

  const touch = (fieldName: string): void => {
    if (touched[fieldName]) {
      touched[fieldName].value = true

      // Auto-validate on blur if configured
      const fieldConfig = config[fieldName]
      if (fieldConfig?.validateOnBlur !== false) {
        validateField(fieldName)
      }
    }
  }

  const touchAll = (): void => {
    for (const fieldName of Object.keys(fields)) {
      touched[fieldName].value = true
    }
  }

  const reset = (): void => {
    for (const fieldName of Object.keys(fields)) {
      resetField(fieldName)
    }
  }

  const resetField = (fieldName: string): void => {
    if (fields[fieldName]) {
      fields[fieldName].value = initialValues[fieldName]
      errors[fieldName].value = ''
      touched[fieldName].value = false
      dirty[fieldName].value = false
    }
  }

  const setFieldValue = (fieldName: string, value: FormFieldValue): void => {
    if (fields[fieldName]) {
      fields[fieldName].value = value
    }
  }

  const setFieldError = (fieldName: string, error: string): void => {
    if (errors[fieldName]) {
      errors[fieldName].value = error
    }
  }

  const clearErrors = (): void => {
    for (const fieldName of Object.keys(errors)) {
      errors[fieldName].value = ''
    }
  }

  const clearFieldError = (fieldName: string): void => {
    if (errors[fieldName]) {
      errors[fieldName].value = ''
    }
  }

  // Computed properties
  const isValid = computed(() => {
    return Object.values(errors).every(error => !error.value)
  })

  const isDirty = computed(() => {
    return Object.values(dirty).some(d => d.value)
  })

  const isTouched = computed(() => {
    return Object.values(touched).some(t => t.value)
  })

  return {
    fields,
    errors,
    touched,
    dirty,
    isValid,
    isDirty,
    isTouched,
    validateField,
    validate,
    touch,
    touchAll,
    reset,
    resetField,
    setFieldValue,
    setFieldError,
    clearErrors,
    clearFieldError
  }
}

export async function quickValidate(
  value: FormFieldValue,
  rules: ValidationRuleConfig[]
): Promise<string> {
  for (const ruleConfig of rules) {
    let result: boolean | string

    if (ruleConfig.rule === 'custom' && ruleConfig.validator) {
      result = await ruleConfig.validator(value, {})
    } else {
      const validator = validators[ruleConfig.rule]
      if (!validator) continue
      result = validator(value, ruleConfig.value)
    }

    if (result !== true) {
      return ruleConfig.message || (typeof result === 'string' ? result : 'Invalid value')
    }
  }

  return ''
}

export { validators }
