"""The database tables for decoded records (S-068, S-069).

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

Only the mapping lives here. Writing records, de-duplication and ingest are
later stories.
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Integer,
    LargeBinary,
    MetaData,
    SmallInteger,
    String,
    UniqueConstraint,
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
