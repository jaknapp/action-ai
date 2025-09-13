from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        'sessions',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )
    op.create_table(
        'processes',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('session_id', sa.String(length=36), sa.ForeignKey('sessions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('pid', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )
    op.create_table(
        'commands',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('process_id', sa.String(length=36), sa.ForeignKey('processes.id', ondelete='CASCADE'), nullable=False),
        sa.Column('command_text', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )
    op.create_table(
        'inputs',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('command_id', sa.String(length=36), sa.ForeignKey('commands.id', ondelete='CASCADE'), nullable=False),
        sa.Column('input_text', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )
    op.create_table(
        'outputs',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('command_id', sa.String(length=36), sa.ForeignKey('commands.id', ondelete='CASCADE'), nullable=False),
        sa.Column('output_text', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )

def downgrade() -> None:
    op.drop_table('outputs')
    op.drop_table('inputs')
    op.drop_table('commands')
    op.drop_table('processes')
    op.drop_table('sessions')
