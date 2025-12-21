"""Initial schema

Revision ID: 001_initial
Revises: 
Create Date: 2025-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create quotations table
    op.create_table(
        'quotations',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('project_description', sa.String(), nullable=False),
        sa.Column('location', sa.String(), nullable=True),
        sa.Column('zip_code', sa.String(), nullable=True),
        sa.Column('project_type', sa.Enum('RESIDENTIAL', 'COMMERCIAL', 'RENOVATION', 'NEW_CONSTRUCTION', name='projecttype'), nullable=True),
        sa.Column('timeline', sa.String(), nullable=True),
        sa.Column('status', sa.Enum('PENDING', 'PROCESSING', 'DATA_COLLECTION', 'COST_CALCULATION', 'COMPLETED', 'FAILED', name='quotationstatus'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_quotations_id'), 'quotations', ['id'], unique=False)

    # Create quotation_data table
    op.create_table(
        'quotation_data',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('quotation_id', sa.String(), nullable=False),
        sa.Column('extracted_data', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('confidence_score', sa.Float(), nullable=True),
        sa.Column('cost_breakdown', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('total_cost', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['quotation_id'], ['quotations.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('quotation_id')
    )
    op.create_index(op.f('ix_quotation_data_id'), 'quotation_data', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_quotation_data_id'), table_name='quotation_data')
    op.drop_table('quotation_data')
    op.drop_index(op.f('ix_quotations_id'), table_name='quotations')
    op.drop_table('quotations')
    op.execute('DROP TYPE IF EXISTS quotationstatus')
    op.execute('DROP TYPE IF EXISTS projecttype')

