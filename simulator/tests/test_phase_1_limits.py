"""The Phase 1 limits, checked rather than trusted to the comments.

AGENTS.md section 1: Phase 1 is read-only monitoring of level and temperature.
The hardwired safety chain is only ever read as status-only digital inputs, and
no code may output to it. The controller is send-only (ADR-0004 decision 10),
and ``interfaces/records.cddl`` has no inbound message type for a command to
travel in.

These tests fail if a later change starts to blur any of that.
"""

from __future__ import annotations

import inspect

import pytest

from tanksim import device, link, plant
from tanksim.cddl import SchemaError
from tanksim.link import BufferedLink, RecordingSink

# Words that would belong to a control path. None of them may appear as a public
# name in the simulator's modules.
FORBIDDEN_NAMES = (
    "write_signal",
    "set_signal",
    "setpoint",
    "command",
    "actuate",
    "trip",
    "interlock",
    "enable_output",
)

# Modules that would carry such a path if one existed.
CHECKED_MODULES = (device, link, plant)


def public_names(module) -> list[str]:
    return [name for name in dir(module) if not name.startswith("_")]


@pytest.mark.parametrize("module", CHECKED_MODULES, ids=lambda m: m.__name__)
def test_no_module_exposes_a_control_path(module):
    names = " ".join(public_names(module)).lower()
    for forbidden in FORBIDDEN_NAMES:
        assert forbidden not in names, f"{module.__name__} exposes {forbidden}"


def test_the_device_has_no_method_that_writes_a_signal():
    methods = [
        name
        for name, _ in inspect.getmembers(device.SimulatedDevice, inspect.isfunction)
        if not name.startswith("_")
    ]
    assert sorted(methods) == ["run", "scan"]


def test_the_link_carries_nothing_inbound():
    # A send-only controller: the link publishes and nothing receives.
    methods = [
        name
        for name, _ in inspect.getmembers(BufferedLink, inspect.isfunction)
        if not name.startswith("_")
    ]
    assert sorted(methods) == ["publish", "set_up"]


def test_the_schema_has_no_inbound_record(schema):
    # If a command record were ever added, this would start to pass.
    for rule in schema.rule_names:
        assert "command" not in rule
        assert "setpoint" not in rule


def test_a_command_shaped_message_is_not_a_valid_record(schema):
    with pytest.raises(SchemaError):
        schema.validate({"v": 1, "cmd": "open_valve"})


def test_safety_chain_channels_are_produced_as_status_inputs_only(signal_list, make_device):
    # The simulator may simulate the safety-chain *status inputs*. They appear
    # in the record like any other reading, and nothing in the simulator can
    # drive them.
    safety = signal_list.safety_path_signals()
    assert safety, "the signal list should mark the safety and alarm channels"

    result = make_device(BufferedLink(RecordingSink())).scan()
    produced = {r.signal_id for r in result.record.readings}
    for signal in safety:
        assert signal.id in produced
        assert signal.read_only is True
        assert signal.unit == "bool"


def test_the_safety_channels_are_the_ones_the_ee_listed(signal_list):
    # Channels 1-2 (safety chain) and 10-15 (alarms) per AGENTS.md section 5.
    channels = sorted(int(signal.source["channel"]) for signal in signal_list.safety_path_signals())
    assert channels == [1, 2, 10, 11, 12, 13, 14, 15]


def test_no_phase_2_signal_is_simulated(signal_list):
    # Vibration, noise, exhaust, fuel and power are Phase 2.
    names = " ".join(signal.name for signal in signal_list)
    for phase_2 in ("vibration", "noise", "exhaust", "fuel", "power", "volume", "mass"):
        assert phase_2 not in names


def test_volume_and_mass_are_not_computed_here(signal_list):
    # ADR-0004 decision 10 computes them in the cloud; the controller is
    # send-only and does not derive them.
    assert "volume" not in dir(plant)
    assert "mass" not in dir(plant)
    assert all(signal.unit != "percent" or signal.group == "health" for signal in signal_list)
