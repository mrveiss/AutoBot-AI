# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#13280 — the *writer* behind the ``"metadata": null`` class fixed by #13220.

``_build_message_dict`` wrote ``"metadata": raw_data`` and ``add_message``
declares ``raw_data: Any = None``, so every message added without metadata was
persisted with an explicit ``null`` (8 of 12 on the live session in #13220).
#13220 taught the two readers to survive it; this closes the producer.

Deliberately **not** done here, and asserted as such below:

- the #13220 reader guards stay. Sessions already on disk are not rewritten, so
  ``"metadata": null`` remains readable forever. A defence against historical
  data is not dead code because the writer stopped producing the shape.
- falsy-but-present metadata (``0``, ``""``, ``[]``) is preserved rather than
  normalised away — ``is not None``, not a truthiness test.

Frontend audit (#13280 scope item 1), read-only, against ``autobot-frontend``:
``useChatStore.ts`` ``findMessageByMetadata`` has the one truthiness guard that
flips (``if (!msg.metadata) return false``), and it reaches the same verdict for
every non-empty criteria object. ``ChatRepository.ts``'s
``msg.metadata || msg.rawData || {}`` is keyed on the legacy ``rawData`` field,
which the current writer never emits beside a freshly built message, so a newly
written ``{}`` cannot shadow it. ``MessageItem.vue`` already length-checks.
No frontend change is required.
"""

import asyncio
from typing import Any, Dict, List

import pytest

from chat_history.messages import MessagesMixin


class _RecordingHistory(MessagesMixin):
    """Exercises the real message mixin against an in-memory session store."""

    def __init__(self) -> None:
        self.history: List[Dict[str, Any]] = []
        self.sessions: Dict[str, List[Dict[str, Any]]] = {}
        self.announced: List[Dict[str, Any]] = []

    async def load_session(self, session_id: str) -> List[Dict[str, Any]]:
        return self.sessions.get(session_id, [])

    async def save_session(self, session_id: str, messages: List[Dict[str, Any]], **_: Any) -> bool:
        self.sessions[session_id] = messages
        return True

    async def _announce_message(self, session_id: str, message: Dict[str, Any]) -> None:
        """Record the announcement instead of publishing it.

        The real one defers an import of ``api.session_events`` and awaits
        ``publish_chat_message``. It swallows its own failures, so it cannot fail
        this test — but it does make a *writer* test reach into the API layer, and
        ``announced`` existed for this and was never populated.
        """
        self.announced.append({"session_id": session_id, "message": message})

    async def _save_history(self) -> None:
        return None

    def _periodic_memory_check(self) -> None:
        return None


class TestWriterNeverPersistsNull:
    def test_build_message_dict_defaults_metadata_to_a_mapping(self) -> None:
        message = _RecordingHistory()._build_message_dict("user", "hi", "default", None, None)

        assert message["metadata"] is not None, "the writer still persists metadata: null (#13280)"
        assert message["metadata"] == {}

    def test_add_message_persists_a_mapping_into_the_session(self) -> None:
        manager = _RecordingHistory()

        asyncio.run(manager.add_message(sender="user", text="hi", session_id="s1"))

        [stored] = manager.sessions["s1"]
        assert stored["metadata"] == {}
        assert stored["metadata"] is not None

    def test_add_message_to_default_history_persists_a_mapping(self) -> None:
        """The ``session_id=None`` branch is a second writer path, not the same one."""
        manager = _RecordingHistory()

        asyncio.run(manager.add_message(sender="user", text="hi"))

        assert manager.history[0]["metadata"] == {}

    @pytest.mark.parametrize("falsy", [0, "", [], False, {}])
    def test_falsy_but_supplied_metadata_survives_verbatim(self, falsy: Any) -> None:
        """A truthiness test here would silently discard metadata a caller passed."""
        message = _RecordingHistory()._build_message_dict("user", "hi", "default", falsy, None)

        assert message["metadata"] is falsy

    def test_supplied_metadata_is_passed_through_unchanged(self) -> None:
        payload = {"requires_approval": True, "terminal_session_id": "term-1"}

        message = _RecordingHistory()._build_message_dict("user", "hi", "default", payload, None)

        assert message["metadata"] == payload


class TestHistoricalNullsStillRead:
    """The #13220 reader defences must survive the writer fix (#13280 scope item 4).

    These are not duplicates of ``metadata_null_guard_test.py``: that module
    pins #13220's behaviour, this one pins that #13280 did **not** take the
    defences with it on the way past.
    """

    def test_filter_still_tolerates_a_historical_null(self) -> None:
        historical = {"id": "x", "sender": "user", "text": "old", "metadata": None}

        assert _RecordingHistory()._message_matches_filter(historical, {"requires_approval": True}) is False

    def test_update_still_tolerates_a_historical_null(self) -> None:
        historical = {"id": "x", "sender": "user", "text": "old", "metadata": None}

        _RecordingHistory()._apply_metadata_updates(historical, {"approval_status": "approved"})

        assert historical["metadata"] == {"approval_status": "approved"}
