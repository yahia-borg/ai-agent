"""Create construction config tables

Revision ID: d1_config_tables
Revises: seperate_session_quotation
Create Date: 2026-02-10 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'd1_config_tables'
down_revision = 'c2_cleanup_old_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # construction_config
    op.create_table(
        'construction_config',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('key', sa.String(100), unique=True, nullable=False, index=True),
        sa.Column('value', postgresql.JSONB(), nullable=False),
        sa.Column('description', postgresql.JSONB(), nullable=True),
        sa.Column('category', sa.String(50), nullable=True, index=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    # room_multipliers
    op.create_table(
        'room_multipliers',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('room_type', sa.String(50), nullable=False, index=True),
        sa.Column('category_key', sa.String(50), nullable=False, index=True),
        sa.Column('multiplier_type', sa.String(20), nullable=False, index=True),
        sa.Column('value', sa.Float(), nullable=False),
        sa.Column('description', postgresql.JSONB(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    # area_distribution_defaults
    op.create_table(
        'area_distribution_defaults',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('project_type', sa.String(50), nullable=False, index=True),
        sa.Column('room_type', sa.String(50), nullable=False),
        sa.Column('percentage', sa.Float(), nullable=False),
        sa.Column('description', postgresql.JSONB(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    # trade_multipliers
    op.create_table(
        'trade_multipliers',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('project_type', sa.String(50), nullable=False, index=True),
        sa.Column('trade_key', sa.String(50), nullable=False),
        sa.Column('value', sa.Float(), nullable=False),
        sa.Column('description', postgresql.JSONB(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    # cost_component_splits
    op.create_table(
        'cost_component_splits',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('category', sa.String(50), nullable=False, index=True),
        sa.Column('component', sa.String(30), nullable=False),
        sa.Column('percentage', sa.Float(), nullable=False),
        sa.Column('label', postgresql.JSONB(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    # category_keywords
    op.create_table(
        'category_keywords',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('keyword_type', sa.String(50), nullable=False, index=True),
        sa.Column('group_key', sa.String(50), nullable=False, index=True),
        sa.Column('keywords', postgresql.JSONB(), nullable=False),
        sa.Column('description', postgresql.JSONB(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    # description_templates
    op.create_table(
        'description_templates',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('category', sa.String(50), nullable=False, index=True),
        sa.Column('template_key', sa.String(50), nullable=False, index=True),
        sa.Column('template_ar', sa.Text(), nullable=True),
        sa.Column('template_en', sa.Text(), nullable=True),
        sa.Column('variables', postgresql.JSONB(), nullable=True),
        sa.Column('description', postgresql.JSONB(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('description_templates')
    op.drop_table('category_keywords')
    op.drop_table('cost_component_splits')
    op.drop_table('trade_multipliers')
    op.drop_table('area_distribution_defaults')
    op.drop_table('room_multipliers')
    op.drop_table('construction_config')
