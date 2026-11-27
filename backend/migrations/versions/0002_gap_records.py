"""Gap records (S-069).

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-27

One row per gap record (S-040): ``lost`` scans, from the ``first`` mark to the
``last``, were measured but will never arrive. Nothing may interpolate across
one. The check constraints repeat the decoder's rules and, like 0001, are a
frozen snapshot in plain SQL, valid in SQLite and Postgres.
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

TABLE = "gap_records"
ROW_ID = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
BOOT_ID_BYTES = 16
DEVICE_ID_MAX_BYTES = 64


def _ck(name: str, condition: str) -> sa.CheckConstraint:
    # op.f(): the full name is final, so no naming convention rewrites it.
    return sa.CheckConstraint(condition, name=op.f(f"ck_{TABLE}_{name}"))


def _mark(end: str) -> list[sa.Column | sa.CheckConstraint]:
    """The columns of one lost-scan mark, ``first`` or ``last``, and their checks."""
    known, unix = f"{end}_time_known", f"{end}_unix_time_s"
    return [
        sa.Column(f"{end}_boot_id", sa.LargeBinary(BOOT_ID_BYTES), nullable=False),
        sa.Column(f"{end}_sequence", sa.BigInteger(), nullable=False),
        sa.Column(f"{end}_uptime_ms", sa.BigInteger(), nullable=False),
        sa.Column(known, sa.Boolean(), nullable=False),
        sa.Column(unix, sa.BigInteger(), nullable=True),
        _ck(f"{end}_boot_id_size", f"length({end}_boot_id) = {BOOT_ID_BYTES}"),
        _ck(f"{end}_time", f"({known} AND {unix} IS NOT NULL) OR (NOT {known} AND {unix} IS NULL)"),
        *(
            _ck(f"{column}_uint", f"{column} >= 0")
            for column in (f"{end}_sequence", f"{end}_uptime_ms", unix)
        ),
    ]


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", ROW_ID, nullable=False),
        sa.Column("device_id", sa.String(DEVICE_ID_MAX_BYTES), nullable=False),
        sa.Column("lost", sa.BigInteger(), nullable=False),
        *_mark("first"),
        *_mark("last"),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{TABLE}")),
        _ck("device_id_not_empty", "length(device_id) >= 1"),
        _ck("lost_at_least_one", "lost >= 1"),
    )


def downgrade() -> None:
    op.drop_table(TABLE)
