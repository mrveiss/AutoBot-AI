---
type: test
scope: backend
issue: 18883
pr: 18933
---
Add `testkit.fake_async_session.FakeAsyncSession`, one fake whose signatures are checked against the installed SQLAlchemy `AsyncSession`, migrate the 38 hand-rolled fake sessions in backend and SLM tests onto it (the approval-claim variant lives in `testkit.fake_approval_session`), and add a ratchet that stops new ones.
