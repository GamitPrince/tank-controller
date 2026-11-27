"""The database tables for decoded records (S-068, S-069) and device ownership (S-073).

Three tables hold everything :func:`tankapi.records.decode_message` returns:
``scan_records`` (one row per scan), ``readings`` (one row per reading, in the
order the device sent them) and ``gap_records`` (S-069). The schema itself is created by
the Alembic migrations under ``backend/migrations/``; these models must match
them, which ``tests/test_db_migrations.py`` checks.

The migration repeats the decoder's rules as check constraints, so a row the
decoder would refuse cannot be stored either: a faulted or unconfigured reading
has no value (NULL, never a substitute, AGENTS.md section 7), every other
reading has exactly one, and ``unix_time_s`` is present exactly when
``time_known`` is true, in scans and in both marks of a gap. A gap record
marks scans that will never arrive; nothing may interpolate across one (S-040).

Ownership follows ADR-0007's customer > plant > tank > device (S-073). A device
is keyed by the ID its records carry, but the record tables keep their own
``device_id`` with no foreign key, so a record from an unregistered or
unclaimed device is still stored. ``device_assignments`` keeps history: a move
closes one row and opens the next, so a reading still belongs to the tank it was
taken on.

``audit_entries`` is the append-only audit trail (S-079): its migration's
triggers refuse UPDATE and DELETE. ``tankapi.audit`` writes it (S-080).

``level_configurations`` and ``strapping_points`` hold each tank's level
configuration with its history (S-085). Nothing reads them yet (S-086).

Only the mapping lives here. Writing records, de-duplication and ingest are
later stories.
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from tankapi.records import (
    BOOT_ID_BYTES,
    DEVICE_ID_MAX_BYTES,
    GapRecord,
    LostScan,
    Quality,
    Reading,
    ScanRecord,
)

# SQLite only auto-numbers an INTEGER primary key; Postgres gets BIGINT.
ROW_ID = BigInteger().with_variant(Integer(), "sqlite")

# Named constraints, so a later migration can drop or change them by name.
NAMING_CONVENTION = {
    "pk": "pk_%(table_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
}

NAME_MAX_CHARS = 100
# A Cognito sub is a 36-character UUID; a route template is a path.
SUBJECT_MAX_CHARS = 128
ROLE_MAX_CHARS = 16
METHOD_MAX_CHARS = 8
ROUTE_MAX_CHARS = 200
# An assignment with no end is the device's current one; a device has at most one.
OPEN_ASSIGNMENT = text("valid_to_unix_s IS NULL")
# Likewise a tank has at most one current level configuration (S-085).
OPEN_CONFIGURATION = OPEN_ASSIGNMENT


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class ScanRow(Base):
    """One scan record. ``(device_id, boot_id, sequence)`` is unique, for de-duplication."""

    __tablename__ = "scan_records"
    __table_args__ = (UniqueConstraint("device_id", "boot_id", "sequence"),)

    id: Mapped[int] = mapped_column(ROW_ID, primary_key=True)
    device_id: Mapped[str] = mapped_column(String(DEVICE_ID_MAX_BYTES))
    signal_list_version: Mapped[int] = mapped_column(BigInteger)
    boot_id: Mapped[bytes] = mapped_column(LargeBinary(BOOT_ID_BYTES))
    sequence: Mapped[int] = mapped_column(BigInteger)
    uptime_ms: Mapped[int] = mapped_column(BigInteger)
    time_known: Mapped[bool] = mapped_column(Boolean)
    unix_time_s: Mapped[int | None] = mapped_column(BigInteger)
    readings: Mapped[list[ReadingRow]] = relationship(
        order_by="ReadingRow.position", cascade="all, delete-orphan"
    )

    @classmethod
    def from_record(cls, record: ScanRecord) -> ScanRow:
        return cls(
            device_id=record.device_id,
            signal_list_version=record.signal_list_version,
            boot_id=record.boot_id,
            sequence=record.sequence,
            uptime_ms=record.uptime_ms,
            time_known=record.time_known,
            unix_time_s=record.unix_time_s,
            readings=[ReadingRow.from_reading(r, n) for n, r in enumerate(record.readings)],
        )

    def to_record(self) -> ScanRecord:
        return ScanRecord(
            device_id=self.device_id,
            signal_list_version=self.signal_list_version,
            boot_id=self.boot_id,
            sequence=self.sequence,
            uptime_ms=self.uptime_ms,
            time_known=self.time_known,
            unix_time_s=self.unix_time_s,
            readings=tuple(row.to_reading() for row in self.readings),
        )


class ReadingRow(Base):
    """One reading. A bool value goes in ``value_bool``, an integer in ``value_int``."""

    __tablename__ = "readings"

    scan_record_id: Mapped[int] = mapped_column(ForeignKey("scan_records.id"), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    signal_id: Mapped[int] = mapped_column(BigInteger)
    quality: Mapped[int] = mapped_column(SmallInteger)
    age_ms: Mapped[int] = mapped_column(BigInteger)
    value_int: Mapped[int | None] = mapped_column(BigInteger)
    value_bool: Mapped[bool | None] = mapped_column(Boolean)

    @classmethod
    def from_reading(cls, reading: Reading, position: int) -> ReadingRow:
        # bool is checked first: in Python a bool is also an int.
        is_bool = isinstance(reading.value, bool)
        return cls(
            position=position,
            signal_id=reading.signal_id,
            quality=int(reading.quality),
            age_ms=reading.age_ms,
            value_int=None if is_bool else reading.value,
            value_bool=reading.value if is_bool else None,
        )

    def to_reading(self) -> Reading:
        value = self.value_bool if self.value_bool is not None else self.value_int
        return Reading(self.signal_id, Quality(self.quality), self.age_ms, value)


class GapRow(Base):
    """One gap record: ``lost`` scans from ``first`` to ``last`` were dropped."""

    __tablename__ = "gap_records"

    id: Mapped[int] = mapped_column(ROW_ID, primary_key=True)
    device_id: Mapped[str] = mapped_column(String(DEVICE_ID_MAX_BYTES))
    lost: Mapped[int] = mapped_column(BigInteger)
    first_boot_id: Mapped[bytes] = mapped_column(LargeBinary(BOOT_ID_BYTES))
    first_sequence: Mapped[int] = mapped_column(BigInteger)
    first_uptime_ms: Mapped[int] = mapped_column(BigInteger)
    first_time_known: Mapped[bool] = mapped_column(Boolean)
    first_unix_time_s: Mapped[int | None] = mapped_column(BigInteger)
    last_boot_id: Mapped[bytes] = mapped_column(LargeBinary(BOOT_ID_BYTES))
    last_sequence: Mapped[int] = mapped_column(BigInteger)
    last_uptime_ms: Mapped[int] = mapped_column(BigInteger)
    last_time_known: Mapped[bool] = mapped_column(Boolean)
    last_unix_time_s: Mapped[int | None] = mapped_column(BigInteger)

    @classmethod
    def from_record(cls, record: GapRecord) -> GapRow:
        return cls(
            device_id=record.device_id,
            lost=record.lost,
            **_mark_columns("first", record.first),
            **_mark_columns("last", record.last),
        )

    def to_record(self) -> GapRecord:
        return GapRecord(self.device_id, self.lost, self._mark("first"), self._mark("last"))

    def _mark(self, end: str) -> LostScan:
        return LostScan(
            boot_id=getattr(self, f"{end}_boot_id"),
            sequence=getattr(self, f"{end}_sequence"),
            uptime_ms=getattr(self, f"{end}_uptime_ms"),
            time_known=getattr(self, f"{end}_time_known"),
            unix_time_s=getattr(self, f"{end}_unix_time_s"),
        )


def _mark_columns(end: str, mark: LostScan) -> dict[str, object]:
    return {
        f"{end}_boot_id": mark.boot_id,
        f"{end}_sequence": mark.sequence,
        f"{end}_uptime_ms": mark.uptime_ms,
        f"{end}_time_known": mark.time_known,
        f"{end}_unix_time_s": mark.unix_time_s,
    }


class CustomerRow(Base):
    """A customer: no user, query or device crosses from one to another (ADR-0007)."""

    __tablename__ = "customers"
    __table_args__ = (UniqueConstraint("name"),)

    id: Mapped[int] = mapped_column(ROW_ID, primary_key=True)
    name: Mapped[str] = mapped_column(String(NAME_MAX_CHARS))


class PlantRow(Base):
    """A plant of one customer, its name unique within that customer."""

    __tablename__ = "plants"
    __table_args__ = (UniqueConstraint("customer_id", "name"),)

    id: Mapped[int] = mapped_column(ROW_ID, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    name: Mapped[str] = mapped_column(String(NAME_MAX_CHARS))


class TankRow(Base):
    """A tank in one plant, its name unique within that plant."""

    __tablename__ = "tanks"
    __table_args__ = (UniqueConstraint("plant_id", "name"),)

    id: Mapped[int] = mapped_column(ROW_ID, primary_key=True)
    plant_id: Mapped[int] = mapped_column(ForeignKey("plants.id"))
    name: Mapped[str] = mapped_column(String(NAME_MAX_CHARS))


class DeviceRow(Base):
    """A known device, by the ``device-id`` its records carry (``interfaces/records.cddl``)."""

    __tablename__ = "devices"

    device_id: Mapped[str] = mapped_column(String(DEVICE_ID_MAX_BYTES), primary_key=True)


class AssignmentRow(Base):
    """A device on a tank over ``[valid_from_unix_s, valid_to_unix_s)``; no end: still there."""

    __tablename__ = "device_assignments"
    __table_args__ = (
        UniqueConstraint("device_id", "valid_from_unix_s"),
        Index(
            "ix_device_assignments_open",
            "device_id",
            unique=True,
            sqlite_where=OPEN_ASSIGNMENT,
            postgresql_where=OPEN_ASSIGNMENT,
        ),
    )

    id: Mapped[int] = mapped_column(ROW_ID, primary_key=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.device_id"))
    tank_id: Mapped[int] = mapped_column(ForeignKey("tanks.id"))
    valid_from_unix_s: Mapped[int] = mapped_column(BigInteger)
    valid_to_unix_s: Mapped[int | None] = mapped_column(BigInteger)


class LevelConfigRow(Base):
    """A tank's transducer range, full height and strapping table over
    ``[valid_from_unix_s, valid_to_unix_s)``, for one calculation version (S-085)."""

    __tablename__ = "level_configurations"
    __table_args__ = (
        UniqueConstraint("tank_id", "version", name="uq_level_configurations_tank_id"),
        UniqueConstraint(
            "tank_id", "valid_from_unix_s", name="uq_level_configurations_tank_id_valid_from"
        ),
        Index(
            "ix_level_configurations_open",
            "tank_id",
            unique=True,
            sqlite_where=OPEN_CONFIGURATION,
            postgresql_where=OPEN_CONFIGURATION,
        ),
    )

    id: Mapped[int] = mapped_column(ROW_ID, primary_key=True)
    tank_id: Mapped[int] = mapped_column(ForeignKey("tanks.id"))
    version: Mapped[int] = mapped_column(Integer)
    calculation_version: Mapped[int] = mapped_column(Integer)
    valid_from_unix_s: Mapped[int] = mapped_column(BigInteger)
    valid_to_unix_s: Mapped[int | None] = mapped_column(BigInteger)
    range_low_mm: Mapped[float] = mapped_column(Float)
    range_high_mm: Mapped[float] = mapped_column(Float)
    max_height_mm: Mapped[float] = mapped_column(Float)
    points: Mapped[list[StrappingPointRow]] = relationship(order_by="StrappingPointRow.position")


class StrappingPointRow(Base):
    """One ``(height_mm, volume_l)`` point. The ``previous_*`` columns repeat the point
    before it, so the migration's checks can refuse one that does not rise (S-085)."""

    __tablename__ = "strapping_points"
    __table_args__ = (
        UniqueConstraint("configuration_id", "position", "height_mm", "volume_l"),
        ForeignKeyConstraint(
            ["configuration_id", "previous_position", "previous_height_mm", "previous_volume_l"],
            [
                "strapping_points.configuration_id",
                "strapping_points.position",
                "strapping_points.height_mm",
                "strapping_points.volume_l",
            ],
            name="fk_strapping_points_previous_point",
        ),
    )

    configuration_id: Mapped[int] = mapped_column(
        ForeignKey("level_configurations.id"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    height_mm: Mapped[float] = mapped_column(Float)
    volume_l: Mapped[float] = mapped_column(Float)
    previous_position: Mapped[int | None] = mapped_column(Integer)
    previous_height_mm: Mapped[float | None] = mapped_column(Float)
    previous_volume_l: Mapped[float | None] = mapped_column(Float)


class AuditRow(Base):
    """One ``/v1`` request by a service caller; ``query`` is a JSON object of its selecting
    parameters. The database refuses UPDATE and DELETE (S-079)."""

    __tablename__ = "audit_entries"

    id: Mapped[int] = mapped_column(ROW_ID, primary_key=True)
    at_unix_ms: Mapped[int] = mapped_column(BigInteger)
    subject: Mapped[str] = mapped_column(String(SUBJECT_MAX_CHARS))
    role: Mapped[str] = mapped_column(String(ROLE_MAX_CHARS))
    method: Mapped[str] = mapped_column(String(METHOD_MAX_CHARS))
    route: Mapped[str] = mapped_column(String(ROUTE_MAX_CHARS))
    device_id: Mapped[str | None] = mapped_column(String(DEVICE_ID_MAX_BYTES))
    query: Mapped[str] = mapped_column(Text)
    status: Mapped[int] = mapped_column(SmallInteger)
