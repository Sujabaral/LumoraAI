"""add starred sessions + saved insights

Revision ID: 60f62e169add
Revises: 6dd0172f163c
Create Date: 2026-02-19 21:00:15.983881
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "60f62e169add"
down_revision = "6dd0172f163c"
branch_labels = None
depends_on = None


def upgrade():
    # 1) New table: saved_insight
    # - Make created_at non-null with SQLite default
    # - Add ondelete behavior to avoid future FK errors
    op.create_table(
        "saved_insight",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=True),
        sa.Column("chat_history_id", sa.Integer(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("(datetime('now'))"),
        ),
        sa.ForeignKeyConstraint(["chat_history_id"], ["chat_history.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_id"], ["chat_session.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # 2) Add nullable column: chat_message.intent_confidence (safe in SQLite)
    with op.batch_alter_table("chat_message", schema=None) as batch_op:
        batch_op.add_column(sa.Column("intent_confidence", sa.Float(), nullable=True))

    # 3) Add NOT NULL column: chat_session.is_starred
    # SQLite requires a default when adding NOT NULL to an existing table.
    with op.batch_alter_table("chat_session", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("is_starred", sa.Boolean(), nullable=False, server_default=sa.text("0"))
        )

    # Optional cleanup: remove DB-level default after backfilling existing rows
    # (keeps schema cleaner; Python-side default handles new rows)
    with op.batch_alter_table("chat_session", schema=None) as batch_op:
        batch_op.alter_column("is_starred", server_default=None)

    # 4) Keep Alembic-detected changes for message_label
    # If this later fails due to duplicates, we can fix by deleting dup rows first.
    with op.batch_alter_table("message_label", schema=None) as batch_op:
        batch_op.alter_column(
            "id",
            existing_type=sa.INTEGER(),
            nullable=False,
            autoincrement=True,
        )
        batch_op.create_unique_constraint(
            "uq_message_label_message_label",
            ["message_id", "label"],
        )


def downgrade():
    # Reverse message_label changes
    with op.batch_alter_table("message_label", schema=None) as batch_op:
        batch_op.drop_constraint("uq_message_label_message_label", type_="unique")
        # NOTE: downgrade nullable=True matches your original autogen file
        batch_op.alter_column(
            "id",
            existing_type=sa.INTEGER(),
            nullable=True,
            autoincrement=True,
        )

    # Drop added columns
    with op.batch_alter_table("chat_session", schema=None) as batch_op:
        batch_op.drop_column("is_starred")

    with op.batch_alter_table("chat_message", schema=None) as batch_op:
        batch_op.drop_column("intent_confidence")

    # Drop table
    op.drop_table("saved_insight")