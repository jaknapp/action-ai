from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0003_messages'
down_revision = '0002_session_topics'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'messages',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('session_id', sa.String(length=36), nullable=False),
        sa.Column('topic_id', sa.String(length=256), nullable=False),
        sa.Column('payload_json', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )
    op.create_index('ix_messages_session_created', 'messages', ['session_id', 'created_at'])


def downgrade() -> None:
    op.drop_index('ix_messages_session_created', table_name='messages')
    op.drop_table('messages')


