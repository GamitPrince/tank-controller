"""Tests for loading the signal list from ``interfaces/signals-v1.yaml``."""

from __future__ import annotations

import pytest

from tanksim.interfaces import ENV_VAR, InterfacesNotFound, find_interfaces_dir, signal_list_path
from tanksim.signals import SIGNAL_GROUPS, SignalListError, load_signal_list


def write_list(tmp_path, body: str):
    path = tmp_path / "signals-v1.yaml"
    path.write_text(body, encoding="utf-8")
    return path


MINIMAL = """
version: 1
status: draft
analogue:
  - id: 1001
    name: level_radar_loop_current
    class: measurement
    unit: mA
    scale: 0.001
    valid_range: [4.0, 20.0]
    update_rate_ms: 1000
    read_only: true
    source:
      device: AD4111
      channel: 1
"""


# -- the real list -------------------------------------------------------


def test_loads_the_real_signal_list(signal_list):
    assert signal_list.version == 1
    assert len(signal_list) > 0
    assert {s.group for s in signal_list} <= set(SIGNAL_GROUPS)


def test_every_phase_1_signal_is_read_only(signal_list):
    # The controller is send-only and the safety chain is only ever read, so a
    # writable signal would be a phase change.
    assert all(signal.read_only for signal in signal_list)


def test_the_list_matches_the_ee_inventory(signal_list):
    # Counts from AGENTS.md section 5, so a silent edit to the YAML is caught.
    assert len(signal_list.in_group("analogue")) == 2
    assert len(signal_list.in_group("temperature")) == 6
    assert len(signal_list.in_group("digital")) == 15
    assert len(signal_list.safety_path_signals()) == 8


def test_the_two_contact_senses_are_not_harmonised(signal_list):
    # A broken wire must read as alarm on a safety or alarm channel, while an
    # open contact on an equipment channel simply means "not running".
    digital = signal_list.in_group("digital")
    safety = {s.contact_sense for s in digital if s.safety_path}
    equipment = {s.contact_sense for s in digital if not s.safety_path}
    assert safety == {"normally_closed"}
    assert equipment == {"normally_open"}


def test_no_signal_the_board_does_not_have(signal_list):
    # Not wired to this board: over-temperature trip, emergency stop, fire,
    # gas, ambient and wind. A record must not imply a signal we do not monitor.
    names = " ".join(signal.name for signal in signal_list)
    for absent in ("over_temp", "emergency", "fire", "gas", "ambient", "wind"):
        assert absent not in names


def test_lookup_by_id_and_name(signal_list):
    first = signal_list.signals[0]
    assert signal_list.by_id(first.id) is first
    assert signal_list.by_name(first.name) is first


def test_lookup_of_an_unknown_signal_fails(signal_list):
    with pytest.raises(SignalListError, match="no signal with id"):
        signal_list.by_id(-1)
    with pytest.raises(SignalListError, match="no signal named"):
        signal_list.by_name("not_a_signal")


def test_scaling_round_trips_through_the_declared_scale(signal_list):
    temperature = signal_list.in_group("temperature")[0]
    raw = temperature.to_raw(145.25)
    assert temperature.to_engineering(raw) == pytest.approx(145.25)


def test_a_boolean_signal_has_no_scaled_value(signal_list):
    digital = signal_list.in_group("digital")[0]
    assert digital.is_boolean
    with pytest.raises(SignalListError, match="boolean"):
        digital.to_raw(1.0)


# -- rejecting a bad list ------------------------------------------------


def test_a_writable_signal_is_refused(tmp_path):
    path = write_list(tmp_path, MINIMAL.replace("read_only: true", "read_only: false"))
    with pytest.raises(SignalListError, match="not read_only"):
        load_signal_list(path)


def test_a_version_mismatch_is_refused(tmp_path):
    path = write_list(tmp_path, MINIMAL.replace("version: 1", "version: 2"))
    with pytest.raises(SignalListError, match="declares version 2"):
        load_signal_list(path)


def test_an_unknown_group_is_refused(tmp_path):
    path = write_list(tmp_path, MINIMAL + "\nvibration:\n  - id: 4001\n")
    with pytest.raises(SignalListError, match="group"):
        load_signal_list(path)


def test_a_missing_field_is_refused(tmp_path):
    path = write_list(tmp_path, MINIMAL.replace("    unit: mA\n", ""))
    with pytest.raises(SignalListError, match="missing unit"):
        load_signal_list(path)


def test_an_inverted_valid_range_is_refused(tmp_path):
    path = write_list(tmp_path, MINIMAL.replace("[4.0, 20.0]", "[20.0, 4.0]"))
    with pytest.raises(SignalListError, match="inverted valid_range"):
        load_signal_list(path)


def test_a_duplicate_id_is_refused(tmp_path):
    doubled = MINIMAL + MINIMAL.split("analogue:")[1].replace(
        "level_radar_loop_current", "level_other"
    )
    path = write_list(tmp_path, doubled)
    with pytest.raises(SignalListError, match="duplicate signal id"):
        load_signal_list(path)


def test_a_duplicate_name_is_refused(tmp_path):
    doubled = MINIMAL + MINIMAL.split("analogue:")[1].replace("id: 1001", "id: 1099")
    path = write_list(tmp_path, doubled)
    with pytest.raises(SignalListError, match="duplicate signal name"):
        load_signal_list(path)


def test_an_empty_list_is_refused(tmp_path):
    path = write_list(tmp_path, "version: 1\nstatus: draft\n")
    with pytest.raises(SignalListError, match="defines no signals"):
        load_signal_list(path)


def test_a_non_mapping_file_is_refused(tmp_path):
    path = write_list(tmp_path, "- just\n- a\n- list\n")
    with pytest.raises(SignalListError, match="YAML mapping"):
        load_signal_list(path)


def test_a_missing_file_is_refused(tmp_path):
    with pytest.raises(SignalListError, match="not found"):
        load_signal_list(tmp_path / "nothing.yaml")


# -- locating interfaces/ ------------------------------------------------


def test_the_env_var_overrides_the_search(monkeypatch, interfaces_dir):
    monkeypatch.setenv(ENV_VAR, str(interfaces_dir))
    assert find_interfaces_dir() == interfaces_dir


def test_an_env_var_pointing_nowhere_is_refused(monkeypatch, tmp_path):
    monkeypatch.setenv(ENV_VAR, str(tmp_path))
    with pytest.raises(InterfacesNotFound, match=ENV_VAR):
        find_interfaces_dir()


def test_the_search_gives_up_outside_a_checkout(monkeypatch, tmp_path):
    monkeypatch.delenv(ENV_VAR, raising=False)
    with pytest.raises(InterfacesNotFound, match="No interfaces/ folder"):
        find_interfaces_dir(start=tmp_path / "deep" / "file.py")


def test_the_version_is_part_of_the_filename(interfaces_dir):
    assert signal_list_path(interfaces_dir).name == "signals-v1.yaml"
