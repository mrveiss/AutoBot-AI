# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every UI-bound risk value carries RiskLevel, never a raw CommandRisk (#14995, #14992).

Three producers sent the raw six-member `CommandRisk` vocabulary
(`safe`/`moderate`/`high`/`critical`/`dangerous`/`forbidden`) where the frontend
normalises against the four-member `RiskLevel` one. #14987 fixed the first; these
are the other two.

The vocabularies overlap on the string `"high"` and `"critical"`, which is what
made this survive: a spot check with a HIGH command looks correct in either
vocabulary. Only `dangerous` and `forbidden` — which have no `RiskLevel`
counterpart and map to CRITICAL — expose it. So these tests drive **all six**
members rather than a representative one.
"""

from __future__ import annotations

import pytest

from autobot_shared.status_enums import CommandRisk
from models.command_execution import RiskLevel
from services.agent_terminal.utils import map_risk_to_level

_RAW_VALUES = {risk.value for risk in CommandRisk}
_WIRE_VALUES = {level.value for level in RiskLevel}


def test_the_two_vocabularies_are_actually_different() -> None:
    """Guard the guard.

    If these ever converge, every assertion below passes without proving
    anything — a raw member would *be* a valid wire value. #13845 records why
    they have not converged: picking one loses FORBIDDEN.
    """
    assert _RAW_VALUES != _WIRE_VALUES
    # The members that expose the bug: no RiskLevel counterpart at all.
    assert {"dangerous", "forbidden"} <= _RAW_VALUES
    assert not {"dangerous", "forbidden"} & _WIRE_VALUES


@pytest.mark.parametrize("risk", list(CommandRisk), ids=lambda r: r.name)
def test_every_command_risk_maps_onto_the_wire_vocabulary(risk: CommandRisk) -> None:
    wire = map_risk_to_level(risk).value

    assert wire in _WIRE_VALUES, f"{risk.name} produced {wire!r}, which is not a RiskLevel value"


@pytest.mark.parametrize("risk", [CommandRisk.DANGEROUS, CommandRisk.FORBIDDEN], ids=lambda r: r.name)
def test_a_blocking_verdict_is_not_downgraded(risk: CommandRisk) -> None:
    """The conversion must not soften a block.

    #13845 records the earlier form of this: an unmapped member fell through to
    MEDIUM, turning a blocking verdict into the middle of the scale.
    """
    assert map_risk_to_level(risk) is RiskLevel.CRITICAL


def test_no_raw_member_survives_the_conversion() -> None:
    """The property the wire depends on, stated once over the whole enum."""
    leaked = [r.name for r in CommandRisk if map_risk_to_level(r).value in (_RAW_VALUES - _WIRE_VALUES)]

    assert not leaked, f"these members reach the wire unconverted: {leaked}"


class TestPayloadsCarryTheWireVocabulary:
    """The payloads themselves, driven for every CommandRisk member.

    These replaced a pair of structural source assertions once the shaping moved
    into `agent_terminal/utils`: a payload builder can be called, so there is no
    reason to settle for grepping the call site for the converter's name.
    """

    @pytest.mark.parametrize("risk", list(CommandRisk), ids=lambda r: r.name)
    def test_the_security_warning_payload_never_carries_a_raw_member(self, risk: CommandRisk) -> None:
        from services.agent_terminal.utils import security_warning_payload

        payload = security_warning_payload("some-blocked-command", risk)

        assert payload["risk_level"] in _WIRE_VALUES
        assert payload["risk_level"] not in (_RAW_VALUES - _WIRE_VALUES)
        # The human-readable half must agree with the machine-readable half --
        # they were built from the same value before, and must stay that way.
        assert payload["risk_level"] in payload["content"]

    @pytest.mark.parametrize("risk", list(CommandRisk), ids=lambda r: r.name)
    def test_the_assessment_payload_never_carries_a_raw_member(self, risk: CommandRisk) -> None:
        from services.agent_terminal.utils import command_assessment_payload

        payload = command_assessment_payload("ls", risk)

        assert payload["risk_level"] in _WIRE_VALUES
        assert payload["risk_level"] in payload["message"]

    def test_confirmation_is_required_for_everything_but_safe(self) -> None:
        """`requires_confirmation` is derived from the RAW member, not the wire
        one -- SAFE maps to LOW, and LOW is not a value the wire vocabulary can
        distinguish from a converted MODERATE."""
        from services.agent_terminal.utils import command_assessment_payload

        assert command_assessment_payload("ls", CommandRisk.SAFE)["requires_confirmation"] is False
        for risk in CommandRisk:
            if risk is not CommandRisk.SAFE:
                assert command_assessment_payload("x", risk)["requires_confirmation"] is True


class TestProducersUseTheConverter:
    """The two producers this issue names, asserted structurally.

    A behavioural test would need a live WebSocket and a running PTY; what is
    actually at stake is whether the value passed to the client went through
    `map_risk_to_level`, and that is visible in the source. #14992's REST
    endpoint additionally has no frontend caller, so there is no end-to-end
    path to drive it through at all — which is precisely why it was filed for
    tracking rather than fixed blind.
    """

    def _source(self, relative: str) -> str:
        from pathlib import Path

        return (Path(__file__).resolve().parents[1] / relative).read_text(encoding="utf-8")

    def test_the_websocket_security_warning_sends_a_converted_value(self) -> None:
        source = self._source("api/terminal_handlers.py")
        start = source.index("security_warning_payload")
        block = source[start - 400 : start + 400]

        assert "security_warning_payload" in block, "security_warning still built inline (#14995)"

    def test_the_rest_endpoint_returns_a_converted_value(self) -> None:
        source = self._source("api/terminal.py")
        assert "command_assessment_payload" in source, "execute_single_command still builds its body inline (#14992)"

    def test_the_internal_records_keep_the_precise_vocabulary(self) -> None:
        """Deliberate asymmetry, so a future reader does not "fix" it.

        The audit log and command history keep the raw six-member member: they
        are internal records, `dangerous` and `forbidden` are more precise than
        CRITICAL, and converting them would rewrite the vocabulary of
        everything already stored.
        """
        source = self._source("api/terminal_handlers.py")

        assert '"risk_level": risk_level.value' in source
