---
type: fix
scope: infra
issue: 14288
pr: 0000
---
`cleanup-nodes.yml`'s NPU-worker and browser-automation cleanup plays now target `npu_worker` and `browser` — group names both execution stacks actually emit (`services/inventory_builder.py` and `role_registry.py::ROLE_ANSIBLE_GROUPS`) — instead of `npu-worker`/`browser-automation`, which no inventory builder produces. Ansible does not treat `-` and `_` as equivalent, so both plays had matched zero hosts on every run while reporting success.
