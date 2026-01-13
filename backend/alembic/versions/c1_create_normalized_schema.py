"""Create normalized multilingual schema

Revision ID: c1_normalized_schema
Revises: b2c3d4e5f6g7
Create Date: 2025-01-09

This migration creates the new normalized schema with:
- Reference tables: currencies, units, categories
- Core tables: materials (JSONB), material_synonyms, labor_rates (JSONB)
- Quotation tables: quotation_items
- Updated session tables

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 'c1_normalized_schema'
down_revision = 'b2c3d4e5f6g7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ========================================================================
    # STEP 1: Enable PostgreSQL extensions for better search
    # ========================================================================
    op.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm')
    
    # ========================================================================
    # STEP 2: Create REFERENCE TABLES
    # ========================================================================
    
    # --- currencies table ---
    op.create_table(
        'currencies',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(3), nullable=False),
        sa.Column('name', postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                  comment='{"en": "Egyptian Pound", "ar": "جنيه مصري"}'),
        sa.Column('symbol', sa.String(10), nullable=True),
        sa.Column('is_default', sa.Boolean(), default=False, nullable=False),
        sa.Column('is_active', sa.Boolean(), default=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_currencies_code', 'currencies', ['code'], unique=True)
    
    # --- units table ---
    op.create_table(
        'units',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(20), nullable=False),
        sa.Column('name', postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                  comment='{"en": "Square Meter", "ar": "متر مربع"}'),
        sa.Column('symbol', sa.String(10), nullable=True),
        sa.Column('unit_type', sa.String(20), nullable=True,
                  comment='area, volume, weight, count, time, length'),
        sa.Column('is_active', sa.Boolean(), default=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_units_code', 'units', ['code'], unique=True)
    
    # --- categories table ---
    op.create_table(
        'categories',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(50), nullable=False),
        sa.Column('name', postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                  comment='{"en": "Cement", "ar": "أسمنت"}'),
        sa.Column('category_type', sa.String(20), nullable=False,
                  comment='material or labor'),
        sa.Column('parent_id', sa.Integer(), nullable=True),
        sa.Column('icon', sa.String(100), nullable=True),
        sa.Column('sort_order', sa.Integer(), default=0, nullable=False),
        sa.Column('is_active', sa.Boolean(), default=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['parent_id'], ['categories.id'], ondelete='SET NULL')
    )
    op.create_index('ix_categories_code', 'categories', ['code'], unique=True)
    op.create_index('ix_categories_type', 'categories', ['category_type'])
    op.create_index('ix_categories_parent', 'categories', ['parent_id'])
    op.create_index('ix_categories_name_gin', 'categories', ['name'], postgresql_using='gin')
    
    # ========================================================================
    # STEP 3: Create CORE DATA TABLES
    # ========================================================================
    
    # --- materials table (new with JSONB) ---
    op.create_table(
        'materials_new',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(50), nullable=True),
        sa.Column('name', postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                  comment='{"en": "Portland Cement", "ar": "أسمنت بورتلاند"}'),
        sa.Column('description', postgresql.JSONB(astext_type=sa.Text()), nullable=True,
                  comment='{"en": "...", "ar": "..."}'),
        sa.Column('category_id', sa.Integer(), nullable=True),
        sa.Column('unit_id', sa.Integer(), nullable=True),
        sa.Column('price', sa.Numeric(12, 2), nullable=False),
        sa.Column('currency_id', sa.Integer(), nullable=True),
        sa.Column('brand', sa.String(100), nullable=True),
        sa.Column('supplier', sa.String(200), nullable=True),
        sa.Column('specifications', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('source', sa.String(100), nullable=True),
        sa.Column('is_active', sa.Boolean(), default=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['unit_id'], ['units.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['currency_id'], ['currencies.id'], ondelete='SET NULL')
    )
    op.create_index('ix_materials_new_id', 'materials_new', ['id'])
    op.create_index('ix_materials_new_code', 'materials_new', ['code'], unique=True)
    op.create_index('ix_materials_new_category', 'materials_new', ['category_id'])
    op.create_index('ix_materials_new_name_gin', 'materials_new', ['name'], postgresql_using='gin')
    op.create_index('ix_materials_new_name_en', 'materials_new', [sa.text("(name->>'en')")])
    op.create_index('ix_materials_new_name_ar', 'materials_new', [sa.text("(name->>'ar')")])
    op.create_index('ix_materials_new_name_en_trgm', 'materials_new', [sa.text("(name->>'en') gin_trgm_ops")], postgresql_using='gin')
    op.create_index('ix_materials_new_name_ar_trgm', 'materials_new', [sa.text("(name->>'ar') gin_trgm_ops")], postgresql_using='gin')
    op.create_index('ix_materials_new_active', 'materials_new', ['is_active'])
    
    # --- material_synonyms table ---
    op.create_table(
        'material_synonyms',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('material_id', sa.Integer(), nullable=False),
        sa.Column('language_code', sa.String(5), nullable=False, comment='en, ar'),
        sa.Column('synonym', sa.String(255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['material_id'], ['materials_new.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('material_id', 'language_code', 'synonym', name='uq_material_synonym')
    )
    op.create_index('ix_material_synonyms_material', 'material_synonyms', ['material_id'])
    op.create_index('ix_material_synonyms_lang', 'material_synonyms', ['language_code'])
    op.create_index('ix_material_synonyms_synonym', 'material_synonyms', ['synonym'])
    op.create_index('ix_material_synonyms_trgm', 'material_synonyms', [sa.text("synonym gin_trgm_ops")], postgresql_using='gin')
    
    # --- labor_rates table (new with JSONB) ---
    op.create_table(
        'labor_rates_new',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(50), nullable=True),
        sa.Column('role', postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                  comment='{"en": "Mason", "ar": "بناء"}'),
        sa.Column('description', postgresql.JSONB(astext_type=sa.Text()), nullable=True,
                  comment='{"en": "...", "ar": "..."}'),
        sa.Column('category_id', sa.Integer(), nullable=True),
        sa.Column('hourly_rate', sa.Numeric(10, 2), nullable=True),
        sa.Column('daily_rate', sa.Numeric(10, 2), nullable=True),
        sa.Column('currency_id', sa.Integer(), nullable=True),
        sa.Column('skill_level', sa.String(20), nullable=True,
                  comment='unskilled, skilled, master'),
        sa.Column('source', sa.String(100), nullable=True),
        sa.Column('is_active', sa.Boolean(), default=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['currency_id'], ['currencies.id'], ondelete='SET NULL')
    )
    op.create_index('ix_labor_rates_new_id', 'labor_rates_new', ['id'])
    op.create_index('ix_labor_rates_new_code', 'labor_rates_new', ['code'], unique=True)
    op.create_index('ix_labor_rates_new_category', 'labor_rates_new', ['category_id'])
    op.create_index('ix_labor_rates_new_role_gin', 'labor_rates_new', ['role'], postgresql_using='gin')
    op.create_index('ix_labor_rates_new_role_en', 'labor_rates_new', [sa.text("(role->>'en')")])
    op.create_index('ix_labor_rates_new_role_ar', 'labor_rates_new', [sa.text("(role->>'ar')")])
    op.create_index('ix_labor_rates_new_role_en_trgm', 'labor_rates_new', [sa.text("(role->>'en') gin_trgm_ops")], postgresql_using='gin')
    op.create_index('ix_labor_rates_new_role_ar_trgm', 'labor_rates_new', [sa.text("(role->>'ar') gin_trgm_ops")], postgresql_using='gin')
    op.create_index('ix_labor_rates_new_active', 'labor_rates_new', ['is_active'])
    
    # ========================================================================
    # STEP 4: Create QUOTATION TABLES
    # ========================================================================
    
    # --- Add language_preference to quotations ---
    op.add_column('quotations', sa.Column('language_preference', sa.String(5), nullable=True, server_default='ar'))
    
    # --- quotation_items table (new normalized line items) ---
    op.create_table(
        'quotation_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('quotation_id', sa.String(), nullable=False),
        sa.Column('item_type', sa.String(20), nullable=False, comment='material or labor'),
        sa.Column('material_id', sa.Integer(), nullable=True),
        sa.Column('labor_rate_id', sa.Integer(), nullable=True),
        sa.Column('name', postgresql.JSONB(astext_type=sa.Text()), nullable=True,
                  comment='Override name if needed'),
        sa.Column('description', postgresql.JSONB(astext_type=sa.Text()), nullable=True,
                  comment='{"en": "...", "ar": "..."}'),
        sa.Column('quantity', sa.Numeric(12, 3), nullable=False),
        sa.Column('unit_id', sa.Integer(), nullable=True),
        sa.Column('unit_price', sa.Numeric(12, 2), nullable=False),
        sa.Column('total_price', sa.Numeric(12, 2), nullable=False),
        sa.Column('notes', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('sort_order', sa.Integer(), default=0, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['quotation_id'], ['quotations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['material_id'], ['materials_new.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['labor_rate_id'], ['labor_rates_new.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['unit_id'], ['units.id'], ondelete='SET NULL')
    )
    op.create_index('ix_quotation_items_quotation', 'quotation_items', ['quotation_id'])
    op.create_index('ix_quotation_items_material', 'quotation_items', ['material_id'])
    op.create_index('ix_quotation_items_labor', 'quotation_items', ['labor_rate_id'])
    op.create_index('ix_quotation_items_type', 'quotation_items', ['item_type'])
    
    # ========================================================================
    # STEP 5: Create SESSION TABLES (new versions)
    # ========================================================================
    
    # --- agent_sessions_new table ---
    op.create_table(
        'agent_sessions_new',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.String(255), nullable=False),
        sa.Column('quotation_id', sa.String(), nullable=True),
        sa.Column('language_preference', sa.String(5), nullable=True, server_default='ar'),
        sa.Column('session_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['quotation_id'], ['quotations.id'], ondelete='SET NULL')
    )
    op.create_index('ix_agent_sessions_new_id', 'agent_sessions_new', ['id'])
    op.create_index('ix_agent_sessions_new_session_id', 'agent_sessions_new', ['session_id'], unique=True)
    op.create_index('ix_agent_sessions_new_quotation', 'agent_sessions_new', ['quotation_id'])
    
    # --- conversation_memory_new table ---
    op.create_table(
        'conversation_memory_new',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.String(255), nullable=False),
        sa.Column('user_id', sa.String(255), nullable=True),
        sa.Column('key', sa.String(255), nullable=False),
        sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_conversation_memory_new_id', 'conversation_memory_new', ['id'])
    op.create_index('ix_conversation_memory_new_session', 'conversation_memory_new', ['session_id'])
    op.create_index('ix_conversation_memory_new_user', 'conversation_memory_new', ['user_id'])
    op.create_index('ix_conversation_memory_new_key', 'conversation_memory_new', ['key'])
    
    # ========================================================================
    # STEP 6: Create SEARCH FUNCTION for multilingual materials
    # ========================================================================
    op.execute("""
        CREATE OR REPLACE FUNCTION search_materials_multilingual(
            p_query TEXT,
            p_language VARCHAR(5) DEFAULT NULL,
            p_category_id INTEGER DEFAULT NULL,
            p_limit INTEGER DEFAULT 10
        )
        RETURNS TABLE (
            id INTEGER,
            code VARCHAR,
            name_en TEXT,
            name_ar TEXT,
            category_id INTEGER,
            unit_id INTEGER,
            price NUMERIC,
            currency_id INTEGER,
            relevance REAL
        ) AS $$
        DECLARE
            v_is_arabic BOOLEAN;
            v_search_field TEXT;
        BEGIN
            -- Detect if query contains Arabic characters
            v_is_arabic := p_query ~ '[\\u0600-\\u06FF]';
            
            -- Override with explicit language if provided
            IF p_language = 'ar' THEN
                v_is_arabic := TRUE;
            ELSIF p_language = 'en' THEN
                v_is_arabic := FALSE;
            END IF;
            
            v_search_field := CASE WHEN v_is_arabic THEN 'ar' ELSE 'en' END;

            RETURN QUERY
            WITH scored AS (
                SELECT 
                    m.id,
                    m.code,
                    m.name->>'en' as name_en,
                    m.name->>'ar' as name_ar,
                    m.category_id,
                    m.unit_id,
                    m.price,
                    m.currency_id,
                    GREATEST(
                        CASE 
                            WHEN LOWER(m.name->>v_search_field) = LOWER(p_query) THEN 1.0
                            ELSE 0.0
                        END,
                        similarity(COALESCE(m.name->>v_search_field, ''), p_query),
                        CASE 
                            WHEN m.name->>v_search_field ILIKE '%' || p_query || '%' THEN 0.7
                            ELSE 0.0
                        END,
                        CASE 
                            WHEN m.name->>(CASE WHEN v_is_arabic THEN 'en' ELSE 'ar' END) ILIKE '%' || p_query || '%' THEN 0.5
                            ELSE 0.0
                        END,
                        COALESCE((
                            SELECT MAX(similarity(s.synonym, p_query))
                            FROM material_synonyms s
                            WHERE s.material_id = m.id
                        ), 0.0)
                    )::REAL as relevance
                FROM materials_new m
                WHERE 
                    m.is_active = true
                    AND (p_category_id IS NULL OR m.category_id = p_category_id)
                    AND (
                        m.name->>v_search_field ILIKE '%' || p_query || '%'
                        OR m.name->>(CASE WHEN v_is_arabic THEN 'en' ELSE 'ar' END) ILIKE '%' || p_query || '%'
                        OR similarity(COALESCE(m.name->>'en', ''), p_query) > 0.3
                        OR similarity(COALESCE(m.name->>'ar', ''), p_query) > 0.3
                        OR EXISTS (
                            SELECT 1 FROM material_synonyms s
                            WHERE s.material_id = m.id
                            AND s.synonym ILIKE '%' || p_query || '%'
                        )
                    )
            )
            SELECT 
                scored.id,
                scored.code,
                scored.name_en,
                scored.name_ar,
                scored.category_id,
                scored.unit_id,
                scored.price,
                scored.currency_id,
                scored.relevance
            FROM scored
            WHERE scored.relevance > 0.1
            ORDER BY scored.relevance DESC, scored.price ASC
            LIMIT p_limit;
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    # ========================================================================
    # STEP 7: Insert DEFAULT DATA for reference tables
    # ========================================================================
    
    # Default currencies
    op.execute("""
        INSERT INTO currencies (code, name, symbol, is_default, is_active) VALUES
        ('EGP', '{"en": "Egyptian Pound", "ar": "جنيه مصري"}', 'ج.م', true, true),
        ('USD', '{"en": "US Dollar", "ar": "دولار أمريكي"}', '$', false, true),
        ('SAR', '{"en": "Saudi Riyal", "ar": "ريال سعودي"}', 'ر.س', false, true),
        ('EUR', '{"en": "Euro", "ar": "يورو"}', '€', false, true)
    """)
    
    # Default units
    op.execute("""
        INSERT INTO units (code, name, symbol, unit_type, is_active) VALUES
        ('piece', '{"en": "Piece", "ar": "قطعة"}', 'pc', 'count', true),
        ('unit', '{"en": "Unit", "ar": "وحدة"}', 'u', 'count', true),
        ('m', '{"en": "Meter", "ar": "متر"}', 'm', 'length', true),
        ('m2', '{"en": "Square Meter", "ar": "متر مربع"}', 'm²', 'area', true),
        ('m3', '{"en": "Cubic Meter", "ar": "متر مكعب"}', 'm³', 'volume', true),
        ('kg', '{"en": "Kilogram", "ar": "كيلوجرام"}', 'kg', 'weight', true),
        ('ton', '{"en": "Ton", "ar": "طن"}', 't', 'weight', true),
        ('bag', '{"en": "Bag", "ar": "شيكارة"}', 'bag', 'count', true),
        ('liter', '{"en": "Liter", "ar": "لتر"}', 'L', 'volume', true),
        ('roll', '{"en": "Roll", "ar": "رول"}', 'roll', 'count', true),
        ('hour', '{"en": "Hour", "ar": "ساعة"}', 'hr', 'time', true),
        ('day', '{"en": "Day", "ar": "يوم"}', 'day', 'time', true),
        ('sqft', '{"en": "Square Foot", "ar": "قدم مربع"}', 'ft²', 'area', true)
    """)
    
    # Default material categories
    op.execute("""
        INSERT INTO categories (code, name, category_type, sort_order, is_active) VALUES
        ('cement', '{"en": "Cement", "ar": "أسمنت"}', 'material', 1, true),
        ('steel', '{"en": "Steel & Iron", "ar": "حديد وصلب"}', 'material', 2, true),
        ('bricks', '{"en": "Bricks & Blocks", "ar": "طوب وبلوكات"}', 'material', 3, true),
        ('sand', '{"en": "Sand & Aggregates", "ar": "رمل وركام"}', 'material', 4, true),
        ('concrete', '{"en": "Concrete", "ar": "خرسانة"}', 'material', 5, true),
        ('wood', '{"en": "Wood & Timber", "ar": "أخشاب"}', 'material', 6, true),
        ('tiles', '{"en": "Tiles & Flooring", "ar": "بلاط وأرضيات"}', 'material', 7, true),
        ('paint', '{"en": "Paints & Finishes", "ar": "دهانات وتشطيبات"}', 'material', 8, true),
        ('plumbing', '{"en": "Plumbing Materials", "ar": "مواد سباكة"}', 'material', 9, true),
        ('electrical', '{"en": "Electrical Materials", "ar": "مواد كهرباء"}', 'material', 10, true),
        ('insulation', '{"en": "Insulation", "ar": "عزل"}', 'material', 11, true),
        ('fixtures', '{"en": "Fixtures & Fittings", "ar": "تركيبات"}', 'material', 12, true),
        ('glass', '{"en": "Glass", "ar": "زجاج"}', 'material', 13, true),
        ('adhesives', '{"en": "Adhesives & Sealants", "ar": "لواصق ومانعات تسرب"}', 'material', 14, true),
        ('tools', '{"en": "Tools & Equipment", "ar": "أدوات ومعدات"}', 'material', 15, true)
    """)
    
    # Default labor categories
    op.execute("""
        INSERT INTO categories (code, name, category_type, sort_order, is_active) VALUES
        ('labor_masonry', '{"en": "Masonry Work", "ar": "أعمال بناء"}', 'labor', 101, true),
        ('labor_electrical', '{"en": "Electrical Work", "ar": "أعمال كهرباء"}', 'labor', 102, true),
        ('labor_plumbing', '{"en": "Plumbing Work", "ar": "أعمال سباكة"}', 'labor', 103, true),
        ('labor_painting', '{"en": "Painting Work", "ar": "أعمال دهانات"}', 'labor', 104, true),
        ('labor_tiling', '{"en": "Tiling Work", "ar": "أعمال بلاط"}', 'labor', 105, true),
        ('labor_carpentry', '{"en": "Carpentry Work", "ar": "أعمال نجارة"}', 'labor', 106, true),
        ('labor_plastering', '{"en": "Plastering Work", "ar": "أعمال محارة"}', 'labor', 107, true),
        ('labor_welding', '{"en": "Welding Work", "ar": "أعمال لحام"}', 'labor', 108, true),
        ('labor_general', '{"en": "General Labor", "ar": "عمالة عامة"}', 'labor', 109, true),
        ('labor_supervision', '{"en": "Supervision", "ar": "إشراف"}', 'labor', 110, true)
    """)


def downgrade() -> None:
    # Drop search function
    op.execute('DROP FUNCTION IF EXISTS search_materials_multilingual')
    
    # Drop new session tables
    op.drop_index('ix_conversation_memory_new_key', table_name='conversation_memory_new')
    op.drop_index('ix_conversation_memory_new_user', table_name='conversation_memory_new')
    op.drop_index('ix_conversation_memory_new_session', table_name='conversation_memory_new')
    op.drop_index('ix_conversation_memory_new_id', table_name='conversation_memory_new')
    op.drop_table('conversation_memory_new')
    
    op.drop_index('ix_agent_sessions_new_quotation', table_name='agent_sessions_new')
    op.drop_index('ix_agent_sessions_new_session_id', table_name='agent_sessions_new')
    op.drop_index('ix_agent_sessions_new_id', table_name='agent_sessions_new')
    op.drop_table('agent_sessions_new')
    
    # Drop quotation_items
    op.drop_index('ix_quotation_items_type', table_name='quotation_items')
    op.drop_index('ix_quotation_items_labor', table_name='quotation_items')
    op.drop_index('ix_quotation_items_material', table_name='quotation_items')
    op.drop_index('ix_quotation_items_quotation', table_name='quotation_items')
    op.drop_table('quotation_items')
    
    # Remove language_preference from quotations
    op.drop_column('quotations', 'language_preference')
    
    # Drop labor_rates_new
    op.drop_index('ix_labor_rates_new_active', table_name='labor_rates_new')
    op.drop_index('ix_labor_rates_new_role_ar_trgm', table_name='labor_rates_new')
    op.drop_index('ix_labor_rates_new_role_en_trgm', table_name='labor_rates_new')
    op.drop_index('ix_labor_rates_new_role_ar', table_name='labor_rates_new')
    op.drop_index('ix_labor_rates_new_role_en', table_name='labor_rates_new')
    op.drop_index('ix_labor_rates_new_role_gin', table_name='labor_rates_new')
    op.drop_index('ix_labor_rates_new_category', table_name='labor_rates_new')
    op.drop_index('ix_labor_rates_new_code', table_name='labor_rates_new')
    op.drop_index('ix_labor_rates_new_id', table_name='labor_rates_new')
    op.drop_table('labor_rates_new')
    
    # Drop material_synonyms
    op.drop_index('ix_material_synonyms_trgm', table_name='material_synonyms')
    op.drop_index('ix_material_synonyms_synonym', table_name='material_synonyms')
    op.drop_index('ix_material_synonyms_lang', table_name='material_synonyms')
    op.drop_index('ix_material_synonyms_material', table_name='material_synonyms')
    op.drop_table('material_synonyms')
    
    # Drop materials_new
    op.drop_index('ix_materials_new_active', table_name='materials_new')
    op.drop_index('ix_materials_new_name_ar_trgm', table_name='materials_new')
    op.drop_index('ix_materials_new_name_en_trgm', table_name='materials_new')
    op.drop_index('ix_materials_new_name_ar', table_name='materials_new')
    op.drop_index('ix_materials_new_name_en', table_name='materials_new')
    op.drop_index('ix_materials_new_name_gin', table_name='materials_new')
    op.drop_index('ix_materials_new_category', table_name='materials_new')
    op.drop_index('ix_materials_new_code', table_name='materials_new')
    op.drop_index('ix_materials_new_id', table_name='materials_new')
    op.drop_table('materials_new')
    
    # Drop reference tables
    op.drop_index('ix_categories_name_gin', table_name='categories')
    op.drop_index('ix_categories_parent', table_name='categories')
    op.drop_index('ix_categories_type', table_name='categories')
    op.drop_index('ix_categories_code', table_name='categories')
    op.drop_table('categories')
    
    op.drop_index('ix_units_code', table_name='units')
    op.drop_table('units')
    
    op.drop_index('ix_currencies_code', table_name='currencies')
    op.drop_table('currencies')