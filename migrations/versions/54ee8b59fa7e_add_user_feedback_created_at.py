"""add user_feedback created_at

Revision ID: 54ee8b59fa7e
Revises: 3d2010bde9da
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "54ee8b59fa7e"
down_revision = "3d2010bde9da"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = inspect(bind)

    # table already exists?
    if "user_feedback" not in insp.get_table_names():
        return

    cols = [c["name"] for c in insp.get_columns("user_feedback")]

    # only add if missing
    if "created_at" not in cols:
        with op.batch_alter_table("user_feedback") as batch_op:
            batch_op.add_column(sa.Column("created_at", sa.DateTime(), nullable=True))


def downgrade():
    bind = op.get_bind()
    insp = inspect(bind)

    if "user_feedback" not in insp.get_table_names():
        return

    cols = [c["name"] for c in insp.get_columns("user_feedback")]

    if "created_at" in cols:
        with op.batch_alter_table("user_feedback") as batch_op:
            batch_op.drop_column("created_at")
