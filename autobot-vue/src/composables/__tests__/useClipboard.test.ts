/**
 * Tests for useClipboard Composable
 *
 * Coverage:
 * - Basic copy functionality
 * - Modern Clipboard API
 * - Fallback for older browsers (execCommand)
 * - Error handling
 * - Copied state management
 * - Auto-reset functionality
 * - Manual reset
 * - Callbacks (onSuccess, onError)
 * - Browser support detection
 * - Legacy mode
 * - Helper functions
 * - Edge cases
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { nextTick } from 'vue'
import {
  useClipboard,
  useClipboardWithMessage,
  useClipboardElement,
  type ClipboardOptions
} from '../useClipboard'

// ========================================
// Test Setup
// ========================================

// Mock navigator.clipboard
const mockWriteText = vi.fn()
const mockClipboard = {
  writeText: mockWriteText
}

// Mock document.execCommand
const mockExecCommand = vi.fn()

beforeEach(() => {
  // Reset mocks
  mockWriteText.mockReset()
  mockExecCommand.mockReset()

  // Mock successful clipboard API by default
  mockWriteText.mockResolvedValue(undefined)
  mockExecCommand.mockReturnValue(true)

  // Setup navigator.clipboard
  Object.defineProperty(navigator, 'clipboard', {
    value: mockClipboard,
    writable: true,
    configurable: true
  })

  // Setup document.execCommand
  document.execCommand = mockExecCommand

  // Mock document.body methods for fallback
  document.body.appendChild = vi.fn()
  document.body.removeChild = vi.fn()

  // Clear timers
  vi.clearAllTimers()
})

afterEach(() => {
  vi.restoreAllMocks()
})

// ========================================
// Basic Functionality Tests
// ========================================

describe('useClipboard - Basic Functionality', () => {
  it('should initialize with correct default values', () => {
    const clipboard = useClipboard()

    expect(clipboard.copied.value).toBe(false)
    expect(clipboard.error.value).toBe(null)
    expect(clipboard.copiedText.value).toBe('')
    expect(clipboard.isSupported.value).toBe(true)
  })

  it('should copy text successfully', async () => {
    const clipboard = useClipboard()

    const result = await clipboard.copy('Hello, World!')

    expect(result).toBe(true)
    expect(mockWriteText).toHaveBeenCalledWith('Hello, World!')
    expect(clipboard.copied.value).toBe(true)
    expect(clipboard.copiedText.value).toBe('Hello, World!')
    expect(clipboard.error.value).toBe(null)
  })

  it('should handle empty string', async () => {
    const clipboard = useClipboard()

    const result = await clipboard.copy('')

    expect(result).toBe(false)
    expect(clipboard.error.value).toBeTruthy()
    expect(clipboard.copied.value).toBe(false)
  })

  it('should handle non-string input', async () => {
    const clipboard = useClipboard()

    // @ts-expect-error Testing invalid input
    const result = await clipboard.copy(null)

    expect(result).toBe(false)
    expect(clipboard.error.value).toBeTruthy()
  })

  it('should reset error on successful copy', async () => {
    const clipboard = useClipboard()

    // First copy fails
    mockWriteText.mockRejectedValueOnce(new Error('Permission denied'))
    await clipboard.copy('Test')
    expect(clipboard.error.value).toBeTruthy()

    // Second copy succeeds
    mockWriteText.mockResolvedValueOnce(undefined)
    await clipboard.copy('Test 2')
    expect(clipboard.error.value).toBe(null)
  })
})

// ========================================
// Clipboard API Tests
// ========================================

describe('useClipboard - Clipboard API', () => {
  it('should use navigator.clipboard.writeText when supported', async () => {
    const clipboard = useClipboard()

    await clipboard.copy('Test text')

    expect(mockWriteText).toHaveBeenCalledWith('Test text')
    expect(mockWriteText).toHaveBeenCalledTimes(1)
  })

  it('should handle Clipboard API errors', async () => {
    const clipboard = useClipboard()

    mockWriteText.mockRejectedValueOnce(new Error('Permission denied'))

    const result = await clipboard.copy('Test')

    expect(result).toBe(false)
    expect(clipboard.error.value).toBeInstanceOf(Error)
    expect(clipboard.copied.value).toBe(false)
  })

  it('should detect Clipboard API support', () => {
    const clipboard = useClipboard()
    expect(clipboard.isSupported.value).toBe(true)

    // Remove clipboard API
    Object.defineProperty(navigator, 'clipboard', {
      value: undefined,
      configurable: true
    })

    const clipboard2 = useClipboard()
    expect(clipboard2.isSupported.value).toBe(false)
  })
})

// ========================================
// Fallback Tests (execCommand)
// ========================================

describe('useClipboard - Fallback (execCommand)', () => {
  beforeEach(() => {
    // Remove clipboard API to test fallback
    Object.defineProperty(navigator, 'clipboard', {
      value: undefined,
      configurable: true
    })
  })

  it('should use execCommand fallback when Clipboard API not supported', async () => {
    const clipboard = useClipboard()

    expect(clipboard.isSupported.value).toBe(false)

    await clipboard.copy('Fallback text')

    expect(mockExecCommand).toHaveBeenCalledWith('copy')
    expect(clipboard.copied.value).toBe(true)
  })

  it('should create and remove temporary textarea for fallback', async () => {
    const clipboard = useClipboard()

    const appendChildSpy = vi.spyOn(document.body, 'appendChild')
    const removeChildSpy = vi.spyOn(document.body, 'removeChild')

    await clipboard.copy('Fallback text')

    expect(appendChildSpy).toHaveBeenCalledTimes(1)
    expect(removeChildSpy).toHaveBeenCalledTimes(1)

    // Check textarea properties
    const textarea = appendChildSpy.mock.calls[0][0] as HTMLTextAreaElement
    expect(textarea.value).toBe('Fallback text')
    expect(textarea.style.position).toBe('fixed')
    expect(textarea.style.opacity).toBe('0')
  })

  it('should handle fallback failure', async () => {
    mockExecCommand.mockReturnValueOnce(false)

    const clipboard = useClipboard()

    const result = await clipboard.copy('Test')

    expect(result).toBe(false)
    expect(clipboard.error.value).toBeTruthy()
    expect(clipboard.copied.value).toBe(false)
  })

  it('should handle fallback exceptions', async () => {
    mockExecCommand.mockImplementationOnce(() => {
      throw new Error('execCommand failed')
    })

    const clipboard = useClipboard()

    const result = await clipboard.copy('Test')

    expect(result).toBe(false)
    expect(clipboard.error.value).toBeTruthy()
  })
})

// ========================================
// Copied State Management Tests
// ========================================

describe('useClipboard - Copied State', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('should auto-reset copied state after default duration', async () => {
    const clipboard = useClipboard()

    await clipboard.copy('Test')
    expect(clipboard.copied.value).toBe(true)

    // Fast-forward 2000ms (default duration)
    vi.advanceTimersByTime(2000)

    expect(clipboard.copied.value).toBe(false)
    expect(clipboard.copiedText.value).toBe('')
  })

  it('should auto-reset after custom duration', async () => {
    const clipboard = useClipboard({
      copiedDuration: 5000
    })

    await clipboard.copy('Test')
    expect(clipboard.copied.value).toBe(true)

    vi.advanceTimersByTime(4999)
    expect(clipboard.copied.value).toBe(true)

    vi.advanceTimersByTime(1)
    expect(clipboard.copied.value).toBe(false)
  })

  it('should not auto-reset when duration is 0', async () => {
    const clipboard = useClipboard({
      copiedDuration: 0
    })

    await clipboard.copy('Test')
    expect(clipboard.copied.value).toBe(true)

    vi.advanceTimersByTime(10000)
    expect(clipboard.copied.value).toBe(true)  // Still copied
  })

  it('should manually reset copied state', async () => {
    const clipboard = useClipboard({
      copiedDuration: 0  // Disable auto-reset
    })

    await clipboard.copy('Test')
    expect(clipboard.copied.value).toBe(true)

    clipboard.resetCopied()
    expect(clipboard.copied.value).toBe(false)
    expect(clipboard.copiedText.value).toBe('')
  })

  it('should clear previous timer when copying again', async () => {
    const clipboard = useClipboard({
      copiedDuration: 2000
    })

    await clipboard.copy('First')
    expect(clipboard.copied.value).toBe(true)

    vi.advanceTimersByTime(1000)

    await clipboard.copy('Second')
    expect(clipboard.copiedText.value).toBe('Second')

    // Old timer should be cleared, new timer started
    vi.advanceTimersByTime(1999)
    expect(clipboard.copied.value).toBe(true)

    vi.advanceTimersByTime(1)
    expect(clipboard.copied.value).toBe(false)
  })
})

// ========================================
// Callback Tests
// ========================================

describe('useClipboard - Callbacks', () => {
  it('should call onSuccess callback on successful copy', async () => {
    const onSuccess = vi.fn()

    const clipboard = useClipboard({
      onSuccess
    })

    await clipboard.copy('Success text')

    expect(onSuccess).toHaveBeenCalledWith('Success text')
    expect(onSuccess).toHaveBeenCalledTimes(1)
  })

  it('should call onError callback on copy failure', async () => {
    const onError = vi.fn()

    mockWriteText.mockRejectedValueOnce(new Error('Copy failed'))

    const clipboard = useClipboard({
      onError
    })

    await clipboard.copy('Fail text')

    expect(onError).toHaveBeenCalledTimes(1)
    expect(onError.mock.calls[0][0]).toBeInstanceOf(Error)
  })

  it('should support async callbacks', async () => {
    const onSuccess = vi.fn().mockResolvedValue(undefined)
    const onError = vi.fn().mockResolvedValue(undefined)

    const clipboard = useClipboard({
      onSuccess,
      onError
    })

    await clipboard.copy('Test')
    expect(onSuccess).toHaveBeenCalled()
  })

  it('should call onError for invalid input', async () => {
    const onError = vi.fn()

    const clipboard = useClipboard({
      onError
    })

    await clipboard.copy('')

    expect(onError).toHaveBeenCalledWith('Invalid text: must be a non-empty string')
  })
})

// ========================================
// Legacy Mode Tests
// ========================================

describe('useClipboard - Legacy Mode', () => {
  it('should force fallback when legacyMode is true', async () => {
    const clipboard = useClipboard({
      legacyMode: true
    })

    expect(clipboard.isSupported.value).toBe(false)

    await clipboard.copy('Legacy text')

    expect(mockWriteText).not.toHaveBeenCalled()
    expect(mockExecCommand).toHaveBeenCalledWith('copy')
  })

  it('should work correctly in legacy mode', async () => {
    const clipboard = useClipboard({
      legacyMode: true
    })

    const result = await clipboard.copy('Test')

    expect(result).toBe(true)
    expect(clipboard.copied.value).toBe(true)
  })
})

// ========================================
// Helper: useClipboardWithMessage
// ========================================

describe('useClipboardWithMessage Helper', () => {
  it('should initialize with empty message', () => {
    const clipboard = useClipboardWithMessage()

    expect(clipboard.message.value).toBe('')
    expect(clipboard.messageType.value).toBe('')
  })

  it('should show success message on successful copy', async () => {
    const clipboard = useClipboardWithMessage(
      'Copy successful!',
      'Copy failed!'
    )

    await clipboard.copy('Test')

    expect(clipboard.message.value).toBe('Copy successful!')
    expect(clipboard.messageType.value).toBe('success')
  })

  it('should show error message on copy failure', async () => {
    mockWriteText.mockRejectedValueOnce(new Error('Permission denied'))

    const clipboard = useClipboardWithMessage(
      'Copy successful!',
      'Copy failed!'
    )

    await clipboard.copy('Test')

    expect(clipboard.message.value).toBe('Copy failed!')
    expect(clipboard.messageType.value).toBe('error')
  })

  it('should use default messages', async () => {
    const clipboard = useClipboardWithMessage()

    await clipboard.copy('Test')

    expect(clipboard.message.value).toBe('Copied!')
    expect(clipboard.messageType.value).toBe('success')
  })
})

// ========================================
// Helper: useClipboardElement
// ========================================

describe('useClipboardElement Helper', () => {
  it('should copy text from HTML element', async () => {
    const element = document.createElement('div')
    element.textContent = 'Element text content'

    const clipboard = useClipboardElement()

    const result = await clipboard.copyElement(element)

    expect(result).toBe(true)
    expect(mockWriteText).toHaveBeenCalledWith('Element text content')
    expect(clipboard.copied.value).toBe(true)
  })

  it('should copy from ref element', async () => {
    const element = document.createElement('pre')
    element.innerText = 'Code content'

    const elementRef = { value: element }

    const clipboard = useClipboardElement()

    const result = await clipboard.copyElement(elementRef as any)

    expect(result).toBe(true)
    expect(mockWriteText).toHaveBeenCalledWith('Code content')
  })

  it('should handle undefined element ref', async () => {
    const elementRef = { value: undefined }

    const clipboard = useClipboardElement()

    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

    const result = await clipboard.copyElement(elementRef as any)

    expect(result).toBe(false)
    expect(consoleErrorSpy).toHaveBeenCalled()

    consoleErrorSpy.mockRestore()
  })

  it('should handle element with no text content', async () => {
    const element = document.createElement('div')
    // No text content

    const clipboard = useClipboardElement()

    const result = await clipboard.copyElement(element)

    expect(result).toBe(false)
    expect(clipboard.error.value).toBeTruthy()
  })

  it('should prefer textContent over innerText', async () => {
    const element = document.createElement('div')
    element.textContent = 'Text content'
    element.innerText = 'Inner text'

    const clipboard = useClipboardElement()

    await clipboard.copyElement(element)

    expect(mockWriteText).toHaveBeenCalledWith('Text content')
  })
})

// ========================================
// Edge Cases Tests
// ========================================

describe('useClipboard - Edge Cases', () => {
  it('should handle very long text', async () => {
    const longText = 'a'.repeat(1000000)  // 1 million characters

    const clipboard = useClipboard()

    const result = await clipboard.copy(longText)

    expect(result).toBe(true)
    expect(mockWriteText).toHaveBeenCalledWith(longText)
  })

  it('should handle special characters', async () => {
    const specialText = '!@#$%^&*()_+-={}[]|\\:";\'<>?,./`~\n\t\r'

    const clipboard = useClipboard()

    const result = await clipboard.copy(specialText)

    expect(result).toBe(true)
    expect(clipboard.copiedText.value).toBe(specialText)
  })

  it('should handle unicode characters', async () => {
    const unicodeText = '你好世界 🌍 مرحبا بالعالم Привет мир'

    const clipboard = useClipboard()

    const result = await clipboard.copy(unicodeText)

    expect(result).toBe(true)
    expect(mockWriteText).toHaveBeenCalledWith(unicodeText)
  })

  it('should reject whitespace-only text', async () => {
    const clipboard = useClipboard()

    const result = await clipboard.copy('   ')

    expect(result).toBe(false)
    expect(clipboard.copied.value).toBe(false)
    expect(clipboard.error.value).toBe('Invalid text: must be a non-empty string')
  })

  it('should handle rapid consecutive copies', async () => {
    const clipboard = useClipboard()

    const results = await Promise.all([
      clipboard.copy('Copy 1'),
      clipboard.copy('Copy 2'),
      clipboard.copy('Copy 3')
    ])

    expect(results).toEqual([true, true, true])
    expect(clipboard.copiedText.value).toBe('Copy 3')  // Last copy wins
  })

  it('should handle copy during pending copy', async () => {
    vi.useFakeTimers()

    let resolveFirst: any
    mockWriteText.mockImplementationOnce(() => {
      return new Promise((resolve) => {
        resolveFirst = resolve
      })
    })

    const clipboard = useClipboard()

    // Start first copy (pending)
    const firstCopy = clipboard.copy('First')

    // Start second copy while first is pending
    const secondCopy = clipboard.copy('Second')

    // Resolve first copy
    resolveFirst()

    const results = await Promise.all([firstCopy, secondCopy])

    expect(results).toEqual([true, true])

    vi.useRealTimers()
  })
})

// ========================================
// Integration Tests
// ========================================

describe('useClipboard - Integration Tests', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('should handle complete workflow with callbacks and auto-reset', async () => {
    const onSuccess = vi.fn()
    const onError = vi.fn()

    const clipboard = useClipboard({
      copiedDuration: 3000,
      onSuccess,
      onError
    })

    // Copy successfully
    await clipboard.copy('Workflow test')

    expect(clipboard.copied.value).toBe(true)
    expect(clipboard.copiedText.value).toBe('Workflow test')
    expect(clipboard.error.value).toBe(null)
    expect(onSuccess).toHaveBeenCalledWith('Workflow test')

    // Wait for auto-reset
    vi.advanceTimersByTime(3000)

    expect(clipboard.copied.value).toBe(false)
    expect(clipboard.copiedText.value).toBe('')

    // Copy with error
    mockWriteText.mockRejectedValueOnce(new Error('Failed'))

    await clipboard.copy('Error test')

    expect(clipboard.copied.value).toBe(false)
    expect(clipboard.error.value).toBeInstanceOf(Error)
    expect(onError).toHaveBeenCalled()
  })

  it('should work with multiple clipboard instances', async () => {
    const clipboard1 = useClipboard({ copiedDuration: 1000 })
    const clipboard2 = useClipboard({ copiedDuration: 2000 })

    await clipboard1.copy('Instance 1')
    await clipboard2.copy('Instance 2')

    expect(clipboard1.copiedText.value).toBe('Instance 1')
    expect(clipboard2.copiedText.value).toBe('Instance 2')

    vi.advanceTimersByTime(1000)

    expect(clipboard1.copied.value).toBe(false)
    expect(clipboard2.copied.value).toBe(true)

    vi.advanceTimersByTime(1000)

    expect(clipboard2.copied.value).toBe(false)
  })
})
