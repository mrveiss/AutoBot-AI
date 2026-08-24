# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Render tests for the backend unit's derived memory limits (#13765).

`autobot-backend` ran for months under `MemoryHigh=8G` / `MemoryMax=12G` applied
by hand with `systemctl set-property`, which writes into
`/etc/systemd/system.control/` — a tree no template, role or repo artifact
mentions. On 2026-08-03 it pinned itself at that watermark with
`memory.events high` at 21,052, the process in `STAT=D` and `/health` timing
out, while `systemctl` reported `active` for the whole window.

The owner's decision (#13765, 2026-08-09) was that the limits must be
*autodetected* rather than templated, because 8 GiB was never a policy — it was
that box. So the acceptance criterion is not "a number is present": it is that
**two hosts with different RAM render different, sensible limits**, which is
what this file asserts.

Follows the render-test precedent in test_backend_service_faulthandler_12777.py.
"""

import os
import re
from pathlib import Path

import pytest

jinja2 = pytest.importorskip("jinja2")

_ROLE_DIR = Path(__file__).resolve().parents[1] / "ansible" / "roles" / "backend"
_TEMPLATE_DIR = _ROLE_DIR / "templates"
_TEMPLATE = "autobot-backend.service.j2"

# The host the incident was reported from. Its hand-applied override was
# MemoryHigh=8589934592 (8 GiB) / MemoryMax=12884901888 (12 GiB).
_INCIDENT_HOST_MB = 16384
_INCIDENT_HIGH_MB = 8192
_INCIDENT_MAX_MB = 12288

_CTX = {
    "backend_install_dir": "/opt/autobot/autobot-backend",
    "backend_code_dir": "/opt/autobot/autobot-backend",
    "backend_log_dir": "/var/log/autobot",
    "backend_host": "0.0.0.0",
    "backend_port": 8001,
    "backend_workers": 1,
    "backend_user": "autobot",
    "backend_group": "autobot",
}


def _render(**overrides) -> str:
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(_TEMPLATE_DIR)))
    # Ansible filters the real template uses; not Jinja2 builtins.
    env.filters["dirname"] = os.path.dirname
    env.filters["basename"] = os.path.basename
    env.filters["bool"] = lambda v: str(v).strip().lower() in ("true", "yes", "1", "on")
    return env.get_template(_TEMPLATE).render(**{**_CTX, **overrides})


def _limits(rendered: str) -> tuple[int | None, int | None]:
    """Return (MemoryHigh MB, MemoryMax MB) actually emitted by the unit.

    Anchored to line starts so a value quoted inside one of the template's
    explanatory comments cannot be mistaken for a live directive — the comments
    discuss these exact numbers, so an unanchored search would pass on a
    template that emits nothing at all.
    """
    high = re.search(r"(?m)^MemoryHigh=(\d+)M$", rendered)
    hard = re.search(r"(?m)^MemoryMax=(\d+)M$", rendered)
    return (int(high.group(1)) if high else None, int(hard.group(1)) if hard else None)


def test_template_actually_derives_from_the_memory_fact():
    """Guard the target exists before anything below asserts about it.

    Every other test here would pass vacuously against a template that had lost
    the block entirely: `_limits` would return (None, None) and the "no limits"
    assertions would hold. Assert the mechanism is present first.
    """
    source = (_TEMPLATE_DIR / _TEMPLATE).read_text(encoding="utf-8")
    assert "ansible_memtotal_mb" in source, "unit no longer derives limits from the host memory fact"
    assert "MemoryHigh=" in source
    assert "backend_memory_floor_mb" in source


def test_two_hosts_with_different_ram_render_different_limits():
    """The acceptance criterion, stated directly (#13765).

    A literal in the template would make these identical — which is the defect
    the owner rejected, not a smaller version of it.
    """
    small_high, small_max = _limits(_render(ansible_memtotal_mb=16384))
    large_high, large_max = _limits(_render(ansible_memtotal_mb=65536))

    assert small_high is not None and large_high is not None
    assert small_high != large_high
    assert small_max != large_max
    assert large_high > small_high
    assert large_max > small_max


def test_derivation_reproduces_the_hand_applied_override():
    """On the incident host the derived values must equal the override.

    This is the check that the derivation *replaces* the out-of-band drop-in
    rather than merely differing from it. `unit_only.yml` deletes that drop-in
    once the unit declares limits of its own, so a derivation that landed on
    different numbers would silently change the incident host's behaviour under
    cover of a fix.
    """
    high, hard = _limits(_render(ansible_memtotal_mb=_INCIDENT_HOST_MB))
    assert high == _INCIDENT_HIGH_MB
    assert hard == _INCIDENT_MAX_MB


@pytest.mark.parametrize(
    ("total_mb", "expected_high", "expected_max"),
    [
        (12288, 6144, 9216),
        (16384, 8192, 12288),
        (32768, 16384, 24576),
        (65536, 32768, 49152),
        (131072, 65536, 98304),
    ],
)
def test_sensible_limits_across_the_hardware_range(total_mb, expected_high, expected_max):
    """Sensible, not merely different: MemoryHigh below MemoryMax, both below total.

    MemoryHigh throttles and MemoryMax kills, so a host where they cross — or
    where either exceeds physical memory — has a limit that can never bind, or
    one that binds before the other in the wrong order.
    """
    high, hard = _limits(_render(ansible_memtotal_mb=total_mb))
    assert (high, hard) == (expected_high, expected_max)
    assert high < hard < total_mb


@pytest.mark.parametrize("total_mb", [1024, 2048, 4096, 8192])
def test_small_hosts_get_no_limits_rather_than_a_cap_they_cannot_meet(total_mb):
    """A watermark under the backend's ~4.3 GiB working set throttles it at idle.

    Emitting a smaller cap for a smaller host would reproduce the incident by
    template on every small install, so below the floor the unit emits nothing.
    """
    rendered = _render(ansible_memtotal_mb=total_mb)
    assert _limits(rendered) == (None, None)
    # And says so, so `systemctl cat` distinguishes "evaluated, left unlimited"
    # from "the fact never resolved".
    assert "No memory limits on this host" in rendered
    assert str(total_mb) in rendered


def test_accounting_is_emitted_even_when_no_limits_are():
    """memory.current / memory.events are what CgroupMemoryCollector reads.

    The reclaim counter is the only signal separating a throttled service from a
    healthy one, and an unlimited host still has to be able to report it. Gating
    accounting on the limits would leave exactly the small hosts dark.
    """
    for total_mb in (2048, 16384):
        assert re.search(r"(?m)^MemoryAccounting=yes$", _render(ansible_memtotal_mb=total_mb))


def test_percentages_are_tunable_and_the_template_holds_no_byte_literal():
    """The owner rejected a literal; a default that ignores its var is one."""
    high, hard = _limits(_render(ansible_memtotal_mb=32768, backend_memory_high_pct=25, backend_memory_max_pct=40))
    assert (high, hard) == (8192, 13107)


def test_floor_is_tunable_so_a_deliberate_small_host_can_opt_in():
    """Raising the floor must remove limits a lower floor would have emitted."""
    assert _limits(_render(ansible_memtotal_mb=16384)) == (_INCIDENT_HIGH_MB, _INCIDENT_MAX_MB)
    assert _limits(_render(ansible_memtotal_mb=16384, backend_memory_floor_mb=999999)) == (None, None)


def test_missing_memory_fact_does_not_render_a_confident_zero():
    """The builtin update path runs `gather_facts: false` on every play.

    Without the fact the template must not emit `MemoryHigh=0M` — a cap that
    would kill the backend on start. It renders no limits, and
    tasks/memory_limits.yml is what stops this state reaching a host at all.
    """
    rendered = _render()
    assert _limits(rendered) == (None, None)
    assert not re.search(r"(?m)^Memory(High|Max)=0M$", rendered)


def test_the_role_guarantees_the_fact_before_rendering():
    """A template guard is not enough on its own — assert the wiring, not the helper.

    memory_limits.yml exists precisely because the render above is silent about
    a missing fact. If the unit-rendering task file stops including it, the
    builtin updater silently renders every host unlimited.
    """
    guard = (_ROLE_DIR / "tasks" / "memory_limits.yml").read_text(encoding="utf-8")
    assert "ansible.builtin.setup" in guard
    assert "ansible.builtin.assert" in guard

    for task_file in ("unit_only.yml", "main.yml"):
        text = (_ROLE_DIR / "tasks" / task_file).read_text(encoding="utf-8")
        assert "memory_limits.yml" in text, f"{task_file} renders the unit without guaranteeing the memory fact"


def test_out_of_band_override_is_removed_only_when_the_unit_carries_limits():
    """Ordering the owner set on #13765, and the reason it is load-bearing.

    A `system.control` drop-in overrides the unit file, so leaving it defeats
    the derived limits entirely; removing it on a host whose unit declares none
    strips a protection someone deliberately added. The gate must therefore read
    the unit that was actually rendered rather than recompute the template's
    condition — two copies of that decision are free to disagree, and the half
    that answers "no limits" is the half that deletes.
    """
    text = (_ROLE_DIR / "tasks" / "unit_only.yml").read_text(encoding="utf-8")
    assert "/etc/systemd/system.control" in text
    assert "/run/systemd/system.control" in text
    assert "ansible.builtin.slurp" in text, "the removal gate must observe the rendered unit, not predict it"
    assert "backend_unit_declares_memory_limits" in text
    # The removal is conditional, and the condition is the observation.
    assert re.search(r"when:\s*backend_unit_declares_memory_limits \| bool", text)
