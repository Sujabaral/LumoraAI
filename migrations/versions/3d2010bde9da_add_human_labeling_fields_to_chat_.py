"""Add human labeling fields to chat_history

Revision ID: 3d2010bde9da
Revises: 2960b604f453
Create Date: 2026-02-06 21:47:06.442367

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3d2010bde9da'
down_revision = '2960b604f453'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('chat_history', schema=None) as batch_op:
        # add BOTH columns (you need human_label too)
        batch_op.add_column(sa.Column('human_label', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column(
            'is_human_labeled',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('0')
        ))

    # optional: remove default after backfill (safe to keep too)
    with op.batch_alter_table('chat_history', schema=None) as batch_op:
        batch_op.alter_column('is_human_labeled', server_default=None)


    # ### end Alembic commands ###


def downgrade():
    with op.batch_alter_table('chat_history', schema=None) as batch_op:
        batch_op.drop_column('is_human_labeled')
        batch_op.drop_column('human_label')

    # ### end Alembic commands ###
