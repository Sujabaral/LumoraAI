"""
add emotion profile and distortion tables

Revision ID: 6c195a8fdd95
Revises: 54ee8b59fa7e
Create Date: 2026-02-13 12:53:13.416935
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "6c195a8fdd95"
down_revision = "54ee8b59fa7e"
branch_labels = None
depends_on = None


def upgrade():
    # -------------------------------
    # New tables
    # -------------------------------
    op.create_table(
        "user_emotion_profile",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("dominant_emotions_json", sa.Text(), nullable=False),
        sa.Column("triggers_json", sa.Text(), nullable=False),
        sa.Column("coping_pref_json", sa.Text(), nullable=False),
        sa.Column("style_pref", sa.String(length=50), nullable=True),
        sa.Column("risk_trend", sa.String(length=30), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("user_id"),
    )

    op.create_table(
        "distortion_event",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=True),
        sa.Column("distortions_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["chat_session.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "user_emotion_event",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=True),
        sa.Column("emotion", sa.String(length=30), nullable=False),
        sa.Column("intensity", sa.Integer(), nullable=False),
        sa.Column("trigger", sa.String(length=60), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["chat_session.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # ---------------------------------------------------------
    # SQLite-safe rebuild of message_label
    # Fixes:
    # - "Constraint must have a name" (SQLite batch ops issue)
    # - half-applied migration leftovers:
    #     * message_label_old already exists
    #     * ix_message_label_message_id already exists
    # ---------------------------------------------------------

    # Clean up possible leftovers from a previous failed run
    # (SQLite allows IF EXISTS for DROP TABLE/INDEX)
    op.execute("DROP INDEX IF EXISTS ix_message_label_message_id")
    op.execute("DROP INDEX IF EXISTS ix_message_label_message_id1")
    op.execute("DROP INDEX IF EXISTS ix_message_label_message_id2")
    op.execute("DROP TABLE IF EXISTS message_label_old")

    # Rename current table to _old (must exist at this point)
    op.rename_table("message_label", "message_label_old")

    # Recreate message_label with named constraints (no auto index=True)
    op.create_table(
        "message_label",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=10), nullable=False),
        sa.Column("labeled_at", sa.DateTime(), nullable=False),
        sa.Column("labeled_by", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
        sa.UniqueConstraint("message_id", name="uq_message_label_message_id"),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["chat_message.id"],
            name="fk_message_label_message_id",
            ondelete="CASCADE",
        ),
    )

    # Create an index with a NEW unique name to avoid collisions with ix_message_label_message_id
    op.create_index("ix2_message_label_message_id", "message_label", ["message_id"])

    # Copy data over
    op.execute(
        """
        INSERT INTO message_label (id, message_id, label, labeled_at, labeled_by)
        SELECT id, message_id, label, labeled_at, labeled_by
        FROM message_label_old
        """
    )

    # Drop old table
    op.drop_table("message_label_old")


def downgrade():
    # Drop the new tables first
    op.drop_table("user_emotion_event")
    op.drop_table("distortion_event")
    op.drop_table("user_emotion_profile")

    # message_label: drop our custom index + table
    # (Simple dev-safe downgrade; if you need to restore the old schema, tell me and I’ll write that too.)
    op.execute("DROP INDEX IF EXISTS ix2_message_label_message_id")
    op.drop_table("message_label")