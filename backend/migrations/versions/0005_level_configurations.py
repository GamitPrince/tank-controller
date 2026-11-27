"""A tank's level configuration and its strapping points (S-085).

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-27

What ``tankapi.level.compute_level`` needs (S-082): the transducer range, the
tank's full height and a strapping table, plus the calculation version the
configuration is used with (ADR-0007 decision 9). A configuration holds over
``[valid_from_unix_s, valid_to_unix_s)`` like a device assignment (S-073), so a
correction opens a new row and an old reading keeps the configuration in force
at its scan time; at most one row per tank is open.

Each strapping point repeats the previous point's position, height and volume,
and a composite foreign key ties them to that row, so a check constraint can
refuse a point that does not rise in both height and volume. The chain also
makes the points contiguous from position 0. The point count and the last
point against the full height are checked when the configuration is read.
Every number has a ceiling far above any tank, because Postgres sorts NaN and
infinity above every number. Like 0003, a frozen snapshot valid in SQLite and
Postgres; nothing cascades a delete.
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

ROW_ID = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
CONFIGS = "level_configurations"
POINTS = "strapping_points"
OPEN = "valid_to_unix_s IS NULL"
CEILING = "1e9"


def _ck(table: str, name: str, condition: str) -> sa.CheckConstraint:
    # op.f(): the full name is final, so no naming convention rewrites it.
    return sa.CheckConstraint(condition, name=op.f(f"ck_{table}_{name}"))


def _bounded(column: str, low: str) -> str:
    return f"{column} {low} AND {column} <= {CEILING}"


def _configurations() -> None:
    op.create_table(
        CONFIGS,
        sa.Column("id", ROW_ID, nullable=False),
        sa.Column("tank_id", ROW_ID, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("calculation_version", sa.Integer(), nullable=False),
        sa.Column("valid_from_unix_s", sa.BigInteger(), nullable=False),
        sa.Column("valid_to_unix_s", sa.BigInteger(), nullable=True),
        sa.Column("range_low_mm", sa.Float(), nullable=False),
        sa.Column("range_high_mm", sa.Float(), nullable=False),
        sa.Column("max_height_mm", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{CONFIGS}")),
        sa.ForeignKeyConstraint(["tank_id"], ["tanks.id"], name=op.f(f"fk_{CONFIGS}_tank_id")),
        sa.UniqueConstraint("tank_id", "version", name=op.f(f"uq_{CONFIGS}_tank_id")),
        sa.UniqueConstraint(
            "tank_id", "valid_from_unix_s", name=op.f(f"uq_{CONFIGS}_tank_id_valid_from")
        ),
        _ck(CONFIGS, "version_positive", "version >= 1"),
        _ck(CONFIGS, "calculation_version_positive", "calculation_version >= 1"),
        _ck(CONFIGS, "valid_from_uint", "valid_from_unix_s >= 0"),
        _ck(CONFIGS, "ends_after_start", f"{OPEN} OR valid_to_unix_s > valid_from_unix_s"),
        _ck(CONFIGS, "range_rises", "range_low_mm >= 0 AND range_high_mm > range_low_mm"),
        _ck(CONFIGS, "range_finite", f"range_high_mm <= {CEILING}"),
        _ck(CONFIGS, "max_height_finite", _bounded("max_height_mm", "> 0")),
    )
    op.create_index(
        op.f(f"ix_{CONFIGS}_open"),
        CONFIGS,
        ["tank_id"],
        unique=True,
        sqlite_where=sa.text(OPEN),
        postgresql_where=sa.text(OPEN),
    )


def _points() -> None:
    rises = (
        "previous_position = position - 1"
        " AND height_mm > previous_height_mm AND volume_l > previous_volume_l"
    )
    first = "previous_position IS NULL AND previous_height_mm IS NULL AND previous_volume_l IS NULL"
    op.create_table(
        POINTS,
        sa.Column("configuration_id", ROW_ID, nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("height_mm", sa.Float(), nullable=False),
        sa.Column("volume_l", sa.Float(), nullable=False),
        sa.Column("previous_position", sa.Integer(), nullable=True),
        sa.Column("previous_height_mm", sa.Float(), nullable=True),
        sa.Column("previous_volume_l", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("configuration_id", "position", name=op.f(f"pk_{POINTS}")),
        sa.ForeignKeyConstraint(
            ["configuration_id"], [f"{CONFIGS}.id"], name=op.f(f"fk_{POINTS}_configuration_id")
        ),
        # The target of the chain below; unique already, since the primary key is in it.
        sa.UniqueConstraint(
            "configuration_id",
            "position",
            "height_mm",
            "volume_l",
            name=op.f(f"uq_{POINTS}_configuration_id"),
        ),
        sa.ForeignKeyConstraint(
            ["configuration_id", "previous_position", "previous_height_mm", "previous_volume_l"],
            [
                f"{POINTS}.configuration_id",
                f"{POINTS}.position",
                f"{POINTS}.height_mm",
                f"{POINTS}.volume_l",
            ],
            name=op.f(f"fk_{POINTS}_previous_point"),
        ),
        _ck(POINTS, "position_uint", "position >= 0"),
        _ck(POINTS, "height_finite", _bounded("height_mm", ">= 0")),
        _ck(POINTS, "volume_finite", _bounded("volume_l", ">= 0")),
        _ck(POINTS, "first_has_no_previous", f"position > 0 OR ({first})"),
        # COALESCE: a NULL previous point must fail the check, not pass it as unknown.
        _ck(POINTS, "rises_from_previous", f"position = 0 OR COALESCE({rises}, FALSE)"),
    )


def upgrade() -> None:
    _configurations()
    _points()


def downgrade() -> None:
    for table in (POINTS, CONFIGS):
        op.drop_table(table)
