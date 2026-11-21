"""Tests for the fault-injection plan and its three interfaces."""

from __future__ import annotations

import json

import pytest

from tanksim.faults import (
    FAULT_KINDS,
    OUT_OF_RANGE,
    SENSOR_FAULT,
    STALE,
    FaultError,
    FaultPlan,
    LinkDrop,
    ScanWindow,
    SignalFault,
    load_scenario,
    out_of_range_value,
    parse_link_drop,
    parse_signal_fault,
    plan_from_scenario,
)


def test_the_three_kinds_the_story_asks_for_exist():
    assert set(FAULT_KINDS) == {SENSOR_FAULT, OUT_OF_RANGE, STALE}


# -- windows -------------------------------------------------------------


def test_an_open_ended_window_covers_everything_after_its_start():
    window = ScanWindow(first=3)
    assert not window.contains(2)
    assert window.contains(3)
    assert window.contains(3000)


def test_a_closed_window_has_both_ends():
    window = ScanWindow(first=2, last=4)
    assert [window.contains(n) for n in range(6)] == [False, False, True, True, True, False]
    assert str(window) == "2-4"


def test_an_impossible_window_is_refused():
    with pytest.raises(FaultError, match="ends before it starts"):
        ScanWindow(first=5, last=2)
    with pytest.raises(FaultError, match="before scan 0"):
        ScanWindow(first=-1)


# -- the API -------------------------------------------------------------


def test_an_unknown_fault_kind_is_refused():
    with pytest.raises(FaultError, match="unknown fault kind"):
        SignalFault(signal_id=1001, kind="explode")


def test_a_permanent_link_drop_is_refused():
    # It would never deliver a record, which is a mistake, not a test.
    with pytest.raises(FaultError, match="never deliver"):
        LinkDrop(window=ScanWindow())


def test_the_plan_reports_the_active_fault():
    plan = FaultPlan(
        signal_faults=(
            SignalFault(1001, SENSOR_FAULT, ScanWindow(1, 2)),
            SignalFault(1001, OUT_OF_RANGE, ScanWindow(2, 3)),
        ),
        link_drops=(LinkDrop(ScanWindow(4, 5)),),
    )
    assert plan.kind_for(1001, 0) is None
    assert plan.kind_for(1001, 1) == SENSOR_FAULT
    # Overlapping faults: the first one given wins, so a scenario reads top down.
    assert plan.kind_for(1001, 2) == SENSOR_FAULT
    assert plan.kind_for(1001, 3) == OUT_OF_RANGE
    assert plan.kind_for(2001, 1) is None
    assert [plan.link_down(n) for n in range(7)] == [
        False,
        False,
        False,
        False,
        True,
        True,
        False,
    ]


def test_an_empty_plan_injects_nothing():
    plan = FaultPlan()
    assert plan.kind_for(1001, 0) is None
    assert plan.link_down(0) is False


def test_a_fault_on_an_unknown_signal_is_caught_before_the_run(signal_list):
    plan = FaultPlan(signal_faults=(SignalFault(9999, SENSOR_FAULT),))
    with pytest.raises(Exception, match="no signal with id 9999"):
        plan.validate_against(signal_list)


def test_an_out_of_range_fault_needs_a_range(signal_list):
    digital = signal_list.in_group("digital")[0]
    plan = FaultPlan(signal_faults=(SignalFault(digital.id, OUT_OF_RANGE),))
    with pytest.raises(FaultError, match="no valid_range"):
        plan.validate_against(signal_list)


def test_a_valid_plan_passes_validation(signal_list):
    analogue = signal_list.in_group("analogue")[0]
    FaultPlan(signal_faults=(SignalFault(analogue.id, OUT_OF_RANGE),)).validate_against(signal_list)


def test_an_injected_out_of_range_value_really_leaves_the_range():
    assert out_of_range_value(4.0, 20.0) > 20.0


# -- the CLI flags -------------------------------------------------------


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ("2001:sensor_fault", SignalFault(2001, SENSOR_FAULT, ScanWindow())),
        ("1001:out_of_range@5-9", SignalFault(1001, OUT_OF_RANGE, ScanWindow(5, 9))),
        ("3001:stale@7", SignalFault(3001, STALE, ScanWindow(7, 7))),
        ("3001:stale@7-", SignalFault(3001, STALE, ScanWindow(7, None))),
        ("3001:stale@-7", SignalFault(3001, STALE, ScanWindow(0, 7))),
    ],
)
def test_a_fault_flag_is_parsed(spec, expected):
    assert parse_signal_fault(spec) == expected


@pytest.mark.parametrize("spec", ["2001", "2001:", ":sensor_fault", "2001:nonsense"])
def test_a_malformed_fault_flag_is_refused(spec):
    with pytest.raises(FaultError):
        parse_signal_fault(spec)


def test_a_fault_flag_with_a_non_numeric_id_is_refused():
    with pytest.raises(FaultError, match="not a whole number"):
        parse_signal_fault("radar:sensor_fault")


def test_a_fault_flag_with_a_non_numeric_window_is_refused():
    with pytest.raises(FaultError, match="not a whole number"):
        parse_signal_fault("2001:stale@soon-later")


def test_a_link_drop_flag_is_parsed():
    assert parse_link_drop("3-7") == LinkDrop(ScanWindow(3, 7))
    assert parse_link_drop("4") == LinkDrop(ScanWindow(4, 4))
    assert parse_link_drop("4-") == LinkDrop(ScanWindow(4, None))


# -- the scenario file ---------------------------------------------------


def test_a_scenario_mapping_builds_the_same_plan():
    plan = plan_from_scenario(
        {
            "signal_faults": [
                {"signal_id": 2001, "kind": SENSOR_FAULT, "first_scan": 3, "last_scan": 6}
            ],
            "link_drops": [{"first_scan": 10, "last_scan": 14}],
        }
    )
    assert plan.signal_faults == (SignalFault(2001, SENSOR_FAULT, ScanWindow(3, 6)),)
    assert plan.link_drops == (LinkDrop(ScanWindow(10, 14)),)


def test_a_scenario_may_leave_a_window_open_ended():
    plan = plan_from_scenario(
        {"signal_faults": [{"signal_id": 1, "kind": STALE, "first_scan": 2, "last_scan": None}]}
    )
    assert plan.signal_faults[0].window.last is None


def test_an_unknown_scenario_key_is_refused():
    with pytest.raises(FaultError, match="unknown key"):
        plan_from_scenario({"faults": []})


def test_a_scenario_file_is_read(tmp_path):
    path = tmp_path / "scenario.json"
    path.write_text(
        json.dumps({"link_drops": [{"first_scan": 1, "last_scan": 2}]}), encoding="utf-8"
    )
    assert load_scenario(path).link_drops == (LinkDrop(ScanWindow(1, 2)),)


def test_a_missing_scenario_file_is_refused(tmp_path):
    with pytest.raises(FaultError, match="not found"):
        load_scenario(tmp_path / "nothing.json")


def test_a_scenario_file_that_is_not_json_is_refused(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(FaultError, match="not valid JSON"):
        load_scenario(path)


def test_a_scenario_file_that_is_not_an_object_is_refused(tmp_path):
    path = tmp_path / "list.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(FaultError, match="JSON object"):
        load_scenario(path)
