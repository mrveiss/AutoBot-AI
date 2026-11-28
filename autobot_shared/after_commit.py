# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Run a callback only once the caller's transaction commits (#21080).

One ``after_commit`` / ``after_soft_rollback`` hook pair per session: a callback is queued with the
transaction (or SAVEPOINT) that was open when it was asked for, ``after_commit`` runs what is queued,
and a rollback (outer or SAVEPOINT) drops the callbacks of exactly the transaction it undid.

Two delivery modes share this one entry point, ``defer_until_commit``:

* default: the hook pair above. Works on any session, a rollback drops the callback, a plain function runs
  inside the ``after_commit`` hook and a coroutine becomes a task.
* ``scope=True`` (formerly ``db_session.run_after_commit``): the callback is queued once on the list
  ``async_session_scope`` seeds, runs after the whole scope exits, is awaited, and its failures surface as
  ``PostCommitCallbackError``. A session without that list raises ``NoCommitScopeError`` (running at once would
  fire BEFORE the commit). A hook queued inside a rolled-back SAVEPOINT stays queued: over-invalidation, never under.
"""

import asyncio
import inspect
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional, Union

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, SessionTransaction

from autobot_shared.db_session import POST_COMMIT_CALLBACKS, NoCommitScopeError
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

#: A plain function, or one returning a coroutine (run as a task on the running loop).
AfterCommitCallback = Callable[[], Union[None, Awaitable[object]]]

_PENDING_KEY = "llc_after_commit_pending"
_HOOKED_KEY = "llc_after_commit_hooked"
#: Strong references so a spawned task is not collected before it runs.
after_commit_tasks: "set[asyncio.Task[None]]" = set()


#: Asked at commit and at rollback whether the work is still wanted (e.g. its row is still in the session).
StillValid = Callable[[], bool]


@dataclass(frozen=True)
class _Pending:
    callback: AfterCommitCallback
    description: str
    transaction: Optional[SessionTransaction]
    still_valid: Optional[StillValid] = None

    def wanted(self) -> bool:
        """Ask *still_valid*. A predicate that raises is logged and treated as wanted: the commit stands and the
        remaining callbacks still run, so a broken check can neither abort ``commit()`` nor silently drop work."""
        if self.still_valid is None:
            return True
        try:
            return bool(self.still_valid())
        except Exception:
            logger.warning(
                "After-commit still_valid check for %s failed; treating it as wanted", self.description, exc_info=True
            )
            return True


def within_transaction(txn: Optional[SessionTransaction], ancestor: SessionTransaction) -> bool:
    """True when *txn* is *ancestor* or nested (SAVEPOINT) inside it."""
    while txn is not None:
        if txn is ancestor:
            return True
        txn = txn.parent
    return False


async def _await_logged(awaitable: Awaitable[object], description: str) -> None:
    try:
        await awaitable
    except Exception:
        logger.warning("After-commit callback %s failed; the commit already happened", description, exc_info=True)


def _run(callback: AfterCommitCallback, description: str) -> Optional["asyncio.Task[None]"]:
    """Run now. A failure is logged (the commit stands); a coroutine becomes a task, returned."""
    try:
        outcome = callback()
    except Exception:
        logger.warning("After-commit callback %s failed; the commit already happened", description, exc_info=True)
        return None
    if not inspect.isawaitable(outcome):
        return None
    try:
        task = asyncio.get_running_loop().create_task(_await_logged(outcome, description))
    except RuntimeError:
        logger.warning("No event loop to run after-commit callback %s; it is dropped", description)
        getattr(outcome, "close", lambda: None)()
        return None
    after_commit_tasks.add(task)
    task.add_done_callback(after_commit_tasks.discard)
    return task


def _run_committed(sync: Session) -> None:
    """``after_commit``: run each queued callback. Also fires on a SAVEPOINT release, which can still roll back."""
    if sync.in_nested_transaction():
        return
    for pending in sync.info.pop(_PENDING_KEY, []):
        if pending.wanted():
            _run(pending.callback, pending.description)


def _undone_by(pending: _Pending, previous_transaction: SessionTransaction) -> bool:
    """True when rolling back *previous_transaction* undid the work *pending* was queued for.

    A callback queued before the session began a transaction has none recorded: it belongs to the next root
    transaction, so only a root rollback (not a SAVEPOINT) undoes it.
    """
    if pending.transaction is None:
        return previous_transaction.parent is None
    return within_transaction(pending.transaction, previous_transaction)


def _drop_undone(sync: Session, previous_transaction: SessionTransaction) -> None:
    """``after_soft_rollback``: drop the callbacks whose transaction this rollback undid."""
    pending = sync.info.get(_PENDING_KEY, [])
    pending[:] = [p for p in pending if not _undone_by(p, previous_transaction) and p.wanted()]


def _queue_on_scope(session: AsyncSession, callback: AfterCommitCallback) -> None:
    """``scope=True``: queue *callback* once on the list ``async_session_scope`` seeds."""
    queued = session.info.get(POST_COMMIT_CALLBACKS)
    if queued is None:
        raise NoCommitScopeError("no post-commit callback list: open the session with async_session_scope")
    if callback not in queued:
        queued.append(callback)


def defer_until_commit(
    session: AsyncSession,
    callback: AfterCommitCallback,
    description: str = "callback",
    *,
    still_valid: Optional[StillValid] = None,
    scope: bool = False,
) -> Optional["asyncio.Task[None]"]:
    """Queue *callback* until *session* commits; a rollback of its transaction drops it.

    A plain function runs synchronously inside the ``after_commit`` hook, never as a task, so a caller
    that relies on the work having started when ``commit()`` returns can. A function returning a coroutine
    becomes a task. *still_valid*, if given, is checked at commit and after any rollback: when it returns
    False the callback is dropped (e.g. ``lambda: sa_inspect(entry).persistent`` for a row since expunged).

    An object that is not a real SQLAlchemy session has no commit to follow, so it runs at once; the task
    that started, if any, is returned so the caller can await it. Otherwise returns None.

    *scope* selects the scope-list mode described in the module docstring; it ignores *description* and *still_valid*.
    """
    if scope:
        _queue_on_scope(session, callback)
        return None
    sync = getattr(session, "sync_session", None)
    if not isinstance(sync, Session):
        return _run(callback, description)
    if not sync.info.get(_HOOKED_KEY):
        event.listen(sync, "after_commit", _run_committed)
        event.listen(sync, "after_soft_rollback", _drop_undone)
        sync.info[_HOOKED_KEY] = True
    txn = sync.get_nested_transaction() or sync.get_transaction()
    sync.info.setdefault(_PENDING_KEY, []).append(_Pending(callback, description, txn, still_valid))
    return None
