"""The append-only audit trail of service staff's requests (S-079).

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-27

ADR-0008 decision 4: the backend may add audit rows but never edit or delete
them. Triggers refuse UPDATE and DELETE in the database itself, so no query,
hand-written or not, can rewrite the trail; on Postgres TRUNCATE is refused too.
The SQLite triggers are tested; the Postgres ones on a local
server too, when TANKAPI_TEST_DATABASE_URL is set (S-098).
[Confirm] The backend's own database role must also lack UPDATE, DELETE and
TRUNCATE on the table and must not own it (the deployment story).

Downgrade drops the table and with it the trail: never run it on a database
whose trail matters. A later SQLite batch migration that rebuilds this table
must create its triggers again.
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

TABLE = "audit_entries"
ROW_ID = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
DEVICE_ID_MAX_BYTES = 64
ROLES = "'operator', 'maintenance', 'admin', 'service'"
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
        sa.Column("method", sa.String(8), nullable=False),
        sa.Column("route", sa.String(200), nullable=False),
        sa.Column("device_id", sa.String(DEVICE_ID_MAX_BYTES), nullable=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("status", sa.SmallInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{TABLE}")),
        _ck("at_uint", "at_unix_ms >= 0"),
        _ck("subject_not_empty", "length(subject) >= 1"),
        _ck("role_known", f"role IN ({ROLES})"),
        _ck("status_http", "status BETWEEN 100 AND 599"),
    )
    # Any other dialect has no entry, so the upgrade stops rather than leave the table open.
    for statement in TRIGGERS[_dialect()]:
        op.execute(statement)


def downgrade() -> None:
    # Dropping the table drops its triggers on both dialects; the function stays on Postgres.
    op.drop_table(TABLE)
    if _dialect() == "postgresql":
        op.execute(f"DROP FUNCTION {FUNCTION}()")
