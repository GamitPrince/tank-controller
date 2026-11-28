"""Raised and cleared advisory alarms, recorded from newly stored scans (S-090, P1-18).

These alarms are reports for people, never actions: nothing here writes to a
device or to the hardwired safety chain (AGENTS.md section 1).

:func:`record_alarm_events` runs inside the ingest transaction, after a
message's records are stored (S-070), on the scans that were new. A duplicate
is skipped before it gets here, so it never raises an alarm twice, and an
event is committed only with the scan it was judged from ``[Confirm]``.

Each scan is judged against the thresholds of the tank its device was on at
the scan's ``t`` (S-074, S-089), with S-088's rule and the alarm's last state,
and one ``alarm_events`` row is added only when that state changes. A scan is
judged at its own time, so a backlog replayed after an outage raises and clears
alarms as it happened: a reading is stale when the device marked it so or its
``age`` is past S-083's limit, never because it arrived late ``[Confirm]``. A
scan with no time, or one ahead of the server clock, moves every alarm of the
device's tank (at its newest judged scan) to ``cannot_evaluate``.

A device forwards its log oldest first, so scans normally arrive in order. A
scan older than one already judged for its device is stored but not judged,
and logged, because the history cannot be rewritten ``[Confirm]``.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tankapi.alarm_rules import (
    AlarmState,
    Measure,
    Sample,
    Threshold,
    Unavailable,
    evaluate,
    level_sample,
    reading_sample,
)
from tankapi.db import AlarmEventRow, AlarmThresholdRow, ScanRow
from tankapi.liveness import Liveness, StaleRules, reading_liveness
from tankapi.ownership import OverlappingAssignmentsError, Unowned, owner_at
from tankapi.records import Reading
from tankapi.tank_level import LevelState, TankLevel, tank_level
from tankapi.thresholds import AlarmKey, ThresholdError, ThresholdInForce, thresholds_at

log = logging.getLogger(__name__)

RAISED = frozenset({AlarmState.HIGH, AlarmState.LOW})


class _History:
    """Each alarm's last state and whether it was last judged raised, read once per message."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._known: dict[AlarmKey, tuple[AlarmState, bool]] = {}

    def get(self, key: AlarmKey) -> tuple[AlarmState, bool]:
        if key not in self._known:
            latest = self._latest(key, judged_only=False)
            self._known[key] = (latest or AlarmState.NORMAL, self._latest(key, True) in RAISED)
        return self._known[key]

    def set(self, key: AlarmKey, state: AlarmState) -> None:
        raised = self._known[key][1] if state is AlarmState.CANNOT_EVALUATE else state in RAISED
        self._known[key] = (state, raised)

    def _latest(self, key: AlarmKey, judged_only: bool) -> AlarmState | None:
        tank_id, measure, signal_id, direction, alarm_class = key
        query = (
            select(AlarmEventRow.state)
            .join(AlarmThresholdRow, AlarmThresholdRow.id == AlarmEventRow.threshold_id)
            .where(
                AlarmThresholdRow.tank_id == tank_id,
                AlarmThresholdRow.measure == measure,
                AlarmThresholdRow.signal_id == signal_id,
                AlarmThresholdRow.direction == direction,
                AlarmThresholdRow.alarm_class == alarm_class,
            )
            .order_by(AlarmEventRow.id.desc())
            .limit(1)
        )
        if judged_only:
            query = query.where(AlarmEventRow.state != AlarmState.CANNOT_EVALUATE.value)
        state = self._session.scalar(query)
        return None if state is None else AlarmState(state)


def record_alarm_events(
    session: Session, scans: Sequence[ScanRow], now_s: float, rules: StaleRules
) -> int:
    """Judge the newly stored ``scans``, oldest first, and add a row per change of state."""
    history = _History(session)
    newest: dict[str, int | None] = {}
    added = 0
    for scan in scans:
        device = scan.device_id
        if device not in newest:
            newest[device] = _newest_judged(session, device, scans, now_s, rules)
        t, seen = scan.unix_time_s, newest[device]
        credible = t is not None and t - now_s <= rules.clock_ahead_s
        if credible and seen is not None and t < seen:
            log.warning(
                "scan %s of device %s is older than one judged: not judged", scan.id, device
            )
            continue
        if credible:
            newest[device] = t
        at = t if t is not None else seen
        if at is not None:
            added += _judge(session, scan, at, credible, now_s, rules, history)
    return added


def _newest_judged(
    session: Session, device_id: str, scans: Sequence[ScanRow], now_s: float, rules: StaleRules
) -> int | None:
    """The newest credible time among the device's scans stored before this message."""
    query = select(func.max(ScanRow.unix_time_s)).where(
        ScanRow.device_id == device_id,
        ScanRow.id.not_in([scan.id for scan in scans]),
        ScanRow.unix_time_s <= now_s + rules.clock_ahead_s,
    )
    return session.scalar(query)


def _judge(
    session: Session,
    scan: ScanRow,
    at: int,
    credible: bool,
    now_s: float,
    rules: StaleRules,
    history: _History,
) -> int:
    """Judge one scan against the thresholds of its device's tank at ``at``."""
    try:
        owner = owner_at(session, scan.device_id, at)
        found = [] if isinstance(owner, Unowned) else thresholds_at(session, owner.tank_id, at)
    except (OverlappingAssignmentsError, ThresholdError) as error:
        log.error("alarms of scan %s of device %s not judged: %s", scan.id, scan.device_id, error)
        return 0
    readings = {row.signal_id: row.to_reading() for row in scan.readings}
    added = 0
    for item in found:
        reading = readings.get(item.threshold.signal_id)
        sample = _sample(session, scan, item.threshold, reading, credible, rules)
        added += _record(session, scan, item, sample, reading, history)
    return added


def _sample(
    session: Session,
    scan: ScanRow,
    threshold: Threshold,
    reading: Reading | None,
    credible: bool,
    rules: StaleRules,
) -> Sample:
    """The threshold's value from this scan, judged at the scan's own time."""
    t = scan.unix_time_s
    if not credible or t is None:
        return Sample(threshold.measure, threshold.signal_id, None, Unavailable.TIME_UNKNOWN)
    if threshold.measure is Measure.SIGNAL:
        liveness = Liveness.LIVE if reading is None else reading_liveness(t, reading, t, rules)
        return reading_sample(threshold.signal_id, reading, liveness)
    radar = None if reading is None else (t, reading)
    try:
        return level_sample(tank_level(session, scan.device_id, radar, t, rules))
    except HTTPException:
        # tank_level has logged the broken configuration; level % cannot be computed.
        return level_sample(TankLevel(status=LevelState.UNCONFIGURED))


def _record(
    session: Session,
    scan: ScanRow,
    item: ThresholdInForce,
    sample: Sample,
    reading: Reading | None,
    history: _History,
) -> int:
    """Add an event if the alarm's state changes; a cannot-evaluate never clears it."""
    previous, raised = history.get(item.key)
    result = evaluate(item.threshold, sample, active=raised)
    if result.state is previous:
        return 0
    history.set(item.key, result.state)
    session.add(
        AlarmEventRow(
            threshold_id=item.id,
            scan_record_id=scan.id,
            unix_time_s=scan.unix_time_s,
            state=result.state.value,
            reason=None if result.reason is None else result.reason.value,
            value=None if result.reason is not None else float(sample.value),
            quality=None if reading is None else int(reading.quality),
            limit_value=item.threshold.limit,
            deadband=item.threshold.deadband,
        )
    )
    return 1
