"""Tests for the device: a scan end to end, and the three injected faults.

This is where the story's acceptance criteria are checked against the real
contract in ``interfaces/``: every signal appears, the record validates, the
frame survives a round trip, and a sensor fault, an out-of-range value and a
link drop each do what the spec says.
"""

from __future__ import annotations

import pytest

from tanksim.device import DeviceError, SimulatedDevice, new_boot_id
from tanksim.faults import (
    OUT_OF_RANGE,
    SENSOR_FAULT,
    STALE,
    FaultPlan,
    LinkDrop,
    ScanWindow,
    SignalFault,
)
from tanksim.framing import decode_frame
from tanksim.record import BOOT_ID_BYTES, decode

# -- a plain scan --------------------------------------------------------


def test_a_scan_produces_every_signal_in_the_list(make_device, link, signal_list):
    result = make_device(link).scan()
    assert [r.signal_id for r in result.record.readings] == [s.id for s in signal_list]


def test_a_scan_record_validates_against_the_cddl_schema(
    make_device, link, schema, signal_list, device_id, boot_id
):
    # The acceptance criterion P1-03 deferred to this story.
    result = make_device(link).scan()
    decoded = decode(result.record.encode(schema), schema)
    assert decoded["dev"] == device_id
    assert decoded["sl"] == signal_list.version
    assert decoded["boot"] == boot_id
    assert len(decoded["r"]) == len(signal_list)


def test_the_published_frame_round_trips_to_a_valid_record(make_device, link, schema, sink):
    device = make_device(link)
    device.scan()
    frame = decode_frame(sink.frames[0])
    assert frame.sequence == 0
    decode(frame.payload, schema)


def test_every_good_reading_carries_a_value(make_device, link, quality):
    for reading in make_device(link).scan().record.readings:
        if reading.quality == quality.good:
            assert reading.value is not None


def test_a_value_sits_inside_the_range_the_signal_list_declares(
    make_device, link, signal_list, quality
):
    for reading in make_device(link).scan().record.readings:
        signal = signal_list.by_id(reading.signal_id)
        if signal.valid_range is None or signal.is_boolean:
            continue
        if reading.quality != quality.good:
            continue
        low, high = signal.valid_range
        assert low <= signal.to_engineering(reading.value) <= high


def test_a_digital_channel_sends_a_bool_not_a_number(make_device, link, signal_list):
    readings = {r.signal_id: r for r in make_device(link).scan().record.readings}
    for signal in signal_list.in_group("digital"):
        assert isinstance(readings[signal.id].value, bool)


def test_the_sequence_number_advances_with_each_scan(make_device, link):
    results = make_device(link).run(scans=3, interval_ms=1000)
    assert [r.record.sequence for r in results] == [0, 1, 2]
    assert [r.record.uptime_ms for r in results] == [0, 1000, 2000]


def test_records_before_sntp_carry_no_unix_time(make_device, link):
    results = make_device(link, sntp_sync_after_ms=1500).run(scans=3, interval_ms=1000)
    assert [r.record.time_known for r in results] == [False, False, True]
    assert [r.record.unix_time_s for r in results][:2] == [None, None]


def test_two_runs_with_the_same_arguments_produce_the_same_records(make_device, schema, link):
    from tanksim.link import BufferedLink, RecordingSink

    first = make_device(link).run(scans=2, interval_ms=1000)
    second = make_device(BufferedLink(RecordingSink())).run(scans=2, interval_ms=1000)
    assert [r.record.encode(schema) for r in first] == [r.record.encode(schema) for r in second]


def test_a_boot_id_is_the_length_the_schema_demands():
    assert len(new_boot_id()) == BOOT_ID_BYTES
    assert new_boot_id() != new_boot_id()


def test_a_device_needs_an_id(signal_list, link):
    from tanksim.clock import SimClock

    with pytest.raises(DeviceError, match="device id is required"):
        SimulatedDevice(
            device_id="",
            signal_list=signal_list,
            link=link,
            clock=SimClock(boot_unix_s=0),
        )


def test_a_negative_run_is_refused(make_device, link):
    with pytest.raises(DeviceError, match="cannot run"):
        make_device(link).run(scans=-1, interval_ms=1000)


# -- sensor failure ------------------------------------------------------


def test_an_injected_sensor_fault_sends_no_value(make_device, link, signal_list, quality, schema):
    temperature = signal_list.in_group("temperature")[0]
    plan = FaultPlan(signal_faults=(SignalFault(temperature.id, SENSOR_FAULT, ScanWindow(0, 0)),))
    result = make_device(link, plan).scan()

    reading = next(r for r in result.record.readings if r.signal_id == temperature.id)
    assert reading.quality == quality.fault
    assert reading.value is None
    # A failed sensor is flagged and excluded, never silently replaced, and the
    # record still validates with the value absent.
    encoded = decode(result.record.encode(schema), schema)
    faulted = next(entry for entry in encoded["r"] if entry["id"] == temperature.id)
    assert "val" not in faulted


def test_a_sensor_fault_only_lasts_for_its_window(make_device, link, signal_list, quality):
    temperature = signal_list.in_group("temperature")[0]
    plan = FaultPlan(signal_faults=(SignalFault(temperature.id, SENSOR_FAULT, ScanWindow(1, 1)),))
    results = make_device(link, plan).run(scans=3, interval_ms=1000)

    qualities = [
        next(r for r in result.record.readings if r.signal_id == temperature.id).quality
        for result in results
    ]
    assert qualities == [quality.good, quality.fault, quality.good]


def test_a_faulted_signal_is_still_present_in_the_record(make_device, link, signal_list):
    # Excluded means "not shown as a measurement", not "left out of the record":
    # the dashboard has to be able to say the sensor failed.
    temperature = signal_list.in_group("temperature")[0]
    plan = FaultPlan(signal_faults=(SignalFault(temperature.id, SENSOR_FAULT),))
    result = make_device(link, plan).scan()
    assert temperature.id in {r.signal_id for r in result.record.readings}


# -- out-of-range values -------------------------------------------------


def test_an_injected_out_of_range_value_is_flagged_not_clamped(
    make_device, link, signal_list, quality
):
    analogue = signal_list.in_group("analogue")[0]
    low, high = analogue.valid_range
    plan = FaultPlan(signal_faults=(SignalFault(analogue.id, OUT_OF_RANGE),))
    result = make_device(link, plan).scan()

    reading = next(r for r in result.record.readings if r.signal_id == analogue.id)
    assert reading.quality == quality.out_of_range
    # The value is sent as measured, outside the range, rather than clamped to
    # the limit, so a consumer can see how far out it is.
    assert analogue.to_engineering(reading.value) > high > low


def test_an_out_of_range_record_still_satisfies_the_schema(make_device, link, signal_list, schema):
    analogue = signal_list.in_group("analogue")[0]
    plan = FaultPlan(signal_faults=(SignalFault(analogue.id, OUT_OF_RANGE),))
    decode(make_device(link, plan).scan().record.encode(schema), schema)


# -- stale values --------------------------------------------------------


def test_a_stale_reading_repeats_the_last_value(make_device, link, signal_list, quality):
    analogue = signal_list.in_group("analogue")[0]
    plan = FaultPlan(signal_faults=(SignalFault(analogue.id, STALE, ScanWindow(1, 1)),))
    results = make_device(link, plan).run(scans=2, interval_ms=1000)

    first, second = (
        next(r for r in result.record.readings if r.signal_id == analogue.id) for result in results
    )
    assert second.quality == quality.stale
    assert second.value == first.value


def test_a_stale_reading_with_nothing_to_repeat_is_a_fault(make_device, link, signal_list, quality):
    # Never show stale data as live, and never invent a value that was never read.
    analogue = signal_list.in_group("analogue")[0]
    plan = FaultPlan(signal_faults=(SignalFault(analogue.id, STALE, ScanWindow(0, 0)),))
    reading = next(
        r for r in make_device(link, plan).scan().record.readings if r.signal_id == analogue.id
    )
    assert reading.quality == quality.fault
    assert reading.value is None


# -- link drop -----------------------------------------------------------


def test_a_link_drop_buffers_and_replays_with_original_timestamps(make_device, link, sink, schema):
    plan = FaultPlan(link_drops=(LinkDrop(ScanWindow(1, 2)),))
    results = make_device(link, plan).run(scans=4, interval_ms=1000)

    assert [r.delivered for r in results] == [True, False, False, True]
    # Four records in, four out: nothing was lost, and the buffered pair is
    # replayed before the scan that found the link up again.
    uptimes = [decode(decode_frame(f).payload, schema)["up"] for f in sink.frames]
    assert uptimes == [0, 1000, 2000, 3000]
    assert [d.uptime_ms for d in sink.deliveries] == [0, 1000, 2000, 3000]
    assert [d.replayed for d in sink.deliveries] == [False, True, True, False]


def test_the_health_signals_report_the_outage(make_device, link, signal_list):
    plan = FaultPlan(link_drops=(LinkDrop(ScanWindow(1, 2)),))
    results = make_device(link, plan).run(scans=4, interval_ms=1000)
    link_signal = signal_list.by_name("health_cloud_link_up")
    buffer_signal = signal_list.by_name("health_log_buffer_used")

    def value(result, signal_id):
        return next(r for r in result.record.readings if r.signal_id == signal_id).value

    assert [value(r, link_signal.id) for r in results] == [True, False, False, True]
    # The log fills during the outage and is empty again after the replay.
    assert value(results[0], buffer_signal.id) == 0
    assert value(results[2], buffer_signal.id) > 0
    assert value(results[3], buffer_signal.id) == 0


def test_a_record_buffered_before_sntp_keeps_no_unix_time(make_device, link, sink):
    plan = FaultPlan(link_drops=(LinkDrop(ScanWindow(0, 0)),))
    make_device(link, plan, sntp_sync_after_ms=1500).run(scans=2, interval_ms=1000)
    assert [d.unix_time_s for d in sink.deliveries] == [None, None]


# -- readings the plant model cannot produce ------------------------------


class _StubPlant:
    """A plant that reports the same status for every signal."""

    def __init__(self, status: str) -> None:
        self._status = status

    def sample(self, signal, state):
        from tanksim.plant import Sample

        return Sample(value=None, status=self._status)


def _device_with_plant(signal_list, link, schema, status):
    from tanksim.clock import SimClock

    return SimulatedDevice(
        device_id="SIM-STUB",
        signal_list=signal_list,
        link=link,
        clock=SimClock(boot_unix_s=0),
        plant=_StubPlant(status),
        schema=schema,
        boot_id=bytes(BOOT_ID_BYTES),
    )


def test_a_signal_the_model_cannot_produce_is_unconfigured(signal_list, link, schema, quality):
    # "Channel present in hardware but not commissioned": the record still
    # carries the id, with no value, so a consumer can say why there is no
    # reading rather than showing a gap.
    device = _device_with_plant(signal_list, link, schema, "unconfigured")
    readings = device.scan().record.readings
    assert {r.quality for r in readings} == {quality.unconfigured}
    assert all(r.value is None for r in readings)


def test_a_signal_the_model_reports_as_failed_is_a_fault(signal_list, link, schema, quality):
    # A bus failure is a fault, not an uncommissioned channel: the two are
    # different things on a screen, so the status decides and not the missing
    # value.
    device = _device_with_plant(signal_list, link, schema, "fault")
    readings = device.scan().record.readings
    assert {r.quality for r in readings} == {quality.fault}
    assert all(r.value is None for r in readings)


def test_the_device_reports_its_identity_and_progress(make_device, link, device_id, boot_id):
    device = make_device(link)
    assert device.device_id == device_id
    assert device.boot_id == boot_id
    assert device.scans_done == 0
    device.run(scans=2, interval_ms=1000)
    assert device.scans_done == 2


def test_one_command_starts_the_simulator():
    # The story's third acceptance criterion, checked the way a person would:
    # run the command in a fresh interpreter and see records come out.
    import subprocess
    import sys

    completed = subprocess.run(
        [sys.executable, "-m", "tanksim", "--scans", "2"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "scan seq=0" in completed.stdout
    assert "scan seq=1" in completed.stdout
