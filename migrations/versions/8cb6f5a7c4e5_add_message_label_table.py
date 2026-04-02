"""add message_label table

Revision ID: 8cb6f5a7c4e5
Revises: aa78297e50b2
Create Date: 2026-02-06
"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime

# revision identifiers, used by Alembic.
revision = "8cb6f5a7c4e5"
down_revision = "aa78297e50b2"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # ✅ If table already exists (created earlier manually / by old code), skip creating it again
    if "message_label" in insp.get_table_names():
        # ensure index exists (SQLite supports IF NOT EXISTS)
        op.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_message_label_message_id "
            "ON message_label (message_id)"
        )
        return

    # Otherwise create it normally
    op.create_table(
        "message_label",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=10), nullable=False),
        sa.Column(
            "labeled_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("labeled_by", sa.Integer(), nullable=True),

        sa.ForeignKeyConstraint(
            ["message_id"],
            ["chat_message.id"],
            name="fk_message_label_message_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["labeled_by"],
            ["user.id"],
            name="fk_message_label_labeled_by",
        ),
        sa.UniqueConstraint("message_id", name="uq_message_label_message_id"),
    )

    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_message_label_message_id "
        "ON message_label (message_id)"
    )

def downgrade():
    op.drop_index("ix_message_label_message_id", table_name="message_label")
    op.drop_table("message_label")
