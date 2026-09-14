---
type: fix
scope: infra
issue: 16020
pr: 0
---
The last three roles (`backend`, `frontend`, `slm_manager`) that carried their own copy of the shared-node-TLS-keypair `openssl` block now include `_shared/tasks/ensure_node_tls_cert.yml` instead, so the invariant "a node that reaches a cert consumer has a cert" is enforced in exactly one place rather than duplicated in four. The shared task now also fails loudly, naming the missing path, if generation somehow didn't produce the certificate — instead of surfacing later as nginx's opaque "cannot load certificate" error. The same cert-ensure step is now also wired into the routine `update-all-nodes.yml` deploy path, not just full provisioning, so an already-provisioned node whose cert expires between provisioning runs gets it refreshed too.
