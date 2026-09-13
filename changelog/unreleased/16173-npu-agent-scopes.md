---
type: refactor
scope: agents
issue: 16173
pr: 0
---
NPUCodeSearchAgent's language-detection and regex-based code-element extraction moved to a new `npu_code_search_patterns.py`, freeing room in the size-ceilinged agent file for `declared_scopes` — `index_directory` runs now claim a hashed scope of the directory they index, so a second agent indexing the same tree is refused rather than racing it.
