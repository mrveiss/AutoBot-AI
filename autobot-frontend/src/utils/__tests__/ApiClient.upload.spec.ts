// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #19983: the main app's upload routes are bearer-gated (check_admin_permission), so ApiClient.uploadFile
// must send the stored JWT through the kit's authorizeUpload hook, and none when there is no token.
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

const { token } = vi.hoisted(() => ({ token: { value: 'live-jwt' as string | null } }));

vi.mock('@/stores/useUserStore', () => ({ useUserStore: () => ({ logout: vi.fn() }) }));
vi.mock('@/utils/orgContext', () => ({ getSelectedCompanyId: () => '' }));
vi.mock('@/utils/authToken', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/utils/authToken')>()),
  readStoredAuthToken: () => token.value,
}));

import { ApiClient } from '@/utils/ApiClient';

class FakeXhr {
  static last: FakeXhr;
  headers: Record<string, string> = {};
  upload: Record<string, unknown> = {};
  timeout = 0;
  status = 200;
  responseText = '{"ok":true}';
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  ontimeout: (() => void) | null = null;
  constructor() {
    FakeXhr.last = this;
  }
  open = vi.fn();
  setRequestHeader(name: string, value: string) {
    this.headers[name] = value;
  }
  send() {
    this.onload?.();
  }
}

describe('ApiClient.uploadFile auth (#19983)', () => {
  beforeEach(() => {
    token.value = 'live-jwt';
    vi.stubGlobal('XMLHttpRequest', FakeXhr);
  });
  afterEach(() => vi.unstubAllGlobals());

  it('sends the stored bearer on the upload request', async () => {
    await new ApiClient().uploadFile('/api/x/upload', new File(['a'], 'a.txt'));
    expect(FakeXhr.last.headers.Authorization).toBe('Bearer live-jwt');
  });

  it('sends no Authorization header when there is no stored token', async () => {
    token.value = null;
    await new ApiClient().uploadFile('/api/x/upload', new File(['a'], 'a.txt'));
    expect(FakeXhr.last.headers.Authorization).toBeUndefined();
  });
});
