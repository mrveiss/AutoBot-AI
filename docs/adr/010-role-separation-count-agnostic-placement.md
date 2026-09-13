# ADR-010: Role Separation with Count-Agnostic Placement

## Status

**Status**: Accepted

Supersedes [ADR-001](001-distributed-vm-architecture.md).

## Date

**Date**: 2026-09-12

## Context

AutoBot is an AI-powered automation platform that requires multiple specialized services:
- Backend API processing
- Frontend web interface
- Redis data storage
- AI/ML model serving
- Browser automation
- Hardware-accelerated AI (NPU)

Running all services on a single machine creates several problems:
1. **Resource contention**: AI workloads compete with API requests
2. **Single point of failure**: One crash affects all services
3. **Scaling limitations**: Cannot scale individual components
4. **Security concerns**: Browser automation needs isolation
5. **Hardware requirements**: NPU acceleration requires specific hardware

ADR-001 (2025-01-01) answered this by fixing the topology at exactly six virtual machines,
one per service. That Context above is sound and survives unchanged — every one of those five
problems is a real reason to separate roles. What did not survive is the leap from "roles
should be separable" to "there are six of them and each gets its own VM": that was one
operator's install, at one point in time, written down as if it were the architecture itself.

By 2026, that fiction had propagated: 54 documents under `docs/`, four code comments in
SSOT-adjacent files (`autobot_shared/ssot_config.py`, `autobot-backend/utils/service_discovery.py`,
`autobot-frontend/src/constants/network.ts`, `autobot-backend/config/registry_defaults.py`), and
four executable tests in `autobot-infrastructure/shared/tests/test_architecture_compliance.py`
all asserted a six-VM topology as if it were guaranteed. Wiring those tests into CI for the
first time (#15051, PR #15315) made the fiction fail loudly: it asserted that the browser
service must be at a specific `VM5` address, that no service may bind to loopback, that ports
must equal specific literals, and that backend and frontend must be on different hosts. None of
those are true of a Docker deployment or a single-VM deployment, both of which AutoBot supports
today and has supported since before ADR-001 was written.

**The owner has confirmed there is no fixed VM count.** AutoBot is elastic: it runs in Docker,
on a single VM, or scaled out to whatever number of machines an operator chooses. That range —
not "six," not "a minimum of N" — is the invariant this ADR records.

## Decision

**Roles are the architectural invariant. The number of hosts that carry them is a deployment
choice, not part of the architecture.**

AutoBot defines the following roles (see [VM_ROLES.md](../architecture/VM_ROLES.md) for the
authoritative, living definition of each role's services, ports, and Ansible group):

| Role | Purpose |
|------|---------|
| `slm` | Control plane — orchestration, admin UI, monitoring stack |
| `backend` | Core API — agents, workflows, knowledge, chat, terminal |
| `frontend` | Web UI (exactly one instance system-wide — see [ADR-005](005-single-frontend-mandate.md)) |
| `database` | Persistent data — Redis Stack, ChromaDB, model storage |
| `aiml` | LLM inference and NPU acceleration |
| `browser` | Web automation — Playwright, VNC desktop |

A deployment resolves each role to a host through the SSOT configuration
(`infrastructure.hosts.<role>`), never through a hardcoded IP or a hostname baked into code.
That resolution is what makes count-agnostic placement possible: the same Ansible roles and
the same application code run whether a role's host is `127.0.0.x` (co-located, one machine),
a dedicated VM, or one of several machines carrying that role at larger scale. Nothing in the
platform enumerates "VM1" through "VM6," and nothing should.

### Co-location constraints

Not every role can be freely mixed with every other, and not every role benefits equally from
isolation. This ADR keeps ADR-001's five original justifications as the constraints that govern
*where* a role can go, not as a reason to fix a count:

- **NPU acceleration needs the hardware.** The `aiml` role's NPU subgroup (`npu_workers`) must
  run wherever the NPU (or a passthrough to it) is physically available. On a machine without
  one, the role falls back to CPU/GPU inference or a cloud provider (see
  [ADR-003](003-npu-integration-strategy.md)). This is a hardware constraint, not a headcount.
- **Browser automation benefits from isolation.** Playwright drives real browser processes and
  is the role most likely to be exposed to untrusted content; giving it its own host (or at
  least its own container/network namespace) limits the blast radius of a compromised page.
  It is not required to be a separate machine — Docker network isolation on a single host
  satisfies the same property at smaller scale.
- **Resource contention** between AI workloads and API requests is the reason `aiml` and
  `backend` are separable roles, not that they must always be separate hosts.
- **Single point of failure** is the reason `database` is a distinct role with its own
  failure domain — again, separable, not mandatorily separate.
- **Frontend isolation** (port conflicts, WebSocket confusion, CORS) is why exactly one
  frontend instance may run system-wide, independent of how many hosts exist
  ([ADR-005](005-single-frontend-mandate.md)).

### How to scale

Scaling is adding or removing hosts per role, never a fixed step from N to N+1 machines:

- **Docker, single host**: every role co-located, bound to distinct `127.0.0.x` loopback
  aliases (see [IP_ADDRESSING_SCHEME.md](../api/IP_ADDRESSING_SCHEME.md)).
- **Single VM**: same as Docker, one operating system instead of containers.
- **Distributed, small**: one host per role, IPs assigned at install time and resolved through
  `infrastructure.hosts.<role>`.
- **Distributed, large**: some roles (most plausibly `aiml` for NPU/GPU inference, or `browser`
  for parallel automation sessions) run on more than one host, load-balanced behind the same
  role name. Nothing about frontend, backend, or database presumes a ceiling.

Adding a new role, or a new host for an existing role, follows the procedure already documented
in [VM_ROLES.md § Adding a New VM Role](../architecture/VM_ROLES.md#adding-a-new-vm-role) — an
Ansible group and `infrastructure.hosts.<role>` entry, never a literal address in application
code.

### One historical install, not a recommendation

A deployment made on 2025-09-12 happened to use six virtual machines, one per role. That
install is preserved as a dated historical record at
[`docs/archives/DISTRIBUTED_6VM_SETUP_20250912.md`](../archives/DISTRIBUTED_6VM_SETUP_20250912.md)
— a snapshot of what one operator ran, not a topology the platform requires or recommends.
Relabelling it "the reference architecture," or replacing six with any other fixed or minimum
count, would reproduce the same defect this ADR corrects.

### Alternatives Considered

1. **Keep ADR-001's fixed count, add a qualifier ("six is the reference architecture")**
   - Pros: Smallest possible diff.
   - Cons: Rejected — this is the same invariant with a hedge in front of it. A reader still
     comes away believing six is a shape the platform knows about, which is exactly the fiction
     that broke four tests in CI.

2. **Replace six with a different fixed number (e.g., a documented minimum)**
   - Pros: Feels more conservative than removing the number outright.
   - Cons: Rejected — no minimum or recommended count is established anywhere in the deployment
     tooling. Inventing one would be the same defect with different arithmetic.

3. **Delete ADR-001 outright**
   - Pros: Removes the wrong artifact entirely.
   - Cons: Rejected — ADRs are a historical record of what was decided and when; superseding
     preserves that history while making clear it no longer governs. See
     "Superseding an ADR" in [`docs/adr/README.md`](README.md).

4. **Role separation with count-agnostic placement (Chosen)**
   - Pros: Keeps every justification in ADR-001's Context, matches how the platform is actually
     built (SSOT-resolved `infrastructure.hosts.<role>`, Ansible groups, `VM_ROLES.md`), and is
     the one description consistent with the owner's confirmation that AutoBot scales from
     Docker or one VM to any operator-chosen count.
   - Cons: Slightly more to hold in your head than "there are six VMs" — but that simplicity was
     false.

## Consequences

### Positive

- **Matches reality**: documentation, code comments, and tests describe what the platform
  actually guarantees instead of one operator's install.
- **No false CI failures**: a deployment resolver that returns `127.0.0.1` for a co-located
  role, or the same host for two roles, is correct rather than a violation.
- **Scales in both directions**: nothing blocks running on fewer hosts (Docker, one VM) or more
  (splitting `aiml` or `browser` across several) without an architecture rewrite.
- **Hardware constraints stay explicit**: NPU placement and browser isolation are recorded as
  *reasons a role goes where it goes*, not folded into an arbitrary headcount.

### Negative

- **Less quotable**: "it depends on the deployment" is a harder one-line answer than "six VMs."
- **Requires reading `VM_ROLES.md`** for the current, living set of roles rather than a static
  table in this ADR — intentional, since roles are added over time (see "Adding a New VM Role").

### Neutral

- Existing per-role Ansible groups, `infrastructure.hosts.<role>` variables, and loopback alias
  conventions are unchanged by this ADR; it documents the invariant they already implement.

## Implementation Notes

### Key Files

- `docs/architecture/VM_ROLES.md` - Authoritative, living role definitions (services, ports,
  Ansible groups, co-located loopback aliases)
- `docs/architecture/DISTRIBUTED_ARCHITECTURE.md` - Canonical distributed-architecture
  document (count-free)
- `docs/archives/DISTRIBUTED_6VM_SETUP_20250912.md` - Historical record of one dated install
- `autobot-slm-backend/ansible/inventory/hosts.yml` - Live Ansible groups per role
- `autobot-slm-backend/ansible/inventory/group_vars/infrastructure.yml` -
  `infrastructure.hosts.<role>` resolution

### Configuration

```yaml
# infrastructure.hosts.<role> resolves at deploy time — never hardcode a role's address
infrastructure:
  hosts:
    backend: "{{ backend_host }}"
    frontend: "{{ frontend_host }}"
    database: "{{ database_host }}"
    aiml: "{{ aiml_host }}"
    browser: "{{ browser_host }}"
```

## Related ADRs

- [ADR-001](001-distributed-vm-architecture.md) - Superseded by this ADR; its Context is
  preserved above
- [ADR-002](002-redis-database-separation.md) - Redis runs on the `database` role's host,
  wherever that is placed
- [ADR-003](003-npu-integration-strategy.md) - NPU worker occupies its own role, placed where
  the hardware is
- [ADR-005](005-single-frontend-mandate.md) - Exactly one frontend instance system-wide,
  independent of host count

---

**Author**: mrveiss
**Copyright**: © 2026 mrveiss
