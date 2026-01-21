"""Add memory tables

Revision ID: a1b2c3d4e5f6
Revises: 80c5f9b455f3
Create Date: 2025-01-16 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '80c5f9b455f3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create conversation_memory table
    op.create_table('conversation_memory',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.String(length=255), nullable=True),
        sa.Column('quotation_id', sa.String(length=255), nullable=True),
        sa.Column('key', sa.String(length=255), nullable=False),
        sa.Column('value', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_conversation_memory_id'), 'conversation_memory', ['id'], unique=False)
    op.create_index(op.f('ix_conversation_memory_user_id'), 'conversation_memory', ['user_id'], unique=False)
    op.create_index(op.f('ix_conversation_memory_quotation_id'), 'conversation_memory', ['quotation_id'], unique=False)
    op.create_index(op.f('ix_conversation_memory_key'), 'conversation_memory', ['key'], unique=False)
    
    # Create agent_sessions table
    op.create_table('agent_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('quotation_id', sa.String(length=255), nullable=False),
        sa.Column('session_data', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('quotation_id')
    )
    op.create_index(op.f('ix_agent_sessions_id'), 'agent_sessions', ['id'], unique=False)
    op.create_index(op.f('ix_agent_sessions_quotation_id'), 'agent_sessions', ['quotation_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_agent_sessions_quotation_id'), table_name='agent_sessions')
    op.drop_index(op.f('ix_agent_sessions_id'), table_name='agent_sessions')
    op.drop_table('agent_sessions')
    
    op.drop_index(op.f('ix_conversation_memory_key'), table_name='conversation_memory')
    op.drop_index(op.f('ix_conversation_memory_quotation_id'), table_name='conversation_memory')
    op.drop_index(op.f('ix_conversation_memory_user_id'), table_name='conversation_memory')
    op.drop_index(op.f('ix_conversation_memory_id'), table_name='conversation_memory')
    op.drop_table('conversation_memory')

