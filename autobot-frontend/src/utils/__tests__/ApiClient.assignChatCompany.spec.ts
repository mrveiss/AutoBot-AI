// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #21997: the client call for the owner's audited, once-only assignment of an Unassigned chat to a company.
import { describe, it, expect, vi } from 'vitest';

import { ApiClient } from '@/utils/ApiClient';

describe('ApiClient.assignChatCompany (#21997)', () => {
  it('posts the company id to the chat session company route', async () => {
    const client = new ApiClient();
    const post = vi.spyOn(client, 'post').mockResolvedValue({ data: { session_id: 'c1' } });

    const result = await client.assignChatCompany('c1', 'company-1');

    expect(post).toHaveBeenCalledTimes(1);
    expect(post.mock.calls[0][0]).toMatch(/\/chat\/sessions\/c1\/company$/);
    expect(post.mock.calls[0][1]).toEqual({ company_id: 'company-1' });
    expect(result).toEqual({ data: { session_id: 'c1' } });
  });
});
