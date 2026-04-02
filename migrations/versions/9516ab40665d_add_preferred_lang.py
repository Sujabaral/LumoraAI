"""add preferred_lang

Revision ID: 9516ab40665d
Revises: 3b78ca9084cc
Create Date: 2026-02-06 13:58:59.340804

"""
from alembic import op
import sqlalchemy as sa

revision = '9516ab40665d'
down_revision = '3b78ca9084cc'
branch_labels = None
depends_on = None


def upgrade():
    # 1) add nullable
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('preferred_lang', sa.String(length=5), nullable=True))

    # 2) backfill existing rows
    op.execute("UPDATE user SET preferred_lang='en' WHERE preferred_lang IS NULL")

    # 3) make NOT NULL
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.alter_column('preferred_lang', existing_type=sa.String(length=5), nullable=False)


def downgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('preferred_lang')
