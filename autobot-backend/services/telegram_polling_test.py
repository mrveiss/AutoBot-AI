# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the Telegram polling ingest (#19010).

Covers the three properties the issue asks for: the offset survives a restart
(so nothing is answered twice), the mode switch leaves exactly one ingest live,
and polled updates go through the same ``process_telegram_update`` as the
webhook.
"""

import asyncio
import importlib
from types import SimpleNamespace

import pytest

from services import telegram_polling as tp


class FakeRedis:
    """Minimal async Redis: a dict that outlives any one poller, like the real store."""

    def __init__(self) -> None:
        self.data: dict = {}

    async def get(self, key):
        return self.data.get(key)

    async def set(self, key, value):
        self.data[key] = str(value).encode("utf-8")


def _update(update_id: int) -> dict:
    return {"update_id": update_id, "message": {"message_id": update_id, "chat": {"id": 1}, "text": "hi"}}


@pytest.fixture
def harness(monkeypatch):
    redis = FakeRedis()
    state = SimpleNamespace(offsets=[], routed=[], batches=[], token="111:secret-a", limits=[])

    async def fake_redis(**kwargs):
        assert kwargs.get("async_client") is True, "an awaited client must be the async one"
        return redis

    async def fake_from_redis():
        return SimpleNamespace(bot_token=state.token, base_url="https://api.telegram.org/bott")

    async def fake_fetch(service, offset, limit=100):
        state.offsets.append(offset)
        state.limits.append(limit)
        return state.batches.pop(0) if state.batches else []

    async def fake_process(app, update):
        state.routed.append(update["update_id"])

    monkeypatch.setattr(tp, "get_redis_client", fake_redis)
    monkeypatch.setattr(tp.TelegramBotService, "from_redis", staticmethod(fake_from_redis))
    monkeypatch.setattr(tp, "fetch_updates", fake_fetch)
    monkeypatch.setattr("api.telegram_bot.process_telegram_update", fake_process)
    state.redis = redis
    return state


async def _drain(app) -> None:
    await asyncio.gather(*list(app.state.telegram_update_tasks))


class TestOffsetPersistence:
    @pytest.mark.asyncio
    async def test_restart_resumes_after_last_dispatched_update(self, harness):
        await tp.save_ingest_mode(tp.INGEST_MODE_POLLING)
        harness.batches = [[_update(7), _update(8)], []]

        first_app = SimpleNamespace(state=SimpleNamespace())
        assert await tp.poll_once(first_app) == 2
        await _drain(first_app)

        # A fresh app is a restarted backend; only Redis carries over.
        assert await tp.poll_once(SimpleNamespace(state=SimpleNamespace())) == 0
        assert harness.offsets == [0, 9]
        assert harness.routed == [7, 8]


class TestBackpressure:
    @pytest.mark.asyncio
    async def test_full_queue_fetches_nothing_and_holds_the_offset(self, harness, monkeypatch):
        monkeypatch.setattr(tp, "MAX_PENDING_REPLIES", 3)
        await tp.save_ingest_mode(tp.INGEST_MODE_POLLING)
        gate = asyncio.Event()

        async def slow_process(app, update):
            await gate.wait()

        monkeypatch.setattr("api.telegram_bot.process_telegram_update", slow_process)
        # Telegram over-delivers: the poller still queues only what fits.
        harness.batches = [[_update(1), _update(2), _update(3), _update(4)], [_update(5)]]
        app = SimpleNamespace(state=SimpleNamespace())
        assert await tp.poll_once(app) == 3
        assert harness.limits == [3]
        offset_after_first = await harness.redis.get(tp.offset_key(harness.token))
        assert offset_after_first == b"4"  # update 4 was never queued, so it is not confirmed

        assert await tp.poll_once(app) == 0  # full: no getUpdates at all
        assert harness.offsets == [0]
        assert await harness.redis.get(tp.offset_key(harness.token)) == offset_after_first

        gate.set()
        await _drain(app)
        assert await tp.poll_once(app) == 1
        assert harness.offsets == [0, 4] and harness.limits == [3, 3]
        await _drain(app)


class TestOffsetIsPerBot:
    @pytest.mark.asyncio
    async def test_token_swap_starts_from_the_new_bots_own_offset(self, harness):
        await tp.save_ingest_mode(tp.INGEST_MODE_POLLING)
        harness.batches = [[_update(500)], [_update(3)], []]
        for token in ("111:secret-a", "222:secret-b", "111:secret-a"):
            harness.token = token
            app = SimpleNamespace(state=SimpleNamespace())
            await tp.poll_once(app)
            await _drain(app)
        # Bot 222 never inherits bot 111's offset 501; bot 111 resumes at its own.
        assert harness.offsets == [0, 0, 501]
        harness.token = "222:secret-b"
        await tp.poll_once(SimpleNamespace(state=SimpleNamespace()))
        assert harness.offsets[-1] == 4

    def test_key_carries_the_public_bot_id_never_the_secret(self):
        assert tp.offset_key("123456:ABC-secret") == f"{tp.TELEGRAM_POLL_OFFSET_KEY}:123456"
        odd = tp.offset_key("not-a-bot-token")
        assert "not-a-bot-token" not in odd and odd != tp.offset_key("other-token")


class TestHttpBudgetFitsTheLease:
    @pytest.fixture
    def reload_with_env(self, monkeypatch):
        def _reload(**env):
            for name, value in env.items():
                monkeypatch.setenv(name, value)
            return importlib.reload(tp)

        yield _reload
        monkeypatch.undo()
        importlib.reload(tp)

    @pytest.mark.parametrize("margin,slack", [("1", "1"), ("1", "100"), ("100", "100"), ("5", "5")])
    def test_total_timeout_ends_inside_the_lease_at_the_cap(self, reload_with_env, margin, slack):
        mod = reload_with_env(
            AUTOBOT_TELEGRAM_POLL_TIMEOUT_SECONDS="100000",
            AUTOBOT_TELEGRAM_POLL_LEASE_MARGIN_SECONDS=margin,
            AUTOBOT_TELEGRAM_POLL_HTTP_SLACK_SECONDS=slack,
        )
        lease_s = mod.DEFAULT_TTL_MS / 1000
        assert mod._POLL_HTTP_TIMEOUT.total <= lease_s - mod._LEASE_MARGIN_S < lease_s
        assert mod._POLL_HTTP_TIMEOUT.sock_read <= mod._POLL_HTTP_TIMEOUT.total
        assert mod.POLL_TIMEOUT_S < mod._POLL_HTTP_TIMEOUT.total


class TestModeSwitch:
    @pytest.mark.asyncio
    async def test_webhook_mode_never_polls(self, harness):
        await tp.save_ingest_mode(tp.INGEST_MODE_WEBHOOK)
        harness.batches = [[_update(1)]]

        assert await tp.poll_once(SimpleNamespace(state=SimpleNamespace())) is None
        assert harness.offsets == []

    @pytest.mark.asyncio
    async def test_unset_mode_defaults_to_webhook(self, harness):
        assert await tp.get_ingest_mode() == tp.INGEST_MODE_WEBHOOK

    @pytest.mark.asyncio
    async def test_unknown_mode_is_rejected(self, harness):
        with pytest.raises(ValueError):
            await tp.save_ingest_mode("both")

    @pytest.mark.asyncio
    async def test_selecting_polling_deletes_webhook(self, harness, monkeypatch):
        from api import telegram_bot as tg
        from api.schemas_telegram import TelegramBotConfigRequest

        calls: list = []

        async def fake_delete(service):
            calls.append("deleteWebhook")

        async def fake_set(url, secret):
            calls.append("setWebhook")

        monkeypatch.setattr(tg, "delete_webhook", fake_delete)
        service = SimpleNamespace(set_webhook=fake_set)
        req = TelegramBotConfigRequest(bot_token="t", ingest_mode="polling")

        assert await tg._apply_ingest_mode(service, req) is None
        assert calls == ["deleteWebhook"]
        assert await tp.get_ingest_mode() == tp.INGEST_MODE_POLLING

    def test_polling_request_with_webhook_url_is_invalid(self):
        from pydantic import ValidationError

        from api.schemas_telegram import TelegramBotConfigRequest

        with pytest.raises(ValidationError):
            TelegramBotConfigRequest(bot_token="t", ingest_mode="polling", webhook_url="https://x.example")


class TestSharedRoutingPath:
    @pytest.mark.asyncio
    async def test_webhook_and_poller_share_process_telegram_update(self, monkeypatch):
        """The webhook delegates to the function the poller dispatches -- one path."""
        from api import telegram_bot as tg

        seen: list = []

        async def fake_process(app, update):
            seen.append((app, update))

        monkeypatch.setattr(tg, "process_telegram_update", fake_process)
        app = SimpleNamespace(state=SimpleNamespace())
        request = SimpleNamespace(app=app)

        await tg.telegram_webhook(request=request, update=_update(3))
        tp._dispatcher_for(app).submit(app, _update(4))
        await _drain(app)

        assert [u["update_id"] for _, u in seen] == [3, 4]
        assert all(a is app for a, _ in seen)


class TestTokenNeverLogged:
    @pytest.mark.asyncio
    async def test_transport_error_drops_the_tokenised_url(self, monkeypatch):
        """aiohttp errors embed the URL, which embeds the token -- it must not propagate."""
        import contextlib

        import aiohttp

        token = "123:SECRET"

        @contextlib.asynccontextmanager
        async def boom(method, url, **kwargs):
            raise aiohttp.InvalidURL(url)
            yield  # pragma: no cover

        monkeypatch.setattr(tp, "get_http_client", lambda: SimpleNamespace(tracked_request=boom))
        service = tp.TelegramBotService(bot_token=token)

        with pytest.raises(RuntimeError) as err:
            await tp.fetch_updates(service, 0)
        assert token not in str(err.value)
        assert err.value.__cause__ is None


class TestReplyDispatcher:
    @pytest.mark.asyncio
    async def test_one_chat_is_answered_in_order_and_concurrency_is_capped(self, monkeypatch):
        live = {"now": 0, "peak": 0}
        order: list = []

        async def slow_process(app, update):
            live["now"] += 1
            live["peak"] = max(live["peak"], live["now"])
            await asyncio.sleep(0.01 if update["update_id"] % 2 else 0.02)
            order.append(update["update_id"])
            live["now"] -= 1

        monkeypatch.setattr("api.telegram_bot.process_telegram_update", slow_process)
        app = SimpleNamespace(state=SimpleNamespace())
        dispatcher = tp._ReplyDispatcher(limit=2)
        app.state.telegram_update_tasks = dispatcher.tasks
        same_chat = [_update(i) for i in (10, 11, 12)]
        other_chats = [{"update_id": 20 + i, "message": {"chat": {"id": 100 + i}}} for i in range(3)]
        for update in same_chat + other_chats:
            dispatcher.submit(app, update)
        await _drain(app)

        assert [u for u in order if u < 20] == [10, 11, 12]
        assert live["peak"] <= 2
        assert dispatcher._chats == {}

    @pytest.mark.asyncio
    async def test_a_failing_reply_is_logged_not_raised(self, monkeypatch):
        async def broken(app, update):
            raise RuntimeError("llm down")

        monkeypatch.setattr("api.telegram_bot.process_telegram_update", broken)
        app = SimpleNamespace(state=SimpleNamespace())
        tp._dispatcher_for(app).submit(app, _update(1))
        results = await asyncio.gather(*list(app.state.telegram_update_tasks), return_exceptions=True)
        assert results == [None]


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_start_runs_the_lease_and_cancel_releases_it(self, monkeypatch):
        events: list = []

        class FakeLease:
            def __init__(self, **kwargs):
                events.append(("init", kwargs["key"]))

            async def run(self, on_tick=None):
                events.append("run")
                await asyncio.Event().wait()

            async def release(self):
                events.append("release")

        monkeypatch.setattr(tp, "LeaderLease", FakeLease)
        app = SimpleNamespace(state=SimpleNamespace())
        await tp.start_polling(app)
        await asyncio.sleep(0)
        app.state.telegram_poller_task.cancel()
        await asyncio.gather(app.state.telegram_poller_task, return_exceptions=True)

        assert events == [("init", tp.TELEGRAM_POLL_LEASE_KEY), "run", "release"]

    @pytest.mark.asyncio
    async def test_idle_tick_waits_instead_of_spinning(self, harness, monkeypatch):
        await tp.save_ingest_mode(tp.INGEST_MODE_WEBHOOK)
        slept: list = []
        ticks: list = []

        class OneTickLease:
            def __init__(self, **kwargs):
                pass

            async def run(self, on_tick=None):
                ticks.append(on_tick)

            async def release(self):
                pass

        async def fake_sleep(seconds):
            slept.append(seconds)

        monkeypatch.setattr(tp, "LeaderLease", OneTickLease)
        app = SimpleNamespace(state=SimpleNamespace())
        await tp.start_polling(app)
        await app.state.telegram_poller_task
        monkeypatch.setattr(tp.asyncio, "sleep", fake_sleep)
        await ticks[0]()

        assert slept == [tp.POLL_IDLE_S]


class TestTokenNotInLeaseLog:
    @pytest.mark.asyncio
    async def test_lease_loop_log_carries_no_token(self, monkeypatch):
        """End to end: a failing getUpdates, logged by LeaderLease.run, shows no token."""
        import contextlib
        import logging

        import aiohttp

        from autobot_shared import leader_lease

        token = "123:SECRET"
        records: list = []

        class Capture(logging.Handler):
            def emit(self, record):
                records.append(record.getMessage())

        @contextlib.asynccontextmanager
        async def boom(method, url, **kwargs):
            raise aiohttp.InvalidURL(url)
            yield  # pragma: no cover

        monkeypatch.setattr(tp, "get_http_client", lambda: SimpleNamespace(tracked_request=boom))
        service = tp.TelegramBotService(bot_token=token)
        lease = leader_lease.LeaderLease(key="k", label="telegram-poller")

        async def leader(*args, **kwargs):
            lease._is_leader = True
            return True

        async def stop(seconds):
            raise asyncio.CancelledError

        monkeypatch.setattr(lease, "update_leadership", leader)
        monkeypatch.setattr(leader_lease.asyncio, "sleep", stop)
        handler = Capture()
        leader_lease.logger.addHandler(handler)
        try:
            # The loop's back-off sleep is the patched one, so it exits by cancellation.
            with contextlib.suppress(asyncio.CancelledError):
                await lease.run(on_tick=lambda: tp.fetch_updates(service, 0))
        finally:
            leader_lease.logger.removeHandler(handler)

        assert records and all(token not in r for r in records)
