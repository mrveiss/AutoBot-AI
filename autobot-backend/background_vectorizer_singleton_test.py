# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The reconciler singleton must actually be constructible (#13277).

``get_background_vectorizer`` returned ``_background_vectorizer()`` — calling the
module global, which is only ever assigned ``None``. Both production callers
(``api/knowledge_vectorization.py``: start a reconcile run, read its status)
therefore raised ``TypeError: 'NoneType' object is not callable``.

The consequence reaches past this module: ``kb:vectorize:pending`` had no
consumer that could be started, so the retry contract of #12312 — and the
recovery path the #13277 repair tool falls back to when a fact cannot be
rebuilt — were both void.

The pre-existing guard at ``api/api_endpoint_migrations_test.py`` only greps
source text for the accessor's name, which is why a decade-simple ``TypeError``
survived. These tests call it.
"""

import threading

import background_vectorization
from background_vectorization import BackgroundVectorizer, get_background_vectorizer


def _reset_singleton():
    background_vectorization._background_vectorizer = None


def test_returns_a_usable_instance():
    _reset_singleton()

    vectorizer = get_background_vectorizer()

    assert isinstance(vectorizer, BackgroundVectorizer)


def test_is_idempotent():
    """Callers share one reconciler — a second instance would double-process."""
    _reset_singleton()

    assert get_background_vectorizer() is get_background_vectorizer()


def test_exposes_the_state_the_status_endpoint_reads():
    _reset_singleton()

    vectorizer = get_background_vectorizer()

    assert vectorizer.is_running is False
    assert vectorizer.last_run is None


def test_concurrent_callers_get_the_same_instance():
    """The accessor is documented thread-safe; hold it to that."""
    _reset_singleton()
    seen = []
    barrier = threading.Barrier(8)

    def grab():
        barrier.wait()
        seen.append(get_background_vectorizer())

    threads = [threading.Thread(target=grab) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(set(id(instance) for instance in seen)) == 1
