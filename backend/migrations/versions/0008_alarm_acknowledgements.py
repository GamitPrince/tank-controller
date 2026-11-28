"""Acknowledgements of raised advisory alarms, append-only (S-092, P1-18).

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-28

One row says that one person saw one raised alarm event: the event, the
caller's token ``sub`` and role, the server's time in Unix milliseconds and an
optional note. ``alarm_events`` is never updated (S-089), so this is its own
table. The unique key on the event means an event is acknowledged at most once.
Nothing here clears, silences or changes how an alarm is judged.

Like 0004 and 0007, triggers refuse UPDATE and DELETE, and TRUNCATE on Postgres.
The SQLite triggers are tested; the Postgres ones on a local
server too, when TANKAPI_TEST_DATABASE_URL is set (S-098).
Downgrade drops the acknowledgements: never run it on a database whose alarms matter.
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

TABLE = "alarm_acknowledgements"
ROW_ID = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
NOTE_MAX_CHARS = 200
ACKNOWLEDGING_ROLES = "'operator', 'maintenance', 'admin'"
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


def _dialect() -> str:
    # The context, not the bind, so --sql mode renders the Postgres form too.
    return op.get_context().dialect.name


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", ROW_ID, nullable=False),
        sa.Column("alarm_event_id", ROW_ID, nullable=False),
        sa.Column("subject", sa.String(128), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("at_unix_ms", sa.BigInteger(), nullable=False),
        sa.Column("note", sa.String(NOTE_MAX_CHARS), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{TABLE}")),
        sa.ForeignKeyConstraint(
            ["alarm_event_id"], ["alarm_events.id"], name=op.f(f"fk_{TABLE}_alarm_event_id")
        ),
        # One acknowledgement per event; a second one, even in a race, is refused.
        sa.UniqueConstraint("alarm_event_id", name=op.f(f"uq_{TABLE}_alarm_event_id")),
        _ck("subject_not_empty", "length(subject) >= 1"),
        _ck("role_acknowledges", f"role IN ({ACKNOWLEDGING_ROLES})"),
        _ck("at_uint", "at_unix_ms >= 0"),
        _ck("note_bounded", f"note IS NULL OR length(note) BETWEEN 1 AND {NOTE_MAX_CHARS}"),
    )
    # Any other dialect has no entry, so the upgrade stops rather than leave the table open.
    for statement in TRIGGERS[_dialect()]:
        op.execute(statement)


def downgrade() -> None:
    # Dropping the table drops its triggers on both dialects; the function stays on Postgres.
    op.drop_table(TABLE)
    if _dialect() == "postgresql":
        op.execute(f"DROP FUNCTION {FUNCTION}()")
