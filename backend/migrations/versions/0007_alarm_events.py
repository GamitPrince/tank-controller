"""Raised and cleared advisory alarms, append-only (S-089, P1-18).

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-27

One row is one change of one alarm's state, judged from one stored scan
(S-088): into ``high`` or ``low``, back to ``normal``, or into
``cannot_evaluate`` with the reason. A clear is a new row; nothing is ever
updated or deleted. Each row names the threshold row in force at the scan's
time and copies its limit and deadband, the value judged (in the measure's
stored unit), the reading's quality, and the scan with its time: never the
time of arrival. An untimed scan has no time, so it can only be
``cannot_evaluate`` for ``time_unknown``.

Like 0004, triggers refuse UPDATE and DELETE, and TRUNCATE on Postgres. The
SQLite triggers are tested; the Postgres function and triggers are only
rendered as text, untested on a server until the TimescaleDB container story.
Downgrade drops the history: never run it on a database whose alarms matter.
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

TABLE = "alarm_events"
ROW_ID = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
STATES = "'normal', 'high', 'low', 'cannot_evaluate'"
REASONS = "'no_reading', 'fault', 'unconfigured', 'stale', 'time_unknown', 'out_of_range'"
UNKNOWN = "state = 'cannot_evaluate'"
REFUSAL = f"{TABLE} is append-only"
FUNCTION = f"{TABLE}_refuse_change"

TRIGGERS = {
    "sqlite": [
        f"CREATE TRIGGER {TABLE}_no_{action.lower()} BEFORE {action} ON {TABLE} "
        f"BEGIN SELECT RAISE(ABORT, '{REFUSAL}'); END"
        for action in ("UPDATE", "DELETE")
    ],
    "postgresql": [
        f"CREATE FUNCTION {FUNCTION}() RETURNS trigger LANGUAGE plpgsql "
        f"AS $$ BEGIN RAISE EXCEPTION '{REFUSAL}'; END $$",
        f"CREATE TRIGGER {TABLE}_no_change BEFORE UPDATE OR DELETE ON {TABLE} "
        f"FOR EACH ROW EXECUTE FUNCTION {FUNCTION}()",
        f"CREATE TRIGGER {TABLE}_no_truncate BEFORE TRUNCATE ON {TABLE} "
        f"FOR EACH STATEMENT EXECUTE FUNCTION {FUNCTION}()",
    ],
}


def _ck(name: str, condition: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(condition, name=op.f(f"ck_{TABLE}_{name}"))


def _reason_is(reason: str) -> str:
    return f"COALESCE(reason = '{reason}', FALSE)"


def _dialect() -> str:
    # The context, not the bind, so --sql mode renders the Postgres form too.
    return op.get_context().dialect.name


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", ROW_ID, nullable=False),
        sa.Column("threshold_id", ROW_ID, nullable=False),
        sa.Column("scan_record_id", ROW_ID, nullable=False),
        sa.Column("unix_time_s", sa.BigInteger(), nullable=True),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(16), nullable=True),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("quality", sa.SmallInteger(), nullable=True),
        sa.Column("limit_value", sa.BigInteger(), nullable=False),
        sa.Column("deadband", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{TABLE}")),
        sa.ForeignKeyConstraint(
            ["threshold_id"], ["alarm_thresholds.id"], name=op.f(f"fk_{TABLE}_threshold_id")
        ),
        sa.ForeignKeyConstraint(
            ["scan_record_id"], ["scan_records.id"], name=op.f(f"fk_{TABLE}_scan_record_id")
        ),
        # One judgement of one threshold per scan, so a scan judged twice is refused.
        sa.UniqueConstraint(
            "threshold_id", "scan_record_id", name=op.f(f"uq_{TABLE}_threshold_id")
        ),
        _ck("state_known", f"state IN ({STATES})"),
        _ck("reason_known", f"reason IS NULL OR reason IN ({REASONS})"),
        # A judged state has a value and no reason; cannot_evaluate the reverse.
        _ck(
            "judged_or_reason",
            f"({UNKNOWN} AND reason IS NOT NULL AND value IS NULL)"
            f" OR (NOT ({UNKNOWN}) AND reason IS NULL AND value IS NOT NULL)",
        ),
        _ck("quality_known", "quality IS NULL OR quality BETWEEN 0 AND 4"),
        # COALESCE: a NULL reason must fail these, not pass them as unknown.
        _ck("quality_unless_no_reading", f"quality IS NOT NULL OR {_reason_is('no_reading')}"),
        _ck("untimed_time_unknown", f"unix_time_s IS NOT NULL OR {_reason_is('time_unknown')}"),
        _ck("time_uint", "unix_time_s IS NULL OR unix_time_s >= 0"),
        _ck("deadband_uint", "deadband >= 0"),
    )
    # Any other dialect has no entry, so the upgrade stops rather than leave the table open.
    for statement in TRIGGERS[_dialect()]:
        op.execute(statement)


def downgrade() -> None:
    # Dropping the table drops its triggers on both dialects; the function stays on Postgres.
    op.drop_table(TABLE)
    if _dialect() == "postgresql":
        op.execute(f"DROP FUNCTION {FUNCTION}()")
