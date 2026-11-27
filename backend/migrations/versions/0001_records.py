"""Scan records and their readings (S-068).

Revision ID: 0001
Revises:
Create Date: 2026-11-27

The check constraints repeat the decoder's rules (``tankapi.records``). Like
every migration they are a frozen snapshot: the quality codes are written out
here rather than imported, so a later change to the code cannot rewrite what
this revision created. Plain SQL, valid in SQLite and Postgres.
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

ROW_ID = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
BOOT_ID_BYTES = 16
DEVICE_ID_MAX_BYTES = 64
# interfaces/records.cddl quality-values: good 0 ... unconfigured 4. Fault (3)
# and unconfigured (4) carry no value; every other quality carries exactly one.
QUALITY_MAX = 4
QUALITIES_WITHOUT_VALUE = "3, 4"
VALUE_MATCHES_QUALITY = (
    f"(quality IN ({QUALITIES_WITHOUT_VALUE}) AND value_int IS NULL AND value_bool IS NULL)"
    f" OR (quality NOT IN ({QUALITIES_WITHOUT_VALUE})"
    " AND (value_int IS NULL) <> (value_bool IS NULL))"
)
TIME_WHEN_KNOWN = (
    "(time_known AND unix_time_s IS NOT NULL) OR (NOT time_known AND unix_time_s IS NULL)"
)


def _ck(table: str, name: str, condition: str) -> sa.CheckConstraint:
    # op.f(): the full name is final, so no naming convention rewrites it.
    return sa.CheckConstraint(condition, name=op.f(f"ck_{table}_{name}"))


def _uint(table: str, *columns: str) -> list[sa.CheckConstraint]:
    return [_ck(table, f"{column}_uint", f"{column} >= 0") for column in columns]


def upgrade() -> None:
    op.create_table(
        "scan_records",
        sa.Column("id", ROW_ID, nullable=False),
        sa.Column("device_id", sa.String(DEVICE_ID_MAX_BYTES), nullable=False),
        sa.Column("signal_list_version", sa.BigInteger(), nullable=False),
        sa.Column("boot_id", sa.LargeBinary(BOOT_ID_BYTES), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("uptime_ms", sa.BigInteger(), nullable=False),
        sa.Column("time_known", sa.Boolean(), nullable=False),
        sa.Column("unix_time_s", sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scan_records")),
        # The de-duplication key: one row per scan, however often it is delivered.
        sa.UniqueConstraint(
            "device_id", "boot_id", "sequence", name=op.f("uq_scan_records_device_id")
        ),
        _ck("scan_records", "device_id_not_empty", "length(device_id) >= 1"),
        _ck("scan_records", "boot_id_size", f"length(boot_id) = {BOOT_ID_BYTES}"),
        _ck("scan_records", "time", TIME_WHEN_KNOWN),
        *_uint("scan_records", "signal_list_version", "sequence", "uptime_ms", "unix_time_s"),
    )
    op.create_table(
        "readings",
        sa.Column("scan_record_id", ROW_ID, nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("signal_id", sa.BigInteger(), nullable=False),
        sa.Column("quality", sa.SmallInteger(), nullable=False),
        sa.Column("age_ms", sa.BigInteger(), nullable=False),
        sa.Column("value_int", sa.BigInteger(), nullable=True),
        sa.Column("value_bool", sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint("scan_record_id", "position", name=op.f("pk_readings")),
        sa.ForeignKeyConstraint(
            ["scan_record_id"], ["scan_records.id"], name=op.f("fk_readings_scan_record_id")
        ),
        _ck("readings", "quality_known", f"quality BETWEEN 0 AND {QUALITY_MAX}"),
        _ck("readings", "value_matches_quality", VALUE_MATCHES_QUALITY),
        *_uint("readings", "position", "signal_id", "age_ms"),
    )


def downgrade() -> None:
    op.drop_table("readings")
    op.drop_table("scan_records")
