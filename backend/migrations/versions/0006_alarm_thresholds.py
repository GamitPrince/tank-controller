"""Each tank's advisory alarm thresholds (S-087, P1-18).

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-27

One row is one limit: a high or a low, of one class (critical, warning or
advisory), on one stored signal or on the level % computed from the radar
(S-086). ``limit_value`` and ``deadband`` are whole numbers in the measure's
stored unit: the signal's transmitted unit (``interfaces/signals-v1.yaml``,
microamps or centi-degrees) or hundredths of a percent. A threshold holds over
``[valid_from_unix_s, valid_to_unix_s)`` like a level configuration (S-085),
so a change closes one row and opens the next, and at most one row per tank,
measure, signal, direction and class is open.

Only the eight analogue signals of signal list v1 take a threshold, never a
digital contact: the device's own alarm and trip contacts stay separate
signals. Like 0003, a frozen snapshot valid in SQLite and Postgres.
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

ROW_ID = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
TABLE = "alarm_thresholds"
OPEN = "valid_to_unix_s IS NULL"
KEY = ["tank_id", "measure", "signal_id", "direction", "alarm_class"]
# signals-v1.yaml: radar and pressure loop current, the six PT100s.
ANALOGUE_SIGNALS = "1001, 1002, 2001, 2002, 2003, 2004, 2005, 2006"
RADAR_SIGNAL = 1001
# A level % threshold in hundredths of a percent: 0 to 100 %.
LEVEL_FULL = 10_000


def _ck(name: str, condition: str) -> sa.CheckConstraint:
    # op.f(): the full name is final, so no naming convention rewrites it.
    return sa.CheckConstraint(condition, name=op.f(f"ck_{TABLE}_{name}"))


def upgrade() -> None:
    level = "measure = 'level_percent'"
    op.create_table(
        TABLE,
        sa.Column("id", ROW_ID, nullable=False),
        sa.Column("tank_id", ROW_ID, nullable=False),
        sa.Column("measure", sa.String(16), nullable=False),
        sa.Column("signal_id", sa.BigInteger(), nullable=False),
        sa.Column("direction", sa.String(8), nullable=False),
        sa.Column("alarm_class", sa.String(16), nullable=False),
        sa.Column("limit_value", sa.BigInteger(), nullable=False),
        sa.Column("deadband", sa.BigInteger(), nullable=False),
        sa.Column("valid_from_unix_s", sa.BigInteger(), nullable=False),
        sa.Column("valid_to_unix_s", sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{TABLE}")),
        sa.ForeignKeyConstraint(["tank_id"], ["tanks.id"], name=op.f(f"fk_{TABLE}_tank_id")),
        sa.UniqueConstraint(*KEY, "valid_from_unix_s", name=op.f(f"uq_{TABLE}_tank_id")),
        _ck("measure_known", "measure IN ('signal', 'level_percent')"),
        _ck("signal_analogue", f"signal_id IN ({ANALOGUE_SIGNALS})"),
        _ck("level_from_radar", f"NOT ({level}) OR signal_id = {RADAR_SIGNAL}"),
        _ck("direction_known", "direction IN ('high', 'low')"),
        _ck("class_known", "alarm_class IN ('critical', 'warning', 'advisory')"),
        _ck("deadband_uint", "deadband >= 0"),
        _ck(
            "level_within_tank",
            f"NOT ({level}) OR (limit_value BETWEEN 0 AND {LEVEL_FULL}"
            f" AND deadband <= {LEVEL_FULL})",
        ),
        _ck("valid_from_uint", "valid_from_unix_s >= 0"),
        _ck("ends_after_start", f"{OPEN} OR valid_to_unix_s > valid_from_unix_s"),
    )
    op.create_index(
        op.f(f"ix_{TABLE}_open"),
        TABLE,
        KEY,
        unique=True,
        sqlite_where=sa.text(OPEN),
        postgresql_where=sa.text(OPEN),
    )


def downgrade() -> None:
    op.drop_table(TABLE)
