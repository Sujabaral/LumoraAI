"""create appointment table

Revision ID: aad5a45d4efe
Revises: 81054b8a5d1a
Create Date: 2026-01-27 14:58:11.174547

"""
from alembic import op
import sqlalchemy as sa

revision = "aad5a45d4efe"
down_revision = "81054b8a5d1a"

def upgrade():
    op.create_table(
        "appointment",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("psychiatrist_id", sa.Integer(), nullable=True),
        sa.Column("psychiatrist_name", sa.String(120), nullable=False),
        sa.Column("start_time", sa.DateTime(), nullable=False),
        sa.Column("end_time", sa.DateTime(), nullable=True),
        sa.Column("amount", sa.Integer(), nullable=True),
        sa.Column("method", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("reminded_24h", sa.Boolean(), server_default=sa.text("0")),
        sa.Column("reminded_1h", sa.Boolean(), server_default=sa.text("0")),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
    )

def downgrade():
    op.drop_table("appointment")
