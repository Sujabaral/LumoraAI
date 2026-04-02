"""add chat sessions

Revision ID: c16f496ac246
Revises: 05cbd8166583
Create Date: 2026-01-25 00:19:58.121383
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = 'c16f496ac246'
down_revision = '05cbd8166583'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = inspect(bind)

    # ----------------------------
    # 1) chat_session table (only if not exists)
    # ----------------------------
    tables = insp.get_table_names()
    if 'chat_session' not in tables:
        op.create_table(
            'chat_session',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('title', sa.String(length=120), nullable=False, server_default='New Chat'),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.Column('is_archived', sa.Boolean(), nullable=False, server_default=sa.text('0')),
            sa.ForeignKeyConstraint(['user_id'], ['user.id']),
            sa.PrimaryKeyConstraint('id')
        )

    # refresh inspector (important after creating table)
    insp = inspect(bind)

    # ----------------------------
    # 2) chat_history.session_id (only if not exists)
    # ----------------------------
    chat_history_cols = [c['name'] for c in insp.get_columns('chat_history')]
    if 'session_id' not in chat_history_cols:
        with op.batch_alter_table('chat_history', schema=None) as batch_op:
            batch_op.add_column(sa.Column('session_id', sa.Integer(), nullable=True))

    # refresh inspector again
    insp = inspect(bind)

    # ----------------------------
    # 3) FK chat_history.session_id -> chat_session.id (only if not exists)
    # SQLite doesn’t preserve fk names well; check by referred table + columns.
    # ----------------------------
    fks = insp.get_foreign_keys('chat_history')
    has_fk = any(
        fk.get('referred_table') == 'chat_session'
        and fk.get('constrained_columns') == ['session_id']
        for fk in fks
    )

    # create FK only if missing
    if not has_fk:
        with op.batch_alter_table('chat_history', schema=None) as batch_op:
            batch_op.create_foreign_key(
                'fk_chat_history_session_id_chat_session',
                'chat_session',
                ['session_id'],
                ['id']
            )

    # ----------------------------
    # 4) psychiatrist_booking changes (make safe)
    # ----------------------------
    pb_cols = [c['name'] for c in insp.get_columns('psychiatrist_booking')]

    with op.batch_alter_table('psychiatrist_booking', schema=None) as batch_op:
        if 'khalti_pidx' not in pb_cols:
            batch_op.add_column(sa.Column('khalti_pidx', sa.String(length=60), nullable=True))
        if 'khalti_transaction_id' not in pb_cols:
            batch_op.add_column(sa.Column('khalti_transaction_id', sa.String(length=80), nullable=True))
        if 'payment_ref' in pb_cols:
            batch_op.drop_column('payment_ref')


def downgrade():
    bind = op.get_bind()
    insp = inspect(bind)

    # psychiatrist_booking rollback (safe)
    pb_cols = [c['name'] for c in insp.get_columns('psychiatrist_booking')]
    with op.batch_alter_table('psychiatrist_booking', schema=None) as batch_op:
        if 'payment_ref' not in pb_cols:
            batch_op.add_column(sa.Column('payment_ref', sa.VARCHAR(length=120), nullable=True))
        if 'khalti_transaction_id' in pb_cols:
            batch_op.drop_column('khalti_transaction_id')
        if 'khalti_pidx' in pb_cols:
            batch_op.drop_column('khalti_pidx')

    # chat_history rollback
    insp = inspect(bind)
    chat_history_cols = [c['name'] for c in insp.get_columns('chat_history')]
    if 'session_id' in chat_history_cols:
        with op.batch_alter_table('chat_history', schema=None) as batch_op:
            # use the named FK we created
            batch_op.drop_constraint('fk_chat_history_session_id_chat_session', type_='foreignkey')
            batch_op.drop_column('session_id')

    # drop chat_session table if exists
    insp = inspect(bind)
    if 'chat_session' in insp.get_table_names():
        op.drop_table('chat_session')
