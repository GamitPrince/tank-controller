"""The append-only change log of a tank's settings (S-101).

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-28

One row is one change a person made to a tank's alarm thresholds (S-087) or
level configuration (S-085): who (the token's ``sub`` and role), when (the
server's time in Unix milliseconds), which tank, which kind of setting, and the
row closed and the row opened, with their values as JSON text. A created
setting has no before, a removed one no after; a change always has one of them.
Only admin and service may edit (S-101 [Confirm] 1). These settings live in the
cloud for advisory alarms and the level display; none ever reaches a device.

Like 0004, triggers refuse UPDATE and DELETE, and TRUNCATE on Postgres.
Downgrade drops the log: never run it on a database whose history matters.
"""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

TABLE = "config_changes"
ROW_ID = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
EDITING_ROLES = "'admin', 'service'"
KINDS = "'alarm_threshold', 'level_configuration'"
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
        sa.Column("at_unix_ms", sa.BigInteger(), nullable=False),
        sa.Column("subject", sa.String(128), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("tank_id", ROW_ID, nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("before_row_id", sa.BigInteger(), nullable=True),
        sa.Column("after_row_id", sa.BigInteger(), nullable=True),
        sa.Column("before", sa.Text(), nullable=True),
        sa.Column("after", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{TABLE}")),
        sa.ForeignKeyConstraint(["tank_id"], ["tanks.id"], name=op.f(f"fk_{TABLE}_tank_id")),
        _ck("at_uint", "at_unix_ms >= 0"),
        _ck("subject_not_empty", "length(subject) >= 1"),
        _ck("role_edits", f"role IN ({EDITING_ROLES})"),
        _ck("kind_known", f"kind IN ({KINDS})"),
        _ck("before_with_row", "(before IS NULL) = (before_row_id IS NULL)"),
        _ck("after_with_row", "(after IS NULL) = (after_row_id IS NULL)"),
        _ck("changes_something", "before IS NOT NULL OR after IS NOT NULL"),
    )
    # Any other dialect has no entry, so the upgrade stops rather than leave the table open.
    for statement in TRIGGERS[_dialect()]:
        op.execute(statement)


def downgrade() -> None:
    # Dropping the table drops its triggers on both dialects; the function stays on Postgres.
    op.drop_table(TABLE)
    if _dialect() == "postgresql":
        op.execute(f"DROP FUNCTION {FUNCTION}()")
