# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Redis Lua scripts behind `work_claims` (split out to keep that module under its size ceiling)."""

# ``cjson`` is available in Redis Lua. Each script is one round trip and runs
# atomically, which is what makes "no two overlapping exclusive claims" true
# across uvicorn workers -- a read-then-write in Python cannot promise it.
_ACQUIRE_LUA = """
local idx, prefix, path = KEYS[1], ARGV[1], ARGV[2]
local mode, payload, ttl = ARGV[3], ARGV[4], tonumber(ARGV[5])
local agent, task = ARGV[6], ARGV[7]
local mine = path .. '|' .. agent .. '|' .. task
local members = redis.call('SMEMBERS', idx)
local renewing = false
local prior = nil
local pruned = {}
for i = 1, #members do
  local member = members[i]
  local raw = redis.call('GET', prefix .. member)
  if not raw then
    redis.call('SREM', idx, member)
    pruned[#pruned + 1] = member
  else
    local sep = string.find(member, '|', 1, true)
    local held_path = string.sub(member, 1, sep - 1)
    local overlaps = held_path == path
      or string.sub(path, 1, #held_path + 1) == held_path .. '/'
      or string.sub(held_path, 1, #path + 1) == path .. '/'
    if overlaps then
      if member == mine then
        renewing = true
        prior = raw
      else
        local held = cjson.decode(raw)
        local same_holder = held.agent_id == agent and held.task_id == task
        local both_shared = mode == 'shared' and held.mode == 'shared'
        if not same_holder and not both_shared then
          return {'conflict', raw, pruned}
        end
      end
    end
  end
end
redis.call('SET', prefix .. mine, payload, 'EX', ttl)
redis.call('SADD', idx, mine)
if renewing then
  local fresh = cjson.decode(payload)
  fresh.renewals = (cjson.decode(prior).renewals or 0) + 1
  payload = cjson.encode(fresh)
  redis.call('SET', prefix .. mine, payload, 'EX', ttl)
  return {'renewed', payload, pruned}
end
return {'acquired', payload, pruned}
"""

# Ownership is now STRUCTURAL, not checked: a holder's key contains its own
# identity, so there is no key another holder could delete by mistake. The
# owner-check these scripts used to carry is gone because it became a
# tautology, not because the property was dropped.
_RELEASE_LUA = """
local idx, prefix = KEYS[1], ARGV[1]
local mine = ARGV[2] .. '|' .. ARGV[3] .. '|' .. ARGV[4]
redis.call('SREM', idx, mine)
return redis.call('DEL', prefix .. mine)
"""

# Renew rewrites the payload rather than only calling EXPIRE: `expires_at` is
# read by `list_claims` and by every `ClaimConflict`, so a TTL extended without
# it leaves a live claim advertising a time in the past, and a refused agent
# retries immediately against a holder it was told had expired.
_RENEW_LUA = """
local prefix, ttl, expires = ARGV[1], tonumber(ARGV[2]), ARGV[3]
local key = prefix .. ARGV[4] .. '|' .. ARGV[5] .. '|' .. ARGV[6]
local raw = redis.call('GET', key)
if not raw then return 0 end
local held = cjson.decode(raw)
held.expires_at = expires
held.renewals = (held.renewals or 0) + 1
redis.call('SET', key, cjson.encode(held), 'EX', ttl)
return 1
"""
