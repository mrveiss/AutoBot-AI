// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Shared Settings Handlers Composable
 *
 * Provides reusable typed event handlers for settings forms.
 * Eliminates duplicate handler patterns across settings components.
 *
 * Issue #184: Split oversized Vue components
 */

import { reactive } from 'vue'

/**
 * Validation result interface
 */
export interface ValidationResult {
  isValid: boolean
  error?: string
}

/**
 * Validation state for form fields
 */
export interface ValidationState {
  errors: Record<string, string>
  success: Record<string, boolean>
}

/**
 * Creates reusable typed event handlers for settings forms
 *
 * @param emit - Vue emit function for the component
 * @param eventName - Name of the event to emit (e.g., 'setting-changed')
 * @returns Object containing handler functions
 */
export function useSettingsHandlers<T extends (...args: unknown[]) => void>(
  emit: T,
  eventName: string
) {
  /**
   * Handle text input change
   */
  const handleInputChange = (key: string) => (event: Event) => {
    const target = event.target as HTMLInputElement
    ;(emit as Function)(eventName, key, target.value)
  }

  /**
   * Handle number input change
   */
  const handleNumberInputChange = (key: string) => (event: Event) => {
    const target = event.target as HTMLInputElement
    ;(emit as Function)(eventName, key, parseInt(target.value, 10))
  }

  /**
   * Handle float input change
   */
  const handleFloatInputChange = (key: string) => (event: Event) => {
    const target = event.target as HTMLInputElement
    ;(emit as Function)(eventName, key, parseFloat(target.value))
  }

  /**
   * Handle checkbox change
   */
  const handleCheckboxChange = (key: string) => (event: Event) => {
    const target = event.target as HTMLInputElement
    ;(emit as Function)(eventName, key, target.checked)
  }

  /**
   * Handle select change
   */
  const handleSelectChange = (key: string) => (event: Event) => {
    const target = event.target as HTMLSelectElement
    ;(emit as Function)(eventName, key, target.value)
  }

  return {
    handleInputChange,
    handleNumberInputChange,
    handleFloatInputChange,
    handleCheckboxChange,
    handleSelectChange
  }
}

/**
 * Creates validation state and handlers for settings forms
 *
 * @returns Validation state and utility functions
 */
export function useSettingsValidation() {
  const validationState = reactive<ValidationState>({
    errors: {},
    success: {}
  })

  /**
   * Clear validation state for a field
   */
  const clearValidation = (key: string) => {
    delete validationState.errors[key]
    delete validationState.success[key]
  }

  /**
   * Set validation error for a field
   */
  const setError = (key: string, error: string) => {
    validationState.errors[key] = error
    delete validationState.success[key]
  }

  /**
   * Set validation success for a field
   */
  const setSuccess = (key: string) => {
    validationState.success[key] = true
    delete validationState.errors[key]
  }

  /**
   * Check if field has error
   */
  const hasError = (key: string): boolean => {
    return key in validationState.errors
  }

  /**
   * Check if field is valid
   */
  const isValid = (key: string): boolean => {
    return validationState.success[key] === true
  }

  /**
   * Get error message for field
   */
  const getError = (key: string): string | undefined => {
    return validationState.errors[key]
  }

  return {
    validationState,
    clearValidation,
    setError,
    setSuccess,
    hasError,
    isValid,
    getError
  }
}

/**
 * Common validation rules for settings fields
 */
export const validationRules = {
  /**
   * Validate URL format
   */
  url: (value: string): ValidationResult => {
    if (!value || typeof value !== 'string') {
      return { isValid: false, error: 'URL is required' }
    }
    if (!value.startsWith('http://') && !value.startsWith('https://')) {
      return { isValid: false, error: 'Must start with http:// or https://' }
    }
    return { isValid: true }
  },

  /**
   * Validate hostname format
   */
  hostname: (value: string): ValidationResult => {
    if (!value || typeof value !== 'string') {
      return { isValid: false, error: 'Hostname is required' }
    }
    // Simple hostname validation
    const hostnameRegex = /^[a-zA-Z0-9]([a-zA-Z0-9.-]*[a-zA-Z0-9])?$/
    if (!hostnameRegex.test(value) && value !== 'localhost') {
      return { isValid: false, error: 'Invalid hostname format' }
    }
    return { isValid: true }
  },

  /**
   * Validate port number
   */
  port: (value: number): ValidationResult => {
    if (typeof value !== 'number' || isNaN(value)) {
      return { isValid: false, error: 'Port must be a number' }
    }
    if (value < 1 || value > 65535) {
      return { isValid: false, error: 'Port must be between 1 and 65535' }
    }
    return { isValid: true }
  },

  /**
   * Validate required string
   */
  required: (value: string, fieldName = 'This field'): ValidationResult => {
    if (!value || (typeof value === 'string' && value.trim() === '')) {
      return { isValid: false, error: `${fieldName} is required` }
    }
    return { isValid: true }
  },

  /**
   * Validate positive number
   */
  positiveNumber: (value: number, fieldName = 'Value'): ValidationResult => {
    if (typeof value !== 'number' || isNaN(value)) {
      return { isValid: false, error: `${fieldName} must be a number` }
    }
    if (value <= 0) {
      return { isValid: false, error: `${fieldName} must be positive` }
    }
    return { isValid: true }
  },

  /**
   * Validate number in range
   */
  range: (value: number, min: number, max: number, fieldName = 'Value'): ValidationResult => {
    if (typeof value !== 'number' || isNaN(value)) {
      return { isValid: false, error: `${fieldName} must be a number` }
    }
    if (value < min || value > max) {
      return { isValid: false, error: `${fieldName} must be between ${min} and ${max}` }
    }
    return { isValid: true }
  }
}
