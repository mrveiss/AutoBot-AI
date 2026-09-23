---
type: fix
scope: ci
issue: 16516
pr: 0000
---
Every python-suite shard now runs pytest with a `faulthandler_timeout` taken from one setting on the shard job, so a test that hangs dumps every thread's traceback into the log, naming the test and the frame it blocks in, instead of printing nothing until the one-hour job limit.
