---
type: fix
scope: backend
issue: 17017
pr: 0000
---
The Operations panel now works. Every status and list request used to fail, because the backend handed back an operation lookup it had not awaited and then converted it into a shape the panel does not read. Starting a comprehensive test run creates an operation again and records who started it. A signed-in user sees, cancels and resumes their own operations, and an administrator sees everyone's. Codebase indexing, knowledge-base population and security scans are not yet backed by a working long-running operation. They now answer 501 Not Implemented instead of failing or reporting success without doing anything, and are tracked in #17023.
