from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0002_session_topics'
down_revision = '0001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'session_topics',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('session_id', sa.String(length=36), sa.ForeignKey('sessions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('topic_id', sa.String(length=256), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('session_topics')


