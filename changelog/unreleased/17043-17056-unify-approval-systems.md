---
type: refactor
scope: backend
issue: 17043
pr: 0000
---
The platform-general and LLC company-scoped approval systems are unified onto one `approvals` table (`company_id` NULL = platform-general, set = LLC), with every existing `llc_approvals` row copied across by migration; `llc/services/approval.py` now reads and writes the unified table, and an approval-gate comment's `author_type` is derived from the verified caller instead of a literal default (#17056).
