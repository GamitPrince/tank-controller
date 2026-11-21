"""Tests for the plant model.

The model is driven by the signal list, so the tests are mostly about that:
every signal gets a value, the values sit inside the ranges the YAML declares,
and a signal the model has no generator for is reported as unconfigured rather
than invented.
"""

from __future__ import annotations

import pytest

from tanksim.plant import PlantConfig, PlantModel, PlantState
from tanksim.signals import SIGNAL_GROUPS, Signal, SignalList

STATE = PlantState(uptime_ms=0, uptime_s=0, link_up=True, buffer_fraction=0.0)


@pytest.fixture
def model(signal_list) -> PlantModel:
    return PlantModel(signal_list)


def test_every_signal_in_the_list_is_produced(model, signal_list):
    samples = model.sample_all(STATE)
    assert set(samples) == {signal.id for signal in signal_list}


def test_every_measured_value_sits_inside_its_declared_range(model, signal_list):
    for uptime_ms in (0, 60_000, 450_000, 900_000, 1_234_567):
        state = PlantState(
            uptime_ms=uptime_ms, uptime_s=uptime_ms // 1000, link_up=True, buffer_fraction=0.5
        )
        for signal in signal_list:
            if signal.valid_range is None or signal.is_boolean:
                continue
            low, high = signal.valid_range
            value = model.sample(signal, state).value
            assert low <= value <= high, f"{signal.name} at {uptime_ms} ms gave {value}"


def test_the_two_analogue_channels_differ(model, signal_list):
    radar, pressure = signal_list.in_group("analogue")
    assert model.sample(radar, STATE).value != model.sample(pressure, STATE).value


def test_the_bottom_of_the_tank_is_hotter_than_the_top(model, signal_list):
    # The base heater sits at the bottom. Comparing the levels is a Phase 2
    # check, but the model should not make them identical.
    by_level = {}
    for signal in signal_list.in_group("temperature"):
        level = signal.source.get("level")
        if float(signal.source.get("orientation_deg", 0)) == 0.0:
            by_level[level] = model.sample(signal, STATE).value
    assert by_level["bottom"] > by_level["middle"] > by_level["upper"]


def test_the_two_sensors_of_a_pair_are_not_identical(model, signal_list):
    pair = [s for s in signal_list.in_group("temperature") if s.source.get("level") == "upper"]
    values = [model.sample(signal, STATE).value for signal in pair]
    assert values[0] != values[1]


def test_safety_and_alarm_contacts_read_healthy_in_a_normal_run(model, signal_list):
    for signal in signal_list.safety_path_signals():
        assert model.sample(signal, STATE).value is False


def test_equipment_status_channels_change_over_a_cycle(model, signal_list):
    equipment = [s for s in signal_list.in_group("digital") if not s.safety_path]
    period_ms = int(model.config.equipment_period_s * 1000)
    seen = set()
    for step in range(0, period_ms, period_ms // 8):
        state = PlantState(uptime_ms=step, uptime_s=step // 1000, link_up=True, buffer_fraction=0.0)
        seen.update(model.sample(signal, state).value for signal in equipment)
    assert seen == {True, False}


def test_the_health_signals_report_the_device_state(model, signal_list):
    state = PlantState(uptime_ms=120_000, uptime_s=120, link_up=False, buffer_fraction=0.25)
    assert model.sample(signal_list.by_name("health_uptime"), state).value == 120
    assert model.sample(signal_list.by_name("health_cloud_link_up"), state).value is False
    buffer_signal = signal_list.by_name("health_log_buffer_used")
    assert model.sample(buffer_signal, state).value == pytest.approx(25.0)


def test_a_signal_group_the_model_does_not_know_is_unconfigured(model):
    invented = Signal(
        id=4001,
        name="vibration_rms",
        group="vibration",
        signal_class="measurement",
        unit="mm/s",
        scale=0.01,
        update_rate_ms=1000,
        read_only=True,
    )
    sample = model.sample(invented, STATE)
    assert sample.status == "unconfigured"
    assert sample.value is None


def test_a_health_signal_the_model_does_not_know_is_unconfigured(model):
    future = Signal(
        id=9099,
        name="health_something_new",
        group="health",
        signal_class="health",
        unit="s",
        scale=1,
        update_rate_ms=60000,
        read_only=True,
    )
    assert model.sample(future, STATE).status == "unconfigured"


def test_a_measured_signal_with_no_range_cannot_be_placed(model):
    rangeless = Signal(
        id=1099,
        name="level_without_a_range",
        group="analogue",
        signal_class="measurement",
        unit="mA",
        scale=0.001,
        update_rate_ms=1000,
        read_only=True,
    )
    with pytest.raises(ValueError, match="no valid_range"):
        model.sample(rangeless, STATE)


def test_the_model_covers_every_group_the_loader_knows(signal_list: SignalList):
    # If a group were added to the loader without a generator, every signal in
    # it would silently come out unconfigured.
    produced = {signal.group for signal in signal_list}
    assert produced == set(SIGNAL_GROUPS)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"analogue_period_s": 0},
        {"temperature_period_s": -1},
        {"equipment_period_s": 0},
        {"analogue_span_fraction": 0},
        {"temperature_span_fraction": 1.5},
        {"equipment_duty": 0},
    ],
)
def test_an_impossible_configuration_is_refused(kwargs):
    with pytest.raises(ValueError):
        PlantConfig(**kwargs)
