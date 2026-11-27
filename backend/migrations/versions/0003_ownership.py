"""Customers, plants, tanks, devices and device assignments (S-073).

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-27

ADR-0007's customer > plant > tank > device. ``scan_records`` and
``gap_records`` are not touched and get no foreign key to ``devices``, so a
record from a device nobody registered or claimed is still stored. An
assignment puts a device on a tank from ``valid_from_unix_s`` until
``valid_to_unix_s``; a move closes one row and opens the next, and at most one
row per device is open. No foreign key cascades a delete: nothing is ever
deleted (ADR-0007 decision 5). Like 0001, a frozen snapshot in plain SQL,
valid in SQLite and Postgres.
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

ROW_ID = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
DEVICE_ID_MAX_BYTES = 64
NAME_MAX_CHARS = 100
ASSIGNMENTS = "device_assignments"
OPEN = "valid_to_unix_s IS NULL"


def _ck(table: str, name: str, condition: str) -> sa.CheckConstraint:
    # op.f(): the full name is final, so no naming convention rewrites it.
    return sa.CheckConstraint(condition, name=op.f(f"ck_{table}_{name}"))


def _named(table: str, *extra: sa.Column | sa.Constraint) -> list:
    """The id and name columns every customer, plant and tank has, then ``extra``."""
    return [
        sa.Column("id", ROW_ID, nullable=False),
        sa.Column("name", sa.String(NAME_MAX_CHARS), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table}")),
        _ck(table, "name_not_empty", "length(name) >= 1"),
        *extra,
    ]


def _child(table: str, parent_table: str, parent_id: str) -> None:
    """A plant under a customer or a tank under a plant: a name unique per parent."""
    op.create_table(
        table,
        *_named(
            table,
            sa.Column(parent_id, ROW_ID, nullable=False),
            sa.ForeignKeyConstraint(
                [parent_id], [f"{parent_table}.id"], name=op.f(f"fk_{table}_{parent_id}")
            ),
            sa.UniqueConstraint(parent_id, "name", name=op.f(f"uq_{table}_{parent_id}")),
        ),
    )


def upgrade() -> None:
    op.create_table(
        "customers",
        *_named("customers", sa.UniqueConstraint("name", name=op.f("uq_customers_name"))),
    )
    _child("plants", "customers", "customer_id")
    _child("tanks", "plants", "plant_id")
    op.create_table(
        "devices",
        sa.Column("device_id", sa.String(DEVICE_ID_MAX_BYTES), nullable=False),
        sa.PrimaryKeyConstraint("device_id", name=op.f("pk_devices")),
        _ck("devices", "device_id_not_empty", "length(device_id) >= 1"),
    )
    op.create_table(
        ASSIGNMENTS,
        sa.Column("id", ROW_ID, nullable=False),
        sa.Column("device_id", sa.String(DEVICE_ID_MAX_BYTES), nullable=False),
        sa.Column("tank_id", ROW_ID, nullable=False),
        sa.Column("valid_from_unix_s", sa.BigInteger(), nullable=False),
        sa.Column("valid_to_unix_s", sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{ASSIGNMENTS}")),
        sa.ForeignKeyConstraint(
            ["device_id"], ["devices.device_id"], name=op.f(f"fk_{ASSIGNMENTS}_device_id")
        ),
        sa.ForeignKeyConstraint(["tank_id"], ["tanks.id"], name=op.f(f"fk_{ASSIGNMENTS}_tank_id")),
        sa.UniqueConstraint(
            "device_id", "valid_from_unix_s", name=op.f(f"uq_{ASSIGNMENTS}_device_id")
        ),
        _ck(ASSIGNMENTS, "valid_from_uint", "valid_from_unix_s >= 0"),
        _ck(ASSIGNMENTS, "ends_after_start", f"{OPEN} OR valid_to_unix_s > valid_from_unix_s"),
    )
    # A partial unique index: at most one open (current) assignment per device.
    op.create_index(
        op.f(f"ix_{ASSIGNMENTS}_open"),
        ASSIGNMENTS,
        ["device_id"],
        unique=True,
        sqlite_where=sa.text(OPEN),
        postgresql_where=sa.text(OPEN),
    )


def downgrade() -> None:
    for table in (ASSIGNMENTS, "devices", "tanks", "plants", "customers"):
        op.drop_table(table)
