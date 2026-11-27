"""Level % and volume from a device's newest radar reading, computed on read (S-086).

ADR-0004 decision 10 computes level % and volume in the backend; the device
sends only the radar loop current (signal 1001). The figures are computed each
time they are asked for, with ``compute_level`` (S-082) and the level
configuration of the tank the device was on at the reading's scan time
(S-074, S-085), and never stored as if measured.

Only a live, good, in-range reading on a configured tank gives figures. Any
other case gives a ``status`` saying why and no figures, never a substitute
or an earlier value: ``no_reading`` (no radar reading to use), ``unconfigured``
(no tank, or no configuration for this calculation version), ``stale`` or
``time_unknown`` (S-083's liveness), and S-082's ``fault`` and
``out_of_range``. Overlapping assignments or configurations, or a stored table
``StrappingTable`` refuses, are refused with 500 rather than guessed.
"""

import logging
from enum import Enum

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from tankapi.level import CALCULATION_VERSION, compute_level
from tankapi.level_config import LevelConfig, LevelConfigError, level_config_at
from tankapi.liveness import Liveness, StaleRules, reading_liveness
from tankapi.ownership import OverlappingAssignmentsError, Unowned, owner_at
from tankapi.readings import HTTP_SERVER_ERROR, QualityName
from tankapi.records import Reading

log = logging.getLogger(__name__)


class LevelState(str, Enum):
    """Why the figures are there or not; only ``ok`` carries them."""

    OK = "ok"
    FAULT = "fault"
    OUT_OF_RANGE = "out_of_range"
    STALE = "stale"
    TIME_UNKNOWN = "time_unknown"
    UNCONFIGURED = "unconfigured"
    NO_READING = "no_reading"


_STATE_FOR_LIVENESS = {
    Liveness.STALE: LevelState.STALE,
    Liveness.TIME_UNKNOWN: LevelState.TIME_UNKNOWN,
}


class TankLevel(BaseModel):
    """The radar reading used, as stored, and the figures computed from it."""

    status: LevelState
    t: int | None = None
    quality: QualityName | None = None
    age_ms: int | None = None
    liveness: Liveness | None = None
    level_mm: float | None = None
    level_percent: float | None = None
    volume_l: float | None = None
    table_version: int | None = None
    calculation_version: int = CALCULATION_VERSION


def tank_level(
    session: Session,
    device_id: str,
    radar: tuple[int, Reading] | None,
    now: float,
    rules: StaleRules,
) -> TankLevel:
    """The level of the device's tank at the time ``t`` of its newest radar reading."""
    if radar is None:
        return TankLevel(status=LevelState.NO_READING)
    t, reading = radar
    liveness = reading_liveness(t, reading, now, rules)
    quality = reading.quality.name.lower()
    seen = {"t": t, "quality": quality, "age_ms": reading.age_ms, "liveness": liveness}
    config = _config(session, device_id, t)
    if config is None:
        return TankLevel(status=LevelState.UNCONFIGURED, **seen)
    if liveness is not Liveness.LIVE:
        state = _STATE_FOR_LIVENESS[liveness]
        return TankLevel(status=state, table_version=config.table.version, **seen)
    result = compute_level(reading, config.table)
    return TankLevel(
        status=LevelState(result.status.value),
        level_mm=result.level_mm,
        level_percent=result.level_percent,
        volume_l=result.volume_l,
        table_version=result.table_version,
        calculation_version=result.calculation_version,
        **seen,
    )


def _config(session: Session, device_id: str, t: int) -> LevelConfig | None:
    """The configuration of the device's tank at ``t``, if it is for this calculation version."""
    try:
        owner = owner_at(session, device_id, t)
        if isinstance(owner, Unowned):
            return None
        config = level_config_at(session, owner.tank_id, t)
    except (OverlappingAssignmentsError, LevelConfigError) as error:
        log.error("level refused for device %s: %s", device_id, error)
        raise HTTPException(HTTP_SERVER_ERROR, "server error") from None
    if config is None or config.calculation_version != CALCULATION_VERSION:
        return None
    return config
