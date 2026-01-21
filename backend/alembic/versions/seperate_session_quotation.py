"""Separate session_id from quotation_id in agent_sessions

Revision ID: b2c3d4e5f6g7
Revises: a1b2c3d4e5f6
Create Date: 2026-01-02 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6g7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    """
    Add session_id column to agent_sessions table and properly separate
    session identifiers from quotation identifiers.
    """
    # Step 1: Drop existing UNIQUE constraint on quotation_id (from add_memory_tables migration)
    op.drop_constraint('agent_sessions_quotation_id_key', 'agent_sessions', type_='unique')

    # Step 2: Make quotation_id nullable
    op.alter_column('agent_sessions', 'quotation_id', nullable=True)

    # Step 3: Add new session_id column
    op.add_column('agent_sessions',
        sa.Column('session_id', sa.String(255), nullable=True)
    )

    # Step 4: Migrate data - copy quotation_id to session_id for existing records
    op.execute("""
        UPDATE agent_sessions
        SET session_id = quotation_id
        WHERE session_id IS NULL
    """)

    # Step 5: Make session_id NOT NULL and UNIQUE
    op.alter_column('agent_sessions', 'session_id', nullable=False)
    op.create_unique_constraint('uq_agent_sessions_session_id', 'agent_sessions', ['session_id'])

    # Step 6: Update quotation_id to NULL for sessions without real quotations
    # (sessions where quotation_id doesn't exist in quotations table)
    op.execute("""
        UPDATE agent_sessions
        SET quotation_id = NULL
        WHERE quotation_id NOT IN (SELECT id FROM quotations)
    """)

    # Step 7: Add foreign key constraint
    op.create_foreign_key(
        'fk_agent_sessions_quotation',
        'agent_sessions', 'quotations',
        ['quotation_id'], ['id'],
        ondelete='CASCADE'
    )

    # Step 8: Add indexes for performance
    op.create_index('idx_agent_sessions_session_id', 'agent_sessions', ['session_id'])
    op.create_index('idx_agent_sessions_quotation_id', 'agent_sessions', ['quotation_id'])


def downgrade():
    """Rollback the session_id separation."""
    op.drop_constraint('fk_agent_sessions_quotation', 'agent_sessions', type_='foreignkey')
    op.drop_index('idx_agent_sessions_quotation_id')
    op.drop_index('idx_agent_sessions_session_id')
    op.drop_constraint('uq_agent_sessions_session_id', 'agent_sessions', type_='unique')
    op.drop_column('agent_sessions', 'session_id')
