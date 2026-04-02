from alembic import op
import sqlalchemy as sa

revision = '6e5736df57bc'
down_revision = '02813ac1ca4f'
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table('chat_message', schema=None) as batch_op:
        batch_op.add_column(sa.Column('role', sa.String(length=20), nullable=False, server_default='user'))

def downgrade():
    with op.batch_alter_table('chat_message', schema=None) as batch_op:
        batch_op.drop_column('role')
