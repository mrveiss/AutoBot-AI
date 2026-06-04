/**
 * Tests for usePushNotifications composable (GH#4459)
 *
 * Coverage:
 * - Unsupported browser detection
 * - subscribe() → requestPermission → VAPID key fetch → pushManager.subscribe → POST backend
 * - subscribe() when permission is 'denied'
 * - unsubscribe() → DELETE backend → pushManager.unsubscribe
 * - Error propagation into error ref
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'

// ─── Mocks ────────────────────────────────────────────────────────────────────

const mockPost = vi.fn()
const mockGet = vi.fn()
vi.mock('@/utils/ApiClient', () => ({
  default: { get: mockGet, post: mockPost },
}))

const mockFetchWithAuth = vi.fn()
vi.mock('@/utils/fetchWithAuth', () => ({ fetchWithAuth: mockFetchWithAuth }))

vi.mock('@/config/ssot-config', () => ({ getApiBase: () => '/api' }))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ info: vi.fn(), error: vi.fn(), debug: vi.fn() }),
}))

// ─── Helpers ──────────────────────────────────────────────────────────────────

const makePushSubscription = (endpoint = 'https://push.example.com/sub') => ({
  endpoint,
  toJSON: () => ({
    endpoint,
    keys: { p256dh: 'cHVibGljS2V5', auth: 'YXV0aEtleQ==' },
  }),
  unsubscribe: vi.fn().mockResolvedValue(true),
})

function mockPushSupported(
  permissionState: NotificationPermission = 'default',
  existingSub: ReturnType<typeof makePushSubscription> | null = null,
  requestPermissionResult: NotificationPermission = 'granted',
) {
  const sub = existingSub

  const pushManager = {
    getSubscription: vi.fn().mockResolvedValue(sub),
    subscribe: vi.fn().mockResolvedValue(makePushSubscription()),
  }

  Object.defineProperty(window, 'Notification', {
    value: {
      permission: permissionState,
      requestPermission: vi.fn().mockResolvedValue(requestPermissionResult),
    },
    writable: true,
    configurable: true,
  })

  Object.defineProperty(navigator, 'serviceWorker', {
    value: {
      ready: Promise.resolve({ pushManager }),
    },
    writable: true,
    configurable: true,
  })

  Object.defineProperty(window, 'PushManager', {
    value: class {},
    writable: true,
    configurable: true,
  })

  return { pushManager }
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('usePushNotifications', () => {
  beforeEach(() => {
    vi.resetModules()
    mockPost.mockReset()
    mockGet.mockReset()
    mockFetchWithAuth.mockReset()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  describe('isSupported', () => {
    it('returns false when Notification API is absent', async () => {
      Object.defineProperty(window, 'Notification', { value: undefined, writable: true, configurable: true })
      Object.defineProperty(window, 'PushManager', { value: undefined, writable: true, configurable: true })

      const { usePushNotifications } = await import('../usePushNotifications')
      const { isSupported } = usePushNotifications()
      expect(isSupported).toBe(false)
    })

    it('returns true when all APIs are present', async () => {
      mockPushSupported()
      const { usePushNotifications } = await import('../usePushNotifications')
      const { isSupported } = usePushNotifications()
      expect(isSupported).toBe(true)
    })
  })

  describe('subscribe()', () => {
    it('fetches VAPID key, subscribes via PushManager, and POSTs to backend', async () => {
      const { pushManager } = mockPushSupported('default', null, 'granted')
      mockGet.mockResolvedValue({ vapidPublicKey: 'dGVzdEtleQ==' }) // base64 "testKey"
      mockPost.mockResolvedValue({ status: 'subscribed' })

      const { usePushNotifications } = await import('../usePushNotifications')
      const { subscribe, subscribed, error } = usePushNotifications()

      await subscribe()

      expect(mockGet).toHaveBeenCalledWith('/api/push/vapid-public-key')
      expect(pushManager.subscribe).toHaveBeenCalledWith(
        expect.objectContaining({ userVisibleOnly: true }),
      )
      expect(mockPost).toHaveBeenCalledWith(
        '/api/push/subscribe',
        expect.objectContaining({ endpoint: expect.any(String) }),
      )
      expect(subscribed.value).toBe(true)
      expect(error.value).toBeNull()
    })

    it('sets error when permission is denied', async () => {
      mockPushSupported('denied', null, 'denied')

      const { usePushNotifications } = await import('../usePushNotifications')
      const { subscribe, subscribed, error } = usePushNotifications()

      await subscribe()

      expect(subscribed.value).toBe(false)
      expect(error.value).toContain('denied')
      expect(mockPost).not.toHaveBeenCalled()
    })

    it('sets error when backend POST fails', async () => {
      mockPushSupported('granted', null, 'granted')
      mockGet.mockResolvedValue({ vapidPublicKey: 'dGVzdEtleQ==' })
      mockPost.mockRejectedValue(new Error('HTTP 500: Internal Server Error'))

      const { usePushNotifications } = await import('../usePushNotifications')
      const { subscribe, subscribed, error } = usePushNotifications()

      await subscribe()

      expect(subscribed.value).toBe(false)
      expect(error.value).toContain('HTTP 500')
    })
  })

  describe('unsubscribe()', () => {
    it('calls DELETE endpoint and unsubscribes via PushManager', async () => {
      const existingSub = makePushSubscription()
      // Start with existing subscription so getSubscription returns it
      mockPushSupported('granted', existingSub, 'granted')
      mockGet.mockResolvedValue({ vapidPublicKey: 'dGVzdEtleQ==' })
      mockPost.mockResolvedValue({ status: 'subscribed' })
      mockFetchWithAuth.mockResolvedValue({ ok: true, status: 200 })

      const { usePushNotifications } = await import('../usePushNotifications')
      const push = usePushNotifications()
      // Subscribe first so _subscribed is true
      await push.subscribe()

      // Reset mocks for the actual unsubscribe call
      mockFetchWithAuth.mockResolvedValue({ ok: true, status: 200 })

      await push.unsubscribe()

      expect(mockFetchWithAuth).toHaveBeenCalledWith(
        expect.stringContaining('/api/push/unsubscribe'),
        expect.objectContaining({ method: 'DELETE' }),
      )
      expect(existingSub.unsubscribe).toHaveBeenCalled()
      expect(push.subscribed.value).toBe(false)
    })

    it('sets error when DELETE fails with non-404 status', async () => {
      const existingSub = makePushSubscription()
      mockPushSupported('granted', existingSub, 'granted')
      mockFetchWithAuth.mockResolvedValue({ ok: false, status: 500 })

      const { usePushNotifications } = await import('../usePushNotifications')
      const push = usePushNotifications()

      await push.unsubscribe()

      expect(push.error.value).toContain('HTTP 500')
    })

    it('tolerates 404 from backend (subscription already gone)', async () => {
      const existingSub = makePushSubscription()
      mockPushSupported('granted', existingSub, 'granted')
      mockFetchWithAuth.mockResolvedValue({ ok: false, status: 404 })

      const { usePushNotifications } = await import('../usePushNotifications')
      const push = usePushNotifications()

      await push.unsubscribe()

      expect(push.error.value).toBeNull()
      expect(push.subscribed.value).toBe(false)
    })
  })
})
