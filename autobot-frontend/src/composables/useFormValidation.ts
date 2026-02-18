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
  /**
   * Built-in validation rule name or 'custom'
   */
  rule: ValidationRule

  /**
   * Value for rule (e.g., minLength value, pattern regex)
   */
  value?: any

  /**
   * Custom error message
   */
  message?: string

  /**
   * Custom validator function (for 'custom' rule)
   * @param fieldValue - Current field value
   * @param allFields - All field values for cross-field validation
   * @returns true if valid, false or error message if invalid
   */
  validator?: (fieldValue: any, allFields: Record<string, any>) => boolean | string | Promise<boolean | string>
}

export interface FieldConfig {
  /**
   * Initial field value
   */
  value: any

  /**
   * Validation rules for this field
   */
  rules?: ValidationRuleConfig[]

  /**
   * Validate on change (default: false)
   */
  validateOnChange?: boolean

  /**
   * Validate on blur (default: true)
   */
  validateOnBlur?: boolean

  /**
   * Debounce validation (milliseconds)
   */
  debounce?: number
}

export interface UseFormValidationReturn {
  /**
   * Reactive field values
   */
  fields: Record<string, Ref<any>>

  /**
   * Validation error messages
   */
  errors: Record<string, Ref<string>>

  /**
   * Touch state (field has been interacted with)
   */
  touched: Record<string, Ref<boolean>>

  /**
   * Dirty state (field value has changed from initial)
   */
  dirty: Record<string, Ref<boolean>>

  /**
   * Is entire form valid
   */
  isValid: ComputedRef<boolean>

  /**
   * Is form dirty (any field changed)
   */
  isDirty: ComputedRef<boolean>

  /**
   * Is form touched (any field touched)
   */
  isTouched: ComputedRef<boolean>

  /**
   * Validate specific field
   */
  validateField: (fieldName: string) => Promise<boolean>

  /**
   * Validate all fields
   */
  validate: () => Promise<boolean>

  /**
   * Mark field as touched
   */
  touch: (fieldName: string) => void

  /**
   * Mark all fields as touched
   */
  touchAll: () => void

  /**
   * Reset form to initial state
   */
  reset: () => void

  /**
   * Reset specific field
   */
  resetField: (fieldName: string) => void

  /**
   * Set field value programmatically
   */
  setFieldValue: (fieldName: string, value: any) => void

  /**
   * Set field error programmatically
   */
  setFieldError: (fieldName: string, error: string) => void

  /**
   * Clear all errors
   */
  clearErrors: () => void

  /**
   * Clear specific field error
   */
  clearFieldError: (fieldName: string) => void
}

// ========================================
// Built-in Validators
// ========================================

/**
 * Built-in validation functions
 */
const validators: Record<ValidationRule, (value: any, ruleValue?: any) => boolean | string> = {
  required: (value) => {
    if (value === null || value === undefined) return 'This field is required'
    if (typeof value === 'string' && value.trim() === '') return 'This field is required'
    if (Array.isArray(value) && value.length === 0) return 'This field is required'
    return true
  },

  minLength: (value, min: number) => {
    if (!value) return true // Skip if empty (use 'required' rule for that)
    const length = String(value).length
    return length >= min || `Must be at least ${min} characters`
  },

  maxLength: (value, max: number) => {
    if (!value) return true
    const length = String(value).length
    return length <= max || `Must be at most ${max} characters`
  },

  min: (value, min: number) => {
    if (!value && value !== 0) return true
    const num = Number(value)
    return !isNaN(num) && num >= min || `Must be at least ${min}`
  },

  max: (value, max: number) => {
    if (!value && value !== 0) return true
    const num = Number(value)
    return !isNaN(num) && num <= max || `Must be at most ${max}`
  },

  pattern: (value, pattern: RegExp) => {
    if (!value) return true
    return pattern.test(String(value)) || 'Invalid format'
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

/**
 * Create form validation
 *
 * @param config - Field configuration object
 * @returns Form validation state and methods
 *
 * @example
 * ```typescript
 * const { fields, errors, isValid, validate } = useFormValidation({
 *   username: {
 *     value: '',
 *     rules: [
 *       { rule: 'required' },
 *       { rule: 'minLength', value: 3 }
 *     ]
 *   }
 * })
 * ```
 */
export function useFormValidation(
  config: Record<string, FieldConfig>
): UseFormValidationReturn {
  // Store initial values for reset
  const initialValues: Record<string, any> = {}

  // Create reactive state for each field
  const fields: Record<string, Ref<any>> = {}
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

  /**
   * Validate a single field
   */
  const validateField = async (fieldName: string): Promise<boolean> => {
    const fieldConfig = config[fieldName]
    if (!fieldConfig || !fieldConfig.rules) return true

    const fieldValue = fields[fieldName].value
    const allFieldValues = Object.entries(fields).reduce((acc, [key, ref]) => {
      acc[key] = ref.value
      return acc
    }, {} as Record<string, any>)

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

  /**
   * Validate all fields
   */
  const validate = async (): Promise<boolean> => {
    const results = await Promise.all(
      Object.keys(fields).map(fieldName => validateField(fieldName))
    )
    return results.every(result => result)
  }

  /**
   * Mark field as touched
   */
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

  /**
   * Mark all fields as touched
   */
  const touchAll = (): void => {
    for (const fieldName of Object.keys(fields)) {
      touched[fieldName].value = true
    }
  }

  /**
   * Reset form to initial state
   */
  const reset = (): void => {
    for (const fieldName of Object.keys(fields)) {
      resetField(fieldName)
    }
  }

  /**
   * Reset specific field
   */
  const resetField = (fieldName: string): void => {
    if (fields[fieldName]) {
      fields[fieldName].value = initialValues[fieldName]
      errors[fieldName].value = ''
      touched[fieldName].value = false
      dirty[fieldName].value = false
    }
  }

  /**
   * Set field value programmatically
   */
  const setFieldValue = (fieldName: string, value: any): void => {
    if (fields[fieldName]) {
      fields[fieldName].value = value
    }
  }

  /**
   * Set field error programmatically
   */
  const setFieldError = (fieldName: string, error: string): void => {
    if (errors[fieldName]) {
      errors[fieldName].value = error
    }
  }

  /**
   * Clear all errors
   */
  const clearErrors = (): void => {
    for (const fieldName of Object.keys(errors)) {
      errors[fieldName].value = ''
    }
  }

  /**
   * Clear specific field error
   */
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

/**
 * Quick validation helper for simple use cases
 *
 * @param value - Value to validate
 * @param rules - Validation rules
 * @returns Error message or empty string if valid
 *
 * @example
 * ```typescript
 * const error = await quickValidate(email, [
 *   { rule: 'required' },
 *   { rule: 'email' }
 * ])
 * ```
 */
export async function quickValidate(
  value: any,
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

/**
 * Export validators for direct use if needed
 */
export { validators }
