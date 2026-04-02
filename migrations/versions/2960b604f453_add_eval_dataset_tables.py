"""add eval dataset tables

Revision ID: 2960b604f453
Revises: 8cb6f5a7c4e5
Create Date: 2026-02-06 20:32:57.625569
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "2960b604f453"
down_revision = "8cb6f5a7c4e5"
branch_labels = None
depends_on = None


def _rebuild_message_label_table_if_needed():
    """
    SQLite-safe rebuild for message_label if constraints/columns are not in expected shape.
    Avoids dropping unnamed constraints (which crashes Alembic on SQLite).
    """
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if "message_label" not in insp.get_table_names():
        return

    cols = {c["name"] for c in insp.get_columns("message_label")}
    required = {"id", "message_id", "label", "labeled_at", "labeled_by"}

    # ✅ If table already has expected columns, do nothing
    if required.issubset(cols):
        return

    # Otherwise rebuild cleanly
    op.rename_table("message_label", "message_label_old")

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

    # Copy data safely (only columns that exist)
    # If labeled_at didn't exist earlier, we fill it with CURRENT_TIMESTAMP
    op.execute(
        """
        INSERT INTO message_label (id, message_id, label, labeled_at, labeled_by)
        SELECT
            id,
            message_id,
            label,
            COALESCE(labeled_at, CURRENT_TIMESTAMP),
            labeled_by
        FROM message_label_old
        """
    )

    op.drop_table("message_label_old")


def upgrade():
    # --- Create eval dataset tables ---
    op.create_table(
        "eval_dataset",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("is_frozen", sa.Boolean(), nullable=False),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["user.id"], name="fk_eval_dataset_created_by"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "eval_dataset_item",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("dataset_id", sa.Integer(), nullable=False),
        sa.Column("chat_history_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["chat_history_id"],
            ["chat_history.id"],
            name="fk_eval_dataset_item_chat_history_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["eval_dataset.id"],
            name="fk_eval_dataset_item_dataset_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dataset_id", "chat_history_id", name="uq_dataset_chat_history"),
    )

    with op.batch_alter_table("eval_dataset_item", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_eval_dataset_item_chat_history_id"),
            ["chat_history_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_eval_dataset_item_dataset_id"),
            ["dataset_id"],
            unique=False,
        )

    # --- SQLite-safe fix for message_label if needed ---
    _rebuild_message_label_table_if_needed()


def downgrade():
    # Drop eval dataset tables
    with op.batch_alter_table("eval_dataset_item", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_eval_dataset_item_dataset_id"))
        batch_op.drop_index(batch_op.f("ix_eval_dataset_item_chat_history_id"))

    op.drop_table("eval_dataset_item")
    op.drop_table("eval_dataset")

    # ✅ IMPORTANT:
    # Do NOT try to drop unnamed constraints on SQLite.
    # We intentionally do nothing for message_label in downgrade to avoid crashes.
