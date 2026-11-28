"""Per-second samples in a TimescaleDB hypertable, with per-minute summaries (S-100).

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-28

``reading_samples`` holds one row per reading of a time-known scan, stamped with
the scan's own time ``t``; a time-unknown scan has no place on a time axis and
gets no sample. ``scan_records`` and ``readings`` stay as they are and are kept
forever: they stand in for the raw archive (S-100 [Confirm] 1 and 2).

The table exists on every database. On PostgreSQL with TimescaleDB available
(ADR-0007 decision 4) it becomes a hypertable on ``t`` with one-day chunks, and
gets the ``reading_minutes`` continuous aggregate, kept forever, and a 90-day
retention policy on the samples (decision 5). The aggregate's statistics count
only good samples: a fault carries no value, and a stale or out-of-range value is
flagged, so none is averaged as good data (AGENTS.md section 7). A gap is never
filled: a minute with lost scans has fewer samples, and an empty minute no row.
The extension is trusted, so a database owner may create it without superuser
rights (S-100 [Confirm] 6). Elsewhere the table stays plain, with no retention.
"""

import logging

import sqlalchemy as sa
from alembic import context, op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

TABLE = "reading_samples"
MINUTES = "reading_minutes"
ROW_ID = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
DEVICE_ID_MAX_BYTES = 64
QUALITY_MAX = 4
GOOD = 0
CHUNK = "INTERVAL '1 day'"
KEEP_SAMPLES = "INTERVAL '90 days'"
# The window spans the samples' whole life, so a backlog replayed days late is still
# summarised before its chunk is dropped; only invalidated minutes are recomputed.
REFRESH = (
    f"start_offset => {KEEP_SAMPLES}, end_offset => INTERVAL '1 minute',"
    " schedule_interval => INTERVAL '1 minute'"
)
GOOD_VALUE = f"FILTER (WHERE quality = {GOOD} AND value_int IS NOT NULL)"
TIMESCALE_STEPS = [
    "CREATE EXTENSION IF NOT EXISTS timescaledb",
    # The index on (device_id, signal_id, t) serves the reads; no default index on t alone.
    f"SELECT create_hypertable('{TABLE}', by_range('t', {CHUNK}), create_default_indexes => false)",
    f"CREATE MATERIALIZED VIEW {MINUTES} WITH (timescaledb.continuous) AS"
    " SELECT device_id, signal_id, time_bucket(INTERVAL '1 minute', t) AS minute,"
    " count(*) AS samples,"
    f" count(*) FILTER (WHERE quality = {GOOD}) AS good_samples,"
    " max(quality) AS worst_quality,"
    f" min(value_int) {GOOD_VALUE} AS min_value,"
    f" max(value_int) {GOOD_VALUE} AS max_value,"
    f" avg(value_int) {GOOD_VALUE} AS avg_value,"
    f" count(*) FILTER (WHERE quality = {GOOD} AND value_bool) AS true_samples"
    f" FROM {TABLE} GROUP BY device_id, signal_id, minute WITH NO DATA",
    f"SELECT add_continuous_aggregate_policy('{MINUTES}', {REFRESH})",
    f"SELECT add_retention_policy('{TABLE}', {KEEP_SAMPLES})",
]

log = logging.getLogger(f"alembic.{__name__}")


def _timescale_available() -> bool:
    # Offline (--sql) has no server to ask; the rendered SQL is the plain table.
    if context.is_offline_mode() or op.get_bind().dialect.name != "postgresql":
        return False
    query = sa.text("SELECT count(*) FROM pg_available_extensions WHERE name = 'timescaledb'")
    if op.get_bind().scalar(query):
        return True
    log.warning("timescaledb is not available: %s stays a plain table, no retention", TABLE)
    return False


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("scan_record_id", ROW_ID, nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("t", sa.DateTime(timezone=True), nullable=False),
        sa.Column("device_id", sa.String(DEVICE_ID_MAX_BYTES), nullable=False),
        sa.Column("signal_id", sa.BigInteger(), nullable=False),
        sa.Column("quality", sa.SmallInteger(), nullable=False),
        sa.Column("value_int", sa.BigInteger(), nullable=True),
        sa.Column("value_bool", sa.Boolean(), nullable=True),
        # A hypertable's primary key must contain its time column.
        sa.PrimaryKeyConstraint("scan_record_id", "position", "t", name=op.f(f"pk_{TABLE}")),
        sa.ForeignKeyConstraint(
            ["scan_record_id"], ["scan_records.id"], name=op.f(f"fk_{TABLE}_scan_record_id")
        ),
        sa.CheckConstraint(
            f"quality BETWEEN 0 AND {QUALITY_MAX}", name=op.f(f"ck_{TABLE}_quality_known")
        ),
    )
    op.create_index(op.f(f"ix_{TABLE}_device_signal_t"), TABLE, ["device_id", "signal_id", "t"])
    if _timescale_available():
        for statement in TIMESCALE_STEPS:
            op.execute(statement)


def downgrade() -> None:
    if _timescale_available():
        # Dropping the aggregate also removes its refresh policy.
        op.execute(f"DROP MATERIALIZED VIEW {MINUTES}")
        op.execute(f"SELECT remove_retention_policy('{TABLE}')")
    op.drop_table(TABLE)
