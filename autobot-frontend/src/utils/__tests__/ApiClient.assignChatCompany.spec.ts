// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #21997: the client call for the owner's audited, once-only assignment of an Unassigned chat to a company.
import { describe, it, expect, vi } from 'vitest';

import { ApiClient } from '@/utils/ApiClient';

describe('ApiClient.assignChatCompany (#21997)', () => {
  it('posts the company id to the chat session company route through the typed contract', async () => {
    const client = new ApiClient();
    const call = vi.spyOn(client, 'call').mockResolvedValue({ data: { session_id: 'c1' } } as never);

    const result = await client.assignChatCompany('c1', 'company-1');

    expect(call).toHaveBeenCalledWith('post', '/api/chat/sessions/{session_id}/company', {
      path: { session_id: 'c1' },
      body: { company_id: 'company-1' },
    });
    expect(result).toEqual({ data: { session_id: 'c1' } });
  });
});
