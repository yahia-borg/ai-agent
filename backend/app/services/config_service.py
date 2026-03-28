"""
Construction Configuration Service with in-memory caching.

Provides cached access to all construction configuration values
stored in the database. Falls back to hardcoded defaults if DB
is unreachable.
"""
import time
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

# Cache TTL in seconds (5 minutes)
_CACHE_TTL = 300


# ── Fallback defaults (used if DB is unreachable) ──────────────────
_FALLBACK_DEFAULTS = {
    "contingency_percentage": 0.10,
    "markup_percentage": 0.10,
    "markup_overhead_split": 0.5,
    "standard_compliance_phrase": "طبقاً للمواصفات الفنية وأصول الصناعة وتعليمات المهندس المشرف",
    "standard_compliance_phrase_en": "According to technical specifications, industry standards, and supervising engineer instructions.",
    "default_brand_paint": "Jotun",
    "default_tile_size_porcelain": "60 سم * 60 سم",
    "default_tile_size_ceramic": "40 سم * 40 سم",
    "plaster_mix_render_coat": 300,
    "plaster_mix_spatter_dash": 450,
    "fallback_labor_rates": {
        "engineer": 150.0, "electrician": 60.0, "plumber": 60.0,
        "tiler": 70.0, "painter": 55.0, "carpenter": 65.0,
        "mason": 60.0, "labor": 40.0, "helper": 40.0, "default": 50.0
    },
    "max_per_material_type": {
        "tiles": 1, "stone": 1, "paint": 2, "plaster": 1,
        "cement": 1, "steel": 1, "wood": 1, "pipes": 2,
        "electrical": 2, "glass": 1, "brick": 1, "vinyl": 1, "default": 2
    },
    "finishing_adjustment_luxury": 1.4,
    "finishing_adjustment_premium": 1.2,
    "finishing_adjustment_economy": 0.8,
    "finishing_keywords_luxury": ["luxury", "فاخر"],
    "finishing_keywords_premium": ["premium", "ممتاز"],
    "finishing_keywords_economy": ["economy", "اقتصادي"],
}

_FALLBACK_ROOM_MATERIAL_MULTIPLIERS = {
    "bathroom": {"tile": 2.5, "paint": 0.3, "plaster": 2.5, "pipes": 2.0, "electrical": 0.8, "waterproofing": 1.2, "default": 1.0},
    "kitchen": {"tile": 1.8, "paint": 1.5, "plaster": 2.0, "pipes": 1.5, "electrical": 1.5, "wood": 0.6, "default": 1.0},
    "bedroom": {"tile": 1.0, "paint": 2.8, "plaster": 2.8, "electrical": 1.0, "default": 1.0},
    "living_room": {"tile": 1.1, "paint": 2.8, "plaster": 2.8, "electrical": 1.2, "default": 1.0},
    "reception": {"tile": 1.1, "paint": 3.0, "plaster": 3.0, "electrical": 1.2, "default": 1.0},
    "office": {"tile": 1.1, "paint": 2.5, "plaster": 2.5, "electrical": 2.0, "default": 1.0},
    "meeting_room": {"tile": 1.1, "paint": 2.5, "plaster": 2.5, "electrical": 1.5, "default": 1.0},
    "corridor": {"tile": 1.0, "paint": 2.0, "plaster": 2.0, "electrical": 0.5, "default": 0.8},
    "balcony": {"tile": 1.2, "paint": 1.0, "waterproofing": 1.0, "electrical": 0.3, "default": 0.6},
    "storage": {"tile": 1.0, "paint": 2.0, "plaster": 2.0, "electrical": 0.4, "default": 0.7},
    "open_plan": {"tile": 1.1, "paint": 2.2, "plaster": 2.2, "electrical": 2.0, "default": 1.0},
    "server_room": {"tile": 1.0, "paint": 2.0, "electrical": 3.0, "default": 1.0},
}

_FALLBACK_ROOM_LABOR_MULTIPLIERS = {
    "bathroom": {"plumber": 2.5, "tiler": 2.0, "electrician": 0.8, "painter": 0.3, "plasterer": 1.5, "default": 1.0},
    "kitchen": {"plumber": 2.0, "tiler": 1.5, "electrician": 1.5, "carpenter": 2.5, "painter": 1.0, "plasterer": 1.2, "default": 1.0},
    "bedroom": {"plumber": 0.2, "tiler": 0.8, "electrician": 1.0, "painter": 1.2, "plasterer": 1.0, "carpenter": 1.0, "default": 1.0},
    "living_room": {"plumber": 0.1, "tiler": 1.0, "electrician": 1.2, "painter": 1.2, "plasterer": 1.0, "default": 1.0},
    "reception": {"plumber": 0.1, "tiler": 1.0, "electrician": 1.2, "painter": 1.3, "plasterer": 1.0, "default": 1.0},
    "office": {"plumber": 0.3, "tiler": 1.0, "electrician": 2.0, "painter": 1.0, "carpenter": 1.5, "default": 1.0},
    "corridor": {"plumber": 0.1, "tiler": 0.8, "electrician": 0.5, "painter": 0.8, "default": 0.7},
    "balcony": {"plumber": 0.3, "tiler": 1.0, "electrician": 0.3, "painter": 0.5, "default": 0.5},
    "storage": {"plumber": 0.1, "tiler": 0.5, "electrician": 0.3, "painter": 0.8, "default": 0.5},
}

_FALLBACK_AREA_DEFAULTS = {
    "residential": {"bedroom": 0.20, "living_room": 0.15, "reception": 0.15, "bathroom": 0.06, "kitchen": 0.10, "corridor": 0.08, "balcony": 0.06},
    "commercial": {"office": 0.30, "reception": 0.15, "meeting_room": 0.12, "corridor": 0.10, "storage": 0.08, "open_plan": 0.35, "server_room": 0.05},
}

_FALLBACK_TRADE_MULTIPLIERS = {
    "residential": {"electrician": 1.5, "plumber": 1.2, "tiler": 2.0, "painter": 1.8, "carpenter": 0.8, "mason": 1.0, "plasterer": 1.5, "welder": 0.3, "supervisor": 0.5, "default": 1.0},
    "commercial": {"electrician": 2.5, "plumber": 1.8, "tiler": 2.2, "painter": 2.0, "carpenter": 1.2, "mason": 0.8, "plasterer": 1.8, "welder": 0.5, "supervisor": 0.8, "default": 1.2},
    "factory": {"electrician": 3.0, "plumber": 1.5, "tiler": 1.0, "painter": 1.2, "carpenter": 0.5, "mason": 1.5, "plasterer": 1.0, "welder": 2.0, "supervisor": 1.0, "default": 1.0},
}

_FALLBACK_COST_SPLITS = {
    "flooring": {"supply": 0.65, "installation": 0.15, "transport": 0.05, "misc": 0.15},
    "painting": {"supply": 0.45, "installation": 0.35, "transport": 0.05, "misc": 0.15},
    "plastering": {"supply": 0.30, "installation": 0.50, "transport": 0.05, "misc": 0.15},
    "electrical": {"supply": 0.70, "installation": 0.20, "transport": 0.02, "misc": 0.08},
    "plumbing": {"supply": 0.60, "installation": 0.25, "transport": 0.05, "misc": 0.10},
    "default": {"supply": 0.55, "installation": 0.25, "transport": 0.05, "misc": 0.15},
}

_FALLBACK_CATEGORY_KEYWORDS = {
    "category_detection": {
        "flooring": ["flooring", "tile", "ceramic", "porcelain", "marble", "parquet", "أرضيات", "سيراميك", "بورسلين", "رخام"],
        "painting": ["paint", "painting", "دهان", "دهانات", "طلاء"],
        "plastering": ["plaster", "plastering", "بياض", "محارة", "تخشين"],
        "plumbing": ["plumbing", "plumber", "sanitaryware", "toilet", "sink", "shower", "سباكة", "مواسير", "حمام"],
        "electrical": ["electrical", "electrician", "wiring", "كهرباء", "أسلاك", "مفاتيح"],
        "carpentry": ["carpentry", "carpenter", "door", "window", "نجارة", "أبواب", "شبابيك"],
        "demolition": ["demolition", "breaking", "هدم", "تكسير"],
    },
    "material_type": {
        "tiles": ["tile", "ceramic", "porcelain", "floor tile", "بلاط", "سيراميك", "بورسلين"],
        "stone": ["marble", "granite", "رخام", "جرانيت"],
        "paint": ["paint", "emulsion", "coating", "دهان", "طلاء"],
        "plaster": ["plaster", "skim", "محارة", "بياض"],
        "cement": ["cement", "أسمنت"],
        "steel": ["steel", "iron", "rebar", "حديد"],
        "wood": ["wood", "timber", "parquet", "خشب", "باركيه"],
        "pipes": ["pipe", "diameter", "مواسير", "قطر"],
        "electrical": ["cable", "wire", "switch", "كهرباء", "سلك"],
        "glass": ["glass", "زجاج"],
        "brick": ["brick", "block", "طوب", "بلوك"],
        "vinyl": ["vinyl", "فينيل"],
    },
    "mat_type_detection": {
        "tile": ["tile", "ceramic", "porcelain", "marble", "flooring"],
        "paint": ["paint", "walls", "painting"],
        "plaster": ["plaster", "plastering"],
        "pipes": ["pipe", "plumb", "plumbing"],
        "electrical": ["cable", "wire", "switch", "electric", "electrical"],
        "wood": ["wood", "parquet", "cabinet", "carpentry"],
        "waterproofing": ["waterproof", "insulation"],
        "door": ["door", "window", "doors_windows"],
        "ceiling": ["ceiling", "ceilings"],
    },
    "brand": {"all": ["knauf", "jotun", "sico", "italian", "carrara", "egyptian", "local"]},
    "color": {"all": ["white", "beige", "light beige", "medium beige", "dark", "black", "cream", "brown"]},
    "finish": {"all": ["matt", "matte", "glossy", "semi-glossy", "semi glossy", "satin"]},
    "flooring_preference": {
        "stone": ["رخام", "marble", "granite", "جرانيت", "عايز رخام", "want marble", "عايز جرانيت"],
        "tiles": ["سيراميك", "ceramic", "porcelain", "بلاط", "عايز سيراميك", "want ceramic", "want tile"],
        "wood": ["خشب", "wood", "parquet", "باركيه", "عايز خشب", "want wood"],
    },
}


class ConstructionConfigService:
    """Cached configuration service for construction parameters."""

    # When DB load fails, don't retry for this many seconds (avoids error spam)
    _DB_RETRY_COOLDOWN = 600  # 10 minutes

    def __init__(self):
        self._cache: Dict[str, Any] = {}
        self._cache_timestamps: Dict[str, float] = {}
        self._loaded = False
        self._db_failed = False
        self._db_fail_time: float = 0

    def _is_cache_valid(self, cache_key: str) -> bool:
        ts = self._cache_timestamps.get(cache_key, 0)
        return (time.time() - ts) < _CACHE_TTL

    async def _load_configs(self):
        """Load all configuration from DB into cache."""
        # If DB previously failed, don't retry until cooldown expires
        if self._db_failed and (time.time() - self._db_fail_time) < self._DB_RETRY_COOLDOWN:
            return

        try:
            async with AsyncSessionLocal() as db:
                from app.models.construction_config import (
                    ConstructionConfig, RoomMultiplier, AreaDistributionDefault,
                    TradeMultiplier, CostComponentSplit, CategoryKeyword, DescriptionTemplate
                )

                # Load construction_config
                result = await db.execute(
                    select(ConstructionConfig).filter(ConstructionConfig.is_active == True)
                )
                configs = {}
                for row in result.scalars().all():
                    configs[row.key] = row.value
                self._cache["configs"] = configs

                # Load room multipliers
                result = await db.execute(
                    select(RoomMultiplier).filter(RoomMultiplier.is_active == True)
                )
                mat_mults: Dict[str, Dict[str, float]] = {}
                labor_mults: Dict[str, Dict[str, float]] = {}
                for row in result.scalars().all():
                    target = mat_mults if row.multiplier_type == "material" else labor_mults
                    if row.room_type not in target:
                        target[row.room_type] = {}
                    target[row.room_type][row.category_key] = row.value
                self._cache["room_material_multipliers"] = mat_mults
                self._cache["room_labor_multipliers"] = labor_mults

                # Load area distribution defaults
                result = await db.execute(
                    select(AreaDistributionDefault).filter(AreaDistributionDefault.is_active == True)
                )
                area_defaults: Dict[str, Dict[str, float]] = {}
                for row in result.scalars().all():
                    if row.project_type not in area_defaults:
                        area_defaults[row.project_type] = {}
                    area_defaults[row.project_type][row.room_type] = row.percentage
                self._cache["area_defaults"] = area_defaults

                # Load trade multipliers
                result = await db.execute(
                    select(TradeMultiplier).filter(TradeMultiplier.is_active == True)
                )
                trade_mults: Dict[str, Dict[str, float]] = {}
                for row in result.scalars().all():
                    if row.project_type not in trade_mults:
                        trade_mults[row.project_type] = {}
                    trade_mults[row.project_type][row.trade_key] = row.value
                self._cache["trade_multipliers"] = trade_mults

                # Load cost component splits
                result = await db.execute(
                    select(CostComponentSplit).filter(CostComponentSplit.is_active == True)
                )
                cost_splits: Dict[str, Dict[str, float]] = {}
                split_labels: Dict[str, Dict[str, Any]] = {}
                for row in result.scalars().all():
                    if row.category not in cost_splits:
                        cost_splits[row.category] = {}
                    cost_splits[row.category][row.component] = row.percentage
                    if row.label:
                        split_labels[row.component] = row.label
                self._cache["cost_splits"] = cost_splits
                self._cache["split_labels"] = split_labels

                # Load category keywords
                result = await db.execute(
                    select(CategoryKeyword).filter(CategoryKeyword.is_active == True)
                )
                kw_cache: Dict[str, Dict[str, Any]] = {}
                for row in result.scalars().all():
                    if row.keyword_type not in kw_cache:
                        kw_cache[row.keyword_type] = {}
                    kw_cache[row.keyword_type][row.group_key] = row.keywords
                self._cache["category_keywords"] = kw_cache

                # Load description templates
                result = await db.execute(
                    select(DescriptionTemplate).filter(DescriptionTemplate.is_active == True)
                )
                templates: Dict[str, Dict[str, Any]] = {}
                for row in result.scalars().all():
                    key = f"{row.category}:{row.template_key}"
                    templates[key] = {
                        "template_ar": row.template_ar,
                        "template_en": row.template_en,
                        "variables": row.variables,
                    }
                self._cache["description_templates"] = templates

            now = time.time()
            for key in ["configs", "room_material_multipliers", "room_labor_multipliers",
                        "area_defaults", "trade_multipliers", "cost_splits", "split_labels",
                        "category_keywords", "description_templates"]:
                self._cache_timestamps[key] = now

            self._loaded = True
            self._db_failed = False
            logger.info("Construction config loaded from DB successfully")

        except Exception as e:
            if not self._db_failed:
                logger.warning(f"Failed to load construction config from DB, using fallback defaults: {e}")
            self._db_failed = True
            self._db_fail_time = time.time()
            self._loaded = False

    async def _ensure_loaded(self):
        """Ensure cache is loaded (lazy load on first access)."""
        if not self._loaded or not self._is_cache_valid("configs"):
            await self._load_configs()

    # ── Public API ──────────────────────────────────────────────────

    async def get_config(self, key: str) -> Any:
        """Get a single config value by key."""
        await self._ensure_loaded()
        configs = self._cache.get("configs", {})
        if key in configs:
            return configs[key]
        return _FALLBACK_DEFAULTS.get(key)

    async def get_room_multipliers(self, room_type: str, multiplier_type: str = "material") -> Dict[str, float]:
        """Get room multipliers for a room type. multiplier_type: 'material' or 'labor'."""
        await self._ensure_loaded()
        cache_key = f"room_{multiplier_type}_multipliers"
        data = self._cache.get(cache_key, {})
        if data and room_type in data:
            return data[room_type]
        # Fallback
        fallback = _FALLBACK_ROOM_MATERIAL_MULTIPLIERS if multiplier_type == "material" else _FALLBACK_ROOM_LABOR_MULTIPLIERS
        return fallback.get(room_type, {"default": 1.0})

    async def get_all_room_multipliers(self, multiplier_type: str = "material") -> Dict[str, Dict[str, float]]:
        """Get all room multipliers. multiplier_type: 'material' or 'labor'."""
        await self._ensure_loaded()
        cache_key = f"room_{multiplier_type}_multipliers"
        data = self._cache.get(cache_key, {})
        if data:
            return data
        return _FALLBACK_ROOM_MATERIAL_MULTIPLIERS if multiplier_type == "material" else _FALLBACK_ROOM_LABOR_MULTIPLIERS

    async def get_area_defaults(self, project_type: str) -> Dict[str, float]:
        """Get area distribution defaults for a project type."""
        await self._ensure_loaded()
        data = self._cache.get("area_defaults", {})
        if data and project_type in data:
            return data[project_type]
        return _FALLBACK_AREA_DEFAULTS.get(project_type, {})

    async def get_trade_multipliers(self, project_type: str) -> Dict[str, float]:
        """Get trade multipliers for a project type."""
        await self._ensure_loaded()
        data = self._cache.get("trade_multipliers", {})
        if data and project_type in data:
            return data[project_type]
        return _FALLBACK_TRADE_MULTIPLIERS.get(project_type, _FALLBACK_TRADE_MULTIPLIERS["residential"])

    async def get_cost_splits(self, category: str) -> Dict[str, float]:
        """Get cost component splits for a category."""
        await self._ensure_loaded()
        data = self._cache.get("cost_splits", {})
        if data:
            # Try exact match, then check if category contains a key
            if category in data:
                return data[category]
            cat_lower = category.lower()
            for key in data:
                if key in cat_lower:
                    return data[key]
            if "default" in data:
                return data["default"]
        # Fallback
        cat_lower = category.lower()
        for key in _FALLBACK_COST_SPLITS:
            if key in cat_lower:
                return _FALLBACK_COST_SPLITS[key]
        return _FALLBACK_COST_SPLITS["default"]

    async def get_split_labels(self) -> Dict[str, Any]:
        """Get bilingual labels for cost split components."""
        await self._ensure_loaded()
        return self._cache.get("split_labels", {
            "supply": {"en": "Supply", "ar": "توريد"},
            "installation": {"en": "Installation", "ar": "تركيب"},
            "transport": {"en": "Transport & Site Logistics", "ar": "نقل وتشوينات"},
            "misc": {"en": "Sundries & Overheads", "ar": "مصروفات نثربة وهامش ربح"},
        })

    async def get_category_keywords(self, keyword_type: str) -> Dict[str, Any]:
        """Get all keywords of a given type (e.g. 'category_detection', 'material_type', 'brand')."""
        await self._ensure_loaded()
        data = self._cache.get("category_keywords", {})
        if data and keyword_type in data:
            return data[keyword_type]
        return _FALLBACK_CATEGORY_KEYWORDS.get(keyword_type, {})

    async def get_description_template(self, category: str, template_key: str) -> Optional[Dict[str, Any]]:
        """Get a description template by category and key."""
        await self._ensure_loaded()
        data = self._cache.get("description_templates", {})
        key = f"{category}:{template_key}"
        return data.get(key)

    def invalidate_cache(self):
        """Force cache invalidation (e.g. after admin updates)."""
        self._cache.clear()
        self._cache_timestamps.clear()
        self._loaded = False
        logger.info("Construction config cache invalidated")


# ── Singleton ───────────────────────────────────────────────────────
_config_service_instance: Optional[ConstructionConfigService] = None


def get_config_service() -> ConstructionConfigService:
    """Get or create the singleton config service instance."""
    global _config_service_instance
    if _config_service_instance is None:
        _config_service_instance = ConstructionConfigService()
    return _config_service_instance
