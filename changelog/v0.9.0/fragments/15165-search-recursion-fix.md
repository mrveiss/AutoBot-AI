---
type: fix
scope: backend
issue: 15165
pr: 0000
---
`SearchMixin.search()`'s basic vector path no longer recurses through `VectorSearchEngine`'s CPU backend and back into itself — `_CPUBackend` now calls a direct, non-recursive `basic_vector_search()` leaf instead.
