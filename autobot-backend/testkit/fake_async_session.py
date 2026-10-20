# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One fake ``AsyncSession``, instead of thirty-odd hand-rolled ones (#18883).

Tests across both backends each wrote their own ``_Session`` with ``commit`` and ``refresh``.
They drifted from the real class: five lacked ``attribute_names`` on ``refresh``, five made it
keyword-only (the real one is positional-or-keyword), and one took ``with_for_update`` on
``get`` positionally (the real one is keyword-only). A fake whose signature differs from the
real session accepts calls the production code can never make, and rejects ones it does.

Rules:

1. **Signatures copy ``sqlalchemy.ext.asyncio.AsyncSession``** -- names, kinds and order.
   ``fake_async_session_test.py`` compares them with ``inspect.signature`` against the
   installed SQLAlchemy, so a SQLAlchemy upgrade that moves a parameter fails there.
2. **Recording is always on** (``added``, ``deleted``, ``statements``, ``refreshed`` and the
   commit/flush/rollback counts); behaviour is opt-in through the constructor. A test that
   passes nothing gets a harmless session that remembers what it was asked.
3. **No SQL is interpreted.** Statements are recorded and answered from ``results``; to test
   a real query, use a real session.

Usage::

    from testkit.fake_async_session import FakeAsyncSession, FakeResult

    session = FakeAsyncSession(assign_ids=True, results=[FakeResult([row])])
    await service.create(session, payload)
    assert session.added and session.commits == 1
"""

from __future__ import annotations

import itertools
from collections import deque
from typing import Any, Callable, Iterable, Optional

from sqlalchemy.exc import InvalidRequestError

from testkit.fake_result import FakeResult

__all__ = ["FakeAsyncSession", "FakeResult", "ResultsExhausted"]


class ResultsExhausted(AssertionError):
    """``strict=True`` and ``execute`` was called with the ``results`` queue empty."""


class _FakeTransaction:
    """What ``begin`` / ``begin_nested`` return, with a real transaction's exit semantics.

    ``begin()``: a clean exit calls the session's ``commit``; an exception calls its ``rollback``.
    ``begin_nested()`` is a SAVEPOINT: a clean exit ``flush``es (the outer transaction still owns
    the commit); an exception undoes only the work done since the savepoint opened (objects added,
    flushed or deleted inside it) and counts as one ``rollbacks``. Neither suppresses the exception.
    An explicit ``commit()`` / ``rollback()`` ends the transaction, so ``__aexit__`` then does nothing.
    """

    def __init__(self, session: "FakeAsyncSession", nested: bool = False) -> None:
        self._session = session
        self._nested = nested
        self._done = False
        self._marks: tuple = (0, 0, 0, 0)

    def __await__(self):
        """``await session.begin_nested()`` starts the transaction too, as on a real AsyncSession."""
        return self.__aenter__().__await__()

    async def __aenter__(self) -> "_FakeTransaction":
        if self._nested:
            # A real Session.begin_nested() flushes pending state before the SAVEPOINT, so outer
            # work survives a savepoint rollback and the marks can't be undercut by an expunge.
            await self._session.flush()
        self._marks = self._session._marks()
        return self

    async def __aexit__(self, type_: Any, value: Any, traceback: Any) -> bool:
        if not self._done:
            if type_ is None:
                await self.commit()
            else:
                await self.rollback()
        return False

    async def commit(self) -> None:
        self._done = True
        await (self._session.flush() if self._nested else self._session.commit())

    async def rollback(self) -> None:
        self._done = True
        if self._nested:
            self._session._undo_to(self._marks)
            self._session.rollbacks += 1
        else:
            await self._session.rollback()


def _as_result(item: Any, stmt: Any) -> FakeResult:
    """Turn one queued answer (result, rows or callable) into a ``FakeResult``."""
    if isinstance(item, BaseException):
        raise item
    if callable(item) and not isinstance(item, FakeResult):
        item = item(stmt)
    if isinstance(item, FakeResult):
        return item
    return FakeResult(list(item) if item is not None else [])


class FakeAsyncSession:
    """Records every call; answers ``execute`` / ``get`` / ``commit`` only as told to.

    Unit of work, as on a real session: ``add`` makes an object *pending* and ``get`` does not
    see it; ``flush`` / ``commit`` register it in ``rows`` (the identity map ``get`` reads).
    ``delete`` is likewise deferred to the flush. ``rollback`` drops pending work, un-registers
    what this transaction flushed and restores what it deleted. ``refresh`` / ``delete`` of an
    object the session never persisted (neither pending-then-flushed, in ``rows``, nor returned
    by ``get`` / ``execute``) raise ``InvalidRequestError``.
    """

    def __init__(
        self,
        *,
        # True numbers new objects 1, 2, ...; a zero-argument callable (e.g. ``uuid.uuid4``) mints each id.
        assign_ids: Any = False,
        results: Optional[Iterable[Any]] = None,
        default_result: Any = None,
        rows: Optional[dict] = None,
        commit_error: Any = None,
        on_refresh: Optional[Callable[[Any], None]] = None,
        on_get: Optional[Callable[[Any, Any], Any]] = None,
        # True: ``execute`` raises ``ResultsExhausted`` once ``results`` is empty, not ``default_result``.
        strict: bool = False,
    ) -> None:
        self.assign_ids = assign_ids
        self.results: deque = deque(results or ())
        self.default_result = default_result
        self.rows: dict = {} if rows is None else rows
        self.commit_error = commit_error
        self.on_refresh = on_refresh
        self.on_get = on_get
        self.strict = strict
        self.added: list = []
        self.deleted: list = []
        self._pending: list = []  # added, not yet flushed
        self._pending_deletes: list = []  # deleted, not yet flushed
        self._flushed: list = []  # registered by a flush of the open transaction
        self._removed: list = []  # (key, instance) removed by a flush of the open transaction
        self._known: dict = {}  # id(obj) -> obj the session has persisted or loaded
        self.statements: list = []
        self.refreshed: list = []
        self.commits = 0
        self.flushes = 0
        self.rollbacks = 0
        self.closed = False
        self._last_commit_failed = False
        self._ids = itertools.count(1)

    @property
    def committed(self) -> bool:
        """True once a commit has succeeded."""
        return self.commits > 0 and not self._last_commit_failed

    def _is_persistent(self, instance: object) -> bool:
        return id(instance) in self._known or any(row is instance for row in self.rows.values())

    def _mint_id(self, instance: object) -> None:
        if self.assign_ids and getattr(instance, "id", None) is None:
            make = self.assign_ids if callable(self.assign_ids) else self._ids.__next__
            instance.id = make()

    def _persist(self, instance: object) -> None:
        """Flush one pending object: mint its id and register it in the identity map."""
        self._mint_id(instance)
        self._known[id(instance)] = instance
        pk = getattr(instance, "id", None)
        if pk is not None:
            self.rows[(type(instance), pk)] = instance
            self._flushed.append(((type(instance), pk), instance))

    def _loaded(self, instance: Any) -> Any:
        if instance is not None:
            self._known[id(instance)] = instance
        return instance

    def _marks(self) -> tuple:
        return (len(self._pending), len(self._pending_deletes), len(self._flushed), len(self._removed))

    def _undo_to(self, marks: tuple) -> None:
        """Undo the pending/flushed/deleted work recorded after *marks* (a savepoint rollback)."""
        pending, pending_deletes, flushed, removed = marks
        del self._pending[pending:]
        del self._pending_deletes[pending_deletes:]
        for key, instance in reversed(self._flushed[flushed:]):
            if self.rows.get(key) is instance:
                del self.rows[key]
            self._known.pop(id(instance), None)
        del self._flushed[flushed:]
        for key, instance in reversed(self._removed[removed:]):
            self.rows[key] = instance
            self._known[id(instance)] = instance
        del self._removed[removed:]

    def add(self, instance: object, _warn: bool = True) -> None:
        self.added.append(instance)
        if not self._is_persistent(instance) and not any(p is instance for p in self._pending):
            self._pending.append(instance)

    def add_all(self, instances: Iterable[object]) -> None:
        for instance in instances:
            self.add(instance)

    async def flush(self, objects: Optional[Iterable[Any]] = None) -> None:
        self.flushes += 1
        pending, self._pending = self._pending, []
        for instance in pending:
            self._persist(instance)
        doomed, self._pending_deletes = self._pending_deletes, []
        for instance in doomed:
            for key in self._drop_rows(instance):
                self._removed.append((key, instance))
            self._known.pop(id(instance), None)

    def _drop_rows(self, instance: object) -> list:
        """Remove every identity-map entry holding *instance* (by identity, whatever its key) and return the keys."""
        keys = [key for key, row in self.rows.items() if row is instance]
        for key in keys:
            del self.rows[key]
        return keys

    def _commit_failure(self) -> Optional[BaseException]:
        err = self.commit_error
        if callable(err) and not isinstance(err, BaseException):
            err = err(self.commits)
        return err

    async def commit(self) -> None:
        self.commits += 1
        err = self._commit_failure()
        self._last_commit_failed = err is not None
        if err is not None:
            raise err
        await self.flush()
        self._flushed.clear()
        self._removed.clear()

    async def rollback(self) -> None:
        self.rollbacks += 1
        self._undo_to((0, 0, 0, 0))

    async def close(self) -> None:
        self.closed = True

    async def refresh(
        self,
        instance: object,
        attribute_names: Optional[Iterable[str]] = None,
        with_for_update: Any = None,
    ) -> None:
        if not self._is_persistent(instance):
            raise InvalidRequestError(f"Instance '{instance!r}' is not persistent within this Session")
        self.refreshed.append(instance)
        if self.on_refresh is not None:
            self.on_refresh(instance)

    async def execute(
        self,
        statement: Any,
        params: Any = None,
        *,
        execution_options: Any = None,
        bind_arguments: Any = None,
        **kw: Any,
    ) -> FakeResult:
        self.statements.append(statement)
        if self.results:
            result = _as_result(self.results.popleft(), statement)
        elif self.strict:
            raise ResultsExhausted(f"execute() #{len(self.statements)} has no queued result (strict=True)")
        else:
            result = _as_result(self.default_result, statement)
        for loaded in result.all():
            self._loaded(loaded)
        return result

    async def scalar(
        self,
        statement: Any,
        params: Any = None,
        *,
        execution_options: Any = None,
        bind_arguments: Any = None,
        **kw: Any,
    ) -> Any:
        result = await self.execute(
            statement, params, execution_options=execution_options, bind_arguments=bind_arguments, **kw
        )
        return result.scalar()

    async def scalars(
        self,
        statement: Any,
        params: Any = None,
        *,
        execution_options: Any = None,
        bind_arguments: Any = None,
        **kw: Any,
    ) -> Any:
        result = await self.execute(
            statement, params, execution_options=execution_options, bind_arguments=bind_arguments, **kw
        )
        return result.scalars()

    async def get(
        self,
        entity: Any,
        ident: Any,
        *,
        options: Any = None,
        populate_existing: bool = False,
        with_for_update: Any = None,
        identity_token: Any = None,
        execution_options: Any = None,
    ) -> Any:
        """Identity-map hit first, then ``on_get(entity, ident)``, else ``None``."""
        if (entity, ident) in self.rows:
            return self.rows[(entity, ident)]
        return self._loaded(self.on_get(entity, ident)) if self.on_get is not None else None

    async def delete(self, instance: object) -> None:
        """Queue *instance* for removal at the next flush; ``get`` still returns it until then."""
        if not self._is_persistent(instance):
            raise InvalidRequestError(f"Instance '{instance!r}' is not persisted")
        self.deleted.append(instance)
        self._pending_deletes.append(instance)

    async def merge(self, instance: Any, *, load: bool = True, options: Any = None) -> Any:
        self.add(instance)
        return instance

    def expunge(self, instance: object) -> None:
        """Detach *instance*: an expunged pending object is transient, so no later flush registers it."""
        self._drop_rows(instance)
        self._known.pop(id(instance), None)
        self._pending = [p for p in self._pending if p is not instance]
        self._pending_deletes = [p for p in self._pending_deletes if p is not instance]

    def begin(self) -> _FakeTransaction:
        return _FakeTransaction(self)

    def begin_nested(self) -> _FakeTransaction:
        return _FakeTransaction(self, nested=True)

    async def __aenter__(self) -> "FakeAsyncSession":
        return self

    async def __aexit__(self, type_: Any, value: Any, traceback: Any) -> None:
        await self.close()
