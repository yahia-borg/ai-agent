"""Drop old tables and rename new tables

Revision ID: c2_cleanup_old_tables
Revises: c1_normalized_schema
Create Date: 2025-01-09

This migration:
1. Drops old tables (materials, labor_rates, agent_sessions, conversation_memory)
2. Renames new tables to final names (materials_new -> materials, etc.)

WARNING: This migration is destructive and cannot be rolled back with data intact.
Make sure you have backed up any data you need before running this.

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'c2_cleanup_old_tables'
down_revision = 'c1_normalized_schema'
branch_labels = None
depends_on = None


def safe_drop_constraint(constraint_name: str, table_name: str, constraint_type: str):
    """Safely drop a constraint if it exists."""
    try:
        op.drop_constraint(constraint_name, table_name, type_=constraint_type)
    except Exception:
        # Constraint doesn't exist, skip
        pass


def safe_drop_index(index_name: str, table_name: str):
    """Safely drop an index if it exists."""
    try:
        op.drop_index(index_name, table_name=table_name)
    except Exception:
        # Index doesn't exist, skip
        pass


def upgrade() -> None:
    # ========================================================================
    # STEP 1: Drop OLD tables
    # ========================================================================
    
    # Drop old conversation_memory
    safe_drop_index('ix_conversation_memory_key', 'conversation_memory')
    safe_drop_index('ix_conversation_memory_quotation_id', 'conversation_memory')
    safe_drop_index('ix_conversation_memory_user_id', 'conversation_memory')
    safe_drop_index('ix_conversation_memory_id', 'conversation_memory')
    op.execute('DROP TABLE IF EXISTS conversation_memory CASCADE')
    
    # Drop old agent_sessions - use CASCADE to handle any constraints
    op.execute('DROP TABLE IF EXISTS agent_sessions CASCADE')
    
    # Drop old materials
    op.execute('DROP TABLE IF EXISTS materials CASCADE')
    
    # Drop old labor_rates
    op.execute('DROP TABLE IF EXISTS labor_rates CASCADE')
    
    # ========================================================================
    # STEP 2: Rename NEW tables to final names
    # ========================================================================
    
    # --- Rename materials_new -> materials ---
    
    # First, drop foreign keys pointing to materials_new
    safe_drop_constraint('material_synonyms_material_id_fkey', 'material_synonyms', 'foreignkey')
    safe_drop_constraint('quotation_items_material_id_fkey', 'quotation_items', 'foreignkey')
    
    # Rename the table
    op.rename_table('materials_new', 'materials')
    
    # Rename indexes (use execute for safety)
    op.execute('ALTER INDEX IF EXISTS ix_materials_new_id RENAME TO ix_materials_id')
    op.execute('ALTER INDEX IF EXISTS ix_materials_new_code RENAME TO ix_materials_code')
    op.execute('ALTER INDEX IF EXISTS ix_materials_new_category RENAME TO ix_materials_category')
    op.execute('ALTER INDEX IF EXISTS ix_materials_new_name_gin RENAME TO ix_materials_name_gin')
    op.execute('ALTER INDEX IF EXISTS ix_materials_new_name_en RENAME TO ix_materials_name_en')
    op.execute('ALTER INDEX IF EXISTS ix_materials_new_name_ar RENAME TO ix_materials_name_ar')
    op.execute('ALTER INDEX IF EXISTS ix_materials_new_name_en_trgm RENAME TO ix_materials_name_en_trgm')
    op.execute('ALTER INDEX IF EXISTS ix_materials_new_name_ar_trgm RENAME TO ix_materials_name_ar_trgm')
    op.execute('ALTER INDEX IF EXISTS ix_materials_new_active RENAME TO ix_materials_active')
    
    # Re-add foreign keys pointing to renamed table
    op.create_foreign_key(
        'material_synonyms_material_id_fkey',
        'material_synonyms', 'materials',
        ['material_id'], ['id'],
        ondelete='CASCADE'
    )
    op.create_foreign_key(
        'quotation_items_material_id_fkey',
        'quotation_items', 'materials',
        ['material_id'], ['id'],
        ondelete='SET NULL'
    )
    
    # --- Rename labor_rates_new -> labor_rates ---
    
    # First, drop foreign key in quotation_items
    safe_drop_constraint('quotation_items_labor_rate_id_fkey', 'quotation_items', 'foreignkey')
    
    # Rename the table
    op.rename_table('labor_rates_new', 'labor_rates')
    
    # Rename indexes
    op.execute('ALTER INDEX IF EXISTS ix_labor_rates_new_id RENAME TO ix_labor_rates_id')
    op.execute('ALTER INDEX IF EXISTS ix_labor_rates_new_code RENAME TO ix_labor_rates_code')
    op.execute('ALTER INDEX IF EXISTS ix_labor_rates_new_category RENAME TO ix_labor_rates_category')
    op.execute('ALTER INDEX IF EXISTS ix_labor_rates_new_role_gin RENAME TO ix_labor_rates_role_gin')
    op.execute('ALTER INDEX IF EXISTS ix_labor_rates_new_role_en RENAME TO ix_labor_rates_role_en')
    op.execute('ALTER INDEX IF EXISTS ix_labor_rates_new_role_ar RENAME TO ix_labor_rates_role_ar')
    op.execute('ALTER INDEX IF EXISTS ix_labor_rates_new_role_en_trgm RENAME TO ix_labor_rates_role_en_trgm')
    op.execute('ALTER INDEX IF EXISTS ix_labor_rates_new_role_ar_trgm RENAME TO ix_labor_rates_role_ar_trgm')
    op.execute('ALTER INDEX IF EXISTS ix_labor_rates_new_active RENAME TO ix_labor_rates_active')
    
    # Re-add foreign key pointing to renamed table
    op.create_foreign_key(
        'quotation_items_labor_rate_id_fkey',
        'quotation_items', 'labor_rates',
        ['labor_rate_id'], ['id'],
        ondelete='SET NULL'
    )
    
    # --- Rename agent_sessions_new -> agent_sessions ---
    op.rename_table('agent_sessions_new', 'agent_sessions')
    
    # Rename indexes
    op.execute('ALTER INDEX IF EXISTS ix_agent_sessions_new_id RENAME TO ix_agent_sessions_id')
    op.execute('ALTER INDEX IF EXISTS ix_agent_sessions_new_session_id RENAME TO ix_agent_sessions_session_id')
    op.execute('ALTER INDEX IF EXISTS ix_agent_sessions_new_quotation RENAME TO ix_agent_sessions_quotation_id')
    
    # --- Rename conversation_memory_new -> conversation_memory ---
    op.rename_table('conversation_memory_new', 'conversation_memory')
    
    # Rename indexes
    op.execute('ALTER INDEX IF EXISTS ix_conversation_memory_new_id RENAME TO ix_conversation_memory_id')
    op.execute('ALTER INDEX IF EXISTS ix_conversation_memory_new_session RENAME TO ix_conversation_memory_session_id')
    op.execute('ALTER INDEX IF EXISTS ix_conversation_memory_new_user RENAME TO ix_conversation_memory_user_id')
    op.execute('ALTER INDEX IF EXISTS ix_conversation_memory_new_key RENAME TO ix_conversation_memory_key')
    
    # ========================================================================
    # STEP 3: Update the search function to use renamed table
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
                FROM materials m
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
    # STEP 4: Create search function for labor rates
    # ========================================================================
    op.execute("""
        CREATE OR REPLACE FUNCTION search_labor_rates_multilingual(
            p_query TEXT,
            p_language VARCHAR(5) DEFAULT NULL,
            p_category_id INTEGER DEFAULT NULL,
            p_limit INTEGER DEFAULT 10
        )
        RETURNS TABLE (
            id INTEGER,
            code VARCHAR,
            role_en TEXT,
            role_ar TEXT,
            category_id INTEGER,
            hourly_rate NUMERIC,
            daily_rate NUMERIC,
            currency_id INTEGER,
            skill_level VARCHAR,
            relevance REAL
        ) AS $$
        DECLARE
            v_is_arabic BOOLEAN;
            v_search_field TEXT;
        BEGIN
            v_is_arabic := p_query ~ '[\\u0600-\\u06FF]';
            
            IF p_language = 'ar' THEN
                v_is_arabic := TRUE;
            ELSIF p_language = 'en' THEN
                v_is_arabic := FALSE;
            END IF;
            
            v_search_field := CASE WHEN v_is_arabic THEN 'ar' ELSE 'en' END;

            RETURN QUERY
            WITH scored AS (
                SELECT 
                    l.id,
                    l.code,
                    l.role->>'en' as role_en,
                    l.role->>'ar' as role_ar,
                    l.category_id,
                    l.hourly_rate,
                    l.daily_rate,
                    l.currency_id,
                    l.skill_level,
                    GREATEST(
                        CASE 
                            WHEN LOWER(l.role->>v_search_field) = LOWER(p_query) THEN 1.0
                            ELSE 0.0
                        END,
                        similarity(COALESCE(l.role->>v_search_field, ''), p_query),
                        CASE 
                            WHEN l.role->>v_search_field ILIKE '%' || p_query || '%' THEN 0.7
                            ELSE 0.0
                        END,
                        CASE 
                            WHEN l.role->>(CASE WHEN v_is_arabic THEN 'en' ELSE 'ar' END) ILIKE '%' || p_query || '%' THEN 0.5
                            ELSE 0.0
                        END
                    )::REAL as relevance
                FROM labor_rates l
                WHERE 
                    l.is_active = true
                    AND (p_category_id IS NULL OR l.category_id = p_category_id)
                    AND (
                        l.role->>v_search_field ILIKE '%' || p_query || '%'
                        OR l.role->>(CASE WHEN v_is_arabic THEN 'en' ELSE 'ar' END) ILIKE '%' || p_query || '%'
                        OR similarity(COALESCE(l.role->>'en', ''), p_query) > 0.3
                        OR similarity(COALESCE(l.role->>'ar', ''), p_query) > 0.3
                    )
            )
            SELECT 
                scored.id,
                scored.code,
                scored.role_en,
                scored.role_ar,
                scored.category_id,
                scored.hourly_rate,
                scored.daily_rate,
                scored.currency_id,
                scored.skill_level,
                scored.relevance
            FROM scored
            WHERE scored.relevance > 0.1
            ORDER BY scored.relevance DESC
            LIMIT p_limit;
        END;
        $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    """
    WARNING: This downgrade does NOT restore the original data.
    It only recreates the old table structures.
    """
    
    # Drop search functions
    op.execute('DROP FUNCTION IF EXISTS search_labor_rates_multilingual')
    
    # This is a destructive migration - downgrade would require
    # recreating old tables without data, which isn't very useful.
    # 
    # If you need to rollback, restore from backup instead.
    
    raise NotImplementedError(
        "Downgrade not supported for this migration. "
        "Please restore from database backup if rollback is needed."
    )