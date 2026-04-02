"""add reminder fields to psychiatrist_booking

Revision ID: 81054b8a5d1a
Revises: c16f496ac246
Create Date: 2026-01-27 14:54:42.826959
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "81054b8a5d1a"
down_revision = "c16f496ac246"
branch_labels = None
depends_on = None


def upgrade():
    # ✅ Only add reminder fields (safe for SQLite)
    with op.batch_alter_table("psychiatrist_booking", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "reminded_24h",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "reminded_1h",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )


def downgrade():
    with op.batch_alter_table("psychiatrist_booking", schema=None) as batch_op:
        batch_op.drop_column("reminded_1h")
        batch_op.drop_column("reminded_24h")
