# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression tests for the memory-privacy IDOR + workspace-shell CSWSH fixes.

Covers the background-security-review findings:
- arbitrary Redis key deletion via caller-supplied ``memory_id``
- fail-open ownership checks (non-dict value / missing owner)
- Cross-Site WebSocket Hijacking (missing Origin validation)
"""

import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from memory.working_memory import is_working_memory_key

_VALID_KEY = "autobot:session:sess123:memory:note1"


class WorkingMemoryKeyShapeTests(unittest.TestCase):
    def test_accepts_canonical_working_memory_key(self):
        self.assertTrue(is_working_memory_key(_VALID_KEY))

    def test_rejects_arbitrary_keys(self):
        for bad in ("", "some:other:key", "autobot:session:x", "memory:entity:1", None, 123):
            self.assertFalse(is_working_memory_key(bad))


class ForgetWorkingMemoryTests(unittest.IsolatedAsyncioTestCase):
    def _redis(self, raw):
        r = AsyncMock()
        r.get = AsyncMock(return_value=raw)
        r.delete = AsyncMock(return_value=1)
        return r

    async def _call(self, memory_id, raw, user_id="alice"):
        import memory.transparency as mt

        redis = self._redis(raw)
        with (
            patch.object(mt, "_bootstrap", lambda: None),
            patch.object(mt, "get_redis_client", AsyncMock(return_value=redis)),
        ):
            result = await mt._forget_working_memory(user_id, memory_id)
        return result, redis

    async def test_rejects_non_working_memory_key_without_touching_redis(self):
        result, redis = await self._call("attacker:supplied:key", json.dumps({"user_id": "alice"}))
        self.assertFalse(result)
        redis.get.assert_not_called()
        redis.delete.assert_not_called()

    async def test_non_dict_value_is_denied_fail_closed(self):
        # A plain string payload must NOT be deletable (previously fail-open).
        result, redis = await self._call(_VALID_KEY, json.dumps("just-a-string"))
        self.assertFalse(result)
        redis.delete.assert_not_called()

    async def test_tenant_mismatch_denied(self):
        result, redis = await self._call(_VALID_KEY, json.dumps({"user_id": "bob"}))
        self.assertFalse(result)
        redis.delete.assert_not_called()

    async def test_owner_can_delete(self):
        result, redis = await self._call(_VALID_KEY, json.dumps({"user_id": "alice"}))
        self.assertTrue(result)
        redis.delete.assert_awaited_once_with(_VALID_KEY)


class ForgetGraphEntityTests(unittest.IsolatedAsyncioTestCase):
    async def _call(self, meta, user_id="alice"):
        import memory.transparency as mt

        redis = MagicMock()
        redis.json.return_value.get = AsyncMock(return_value={"metadata": meta})
        redis.delete = AsyncMock(return_value=1)
        with (
            patch.object(mt, "_bootstrap", lambda: None),
            patch.object(mt, "get_redis_client", AsyncMock(return_value=redis)),
        ):
            result = await mt._forget_graph_entity(user_id, "ent1")
        return result, redis

    async def test_missing_owner_is_denied_by_default(self):
        result, redis = await self._call({})  # no user_id / owner_id
        self.assertFalse(result)
        redis.delete.assert_not_called()

    async def test_owner_mismatch_denied(self):
        result, redis = await self._call({"user_id": "bob"})
        self.assertFalse(result)
        redis.delete.assert_not_called()

    async def test_owner_match_deletes(self):
        result, redis = await self._call({"user_id": "alice"})
        self.assertTrue(result)


class ValidateWsOriginTests(unittest.TestCase):
    def _ws(self, headers):
        ws = MagicMock()
        ws.headers = headers
        return ws

    def test_disallowed_origin_rejected(self):
        from api.task_workspace_ws import _validate_ws_origin

        ws = self._ws({"origin": "https://evil.example", "authorization": "Bearer x"})
        with patch("config.manager.get_config_manager") as gcm:
            gcm.return_value.get_cors_origins.return_value = ["https://app.internal"]
            with self.assertRaises(PermissionError):
                _validate_ws_origin(ws)

    def test_allowlisted_origin_passes(self):
        from api.task_workspace_ws import _validate_ws_origin

        ws = self._ws({"origin": "https://app.internal"})
        with patch("config.manager.get_config_manager") as gcm:
            gcm.return_value.get_cors_origins.return_value = ["https://app.internal"]
            _validate_ws_origin(ws)  # no raise

    def test_absent_origin_non_browser_passes(self):
        from api.task_workspace_ws import _validate_ws_origin

        _validate_ws_origin(self._ws({}))  # no raise — Origin-only, no auth precondition

    def test_origin_check_no_longer_requires_authorization_header(self):
        """#11016: an allowlisted same-origin client with NO Authorization header
        must pass the Origin gate (auth is decided by _authenticate_ws_admin), so
        cookie-authenticated admins are no longer locked out."""
        from api.task_workspace_ws import _validate_ws_origin

        ws = self._ws({"origin": "https://app.internal"})  # no 'authorization'
        with (
            patch.dict("os.environ", {"AUTOBOT_REQUIRE_WS_AUTH": "1"}),
            patch("config.manager.get_config_manager") as gcm,
        ):
            gcm.return_value.get_cors_origins.return_value = ["https://app.internal"]
            _validate_ws_origin(ws)  # no raise


if __name__ == "__main__":
    unittest.main()
