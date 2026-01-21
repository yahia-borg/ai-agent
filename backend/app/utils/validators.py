from typing import Optional, List, Dict, Any, Tuple
from app.models.quotation import ProjectType


def validate_project_description(description: str) -> tuple[bool, Optional[str]]:
    """Validate project description"""
    if not description or len(description.strip()) < 10:
        return False, "Project description must be at least 10 characters"
    
    words = description.split()
    if len(words) < 10:
        return False, "Project description must contain at least 10 words"
    
    return True, None


def validate_zip_code(zip_code: Optional[str]) -> tuple[bool, Optional[str]]:
    """Validate zip code format"""
    if not zip_code:
        return True, None  # Optional field
    
    # Remove any non-digit characters
    digits_only = ''.join(filter(str.isdigit, zip_code))
    
    if len(digits_only) == 5 or len(digits_only) == 9:
        return True, None
    
    return False, "Zip code must be 5 or 9 digits"


def validate_project_type(project_type: Optional[ProjectType]) -> tuple[bool, Optional[str]]:
    """Validate project type"""
    if project_type is None:
        return True, None  # Optional field
    
    valid_types = [ProjectType.RESIDENTIAL, ProjectType.COMMERCIAL, 
                   ProjectType.RENOVATION, ProjectType.NEW_CONSTRUCTION]
    
    if project_type not in valid_types:
        return False, f"Invalid project type. Must be one of: {[t.value for t in valid_types]}"
    
    return True, None


# Material consumption rates per square meter (based on Egyptian standards)
CONSUMPTION_RATES = {
    'cement_plastering': 25.0,  # kg per m² for plastering
    'cement_flooring': 10.0,    # kg per m² for flooring
    'paint': 0.5,               # liters per m² (all layers)
    'tiles_waste_factor': 1.05, # 5% waste factor for tiles
    'sand_plastering': 0.05,    # m³ per m² for plastering
    'sand_flooring': 0.03,      # m³ per m² for flooring
}


def validate_quotation_quantities(
    items: List[Dict[str, Any]],
    project_area: Optional[float] = None,
    project_type: Optional[str] = None
) -> Tuple[bool, List[str]]:
    """
    Validate quantities in quotation items based on project specifications.
    
    Args:
        items: List of quotation items with 'name', 'quantity', 'unit' fields
        project_area: Project area in square meters (optional)
        project_type: Type of project (optional)
    
    Returns:
        Tuple of (is_valid, list_of_error_messages)
    """
    errors = []
    
    if not items:
        return True, []
    
    for item in items:
        name = item.get('name', '').lower()
        quantity = item.get('quantity', 0)
        unit = item.get('unit', '').lower()
        
        # Skip validation if quantity is 0 or invalid
        if quantity <= 0:
            continue
        
        # Area-based items validation (flooring, painting, plastering)
        if any(keyword in name for keyword in ['flooring', 'tile', 'ceramic', 'porcelain', 'marble', 'أرضيات']):
            if unit in ['m²', 'm2', 'م²'] and project_area:
                # Tiles should be area × waste factor (1.05 for 5% waste)
                expected_min = project_area * 0.95  # Allow 5% less
                expected_max = project_area * 1.10  # Allow 10% more (includes waste)
                if not (expected_min <= quantity <= expected_max):
                    errors.append(
                        f"Flooring quantity {quantity} m² doesn't match project area {project_area} m² "
                        f"(expected {expected_min:.2f}-{expected_max:.2f} m²)"
                    )
        
        elif any(keyword in name for keyword in ['paint', 'painting', 'دهان', 'طلاء']):
            if unit in ['m²', 'm2', 'م²'] and project_area:
                # Painting area should match project area ±10%
                expected_min = project_area * 0.9
                expected_max = project_area * 1.1
                if not (expected_min <= quantity <= expected_max):
                    errors.append(
                        f"Painting area {quantity} m² doesn't match project area {project_area} m² "
                        f"(expected {expected_min:.2f}-{expected_max:.2f} m²)"
                    )
            elif unit in ['liter', 'l', 'لتر'] and project_area:
                # Paint consumption: ~0.5 liters per m²
                expected_paint = project_area * CONSUMPTION_RATES['paint']
                expected_min = expected_paint * 0.8  # Allow 20% variance
                expected_max = expected_paint * 1.2
                if not (expected_min <= quantity <= expected_max):
                    errors.append(
                        f"Paint quantity {quantity} L seems incorrect for {project_area} m² "
                        f"(expected ~{expected_paint:.2f} L based on 0.5 L/m² standard)"
                    )
        
        elif any(keyword in name for keyword in ['plaster', 'plastering', 'بياض', 'محارة']):
            if unit in ['m²', 'm2', 'م²'] and project_area:
                # Plastering area should match project area ±10%
                expected_min = project_area * 0.9
                expected_max = project_area * 1.1
                if not (expected_min <= quantity <= expected_max):
                    errors.append(
                        f"Plastering area {quantity} m² doesn't match project area {project_area} m² "
                        f"(expected {expected_min:.2f}-{expected_max:.2f} m²)"
                    )
        
        # Material consumption validation
        elif any(keyword in name for keyword in ['cement', 'أسمنت']):
            if unit in ['kg', 'كيلو', 'كجم'] and project_area:
                # Cement for plastering: ~25 kg per m²
                # Allow variance based on usage (plastering vs flooring)
                expected_cement = project_area * CONSUMPTION_RATES['cement_plastering']
                expected_min = expected_cement * 0.7  # Allow 30% variance
                expected_max = expected_cement * 1.5  # Allow for different applications
                if not (expected_min <= quantity <= expected_max):
                    errors.append(
                        f"Cement quantity {quantity} kg seems incorrect for {project_area} m² "
                        f"(expected ~{expected_cement:.2f} kg based on 25 kg/m² standard for plastering)"
                    )
            elif unit in ['sack', 'bag', 'كيس', 'شيكارة'] and project_area:
                # Cement sacks: 50 kg per sack
                # Convert to kg for validation
                quantity_kg = quantity * 50
                expected_cement = project_area * CONSUMPTION_RATES['cement_plastering']
                expected_min = expected_cement * 0.7
                expected_max = expected_cement * 1.5
                if not (expected_min <= quantity_kg <= expected_max):
                    errors.append(
                        f"Cement quantity {quantity} sacks ({quantity_kg} kg) seems incorrect for {project_area} m² "
                        f"(expected ~{expected_cement/50:.1f} sacks based on 25 kg/m² standard)"
                    )
        
        elif any(keyword in name for keyword in ['sand', 'رمل']):
            if unit in ['m³', 'm3', 'م³'] and project_area:
                # Sand for plastering: ~0.05 m³ per m²
                expected_sand = project_area * CONSUMPTION_RATES['sand_plastering']
                expected_min = expected_sand * 0.8
                expected_max = expected_sand * 1.2
                if not (expected_min <= quantity <= expected_max):
                    errors.append(
                        f"Sand quantity {quantity} m³ seems incorrect for {project_area} m² "
                        f"(expected ~{expected_sand:.3f} m³ based on 0.05 m³/m² standard)"
                    )
        
        # Count-based items validation
        elif any(keyword in name for keyword in ['door', 'باب', 'أبواب']):
            if unit in ['unit', 'count', 'عدد', 'مقطوعية']:
                # Doors: typically 1-20 for residential, up to 50 for commercial
                max_doors = 50 if project_type == 'commercial' else 20
                if not (1 <= quantity <= max_doors):
                    errors.append(
                        f"Door quantity {quantity} seems unreasonable "
                        f"(expected 1-{max_doors} for {project_type or 'residential'} projects)"
                    )
        
        elif any(keyword in name for keyword in ['window', 'شباك', 'نافذة', 'شبابيك']):
            if unit in ['unit', 'count', 'عدد']:
                # Windows: typically 1-50 for residential, up to 100 for commercial
                max_windows = 100 if project_type == 'commercial' else 50
                if not (1 <= quantity <= max_windows):
                    errors.append(
                        f"Window quantity {quantity} seems unreasonable "
                        f"(expected 1-{max_windows} for {project_type or 'residential'} projects)"
                    )
        
        elif any(keyword in name for keyword in ['toilet', 'sink', 'shower', 'مرحاض', 'حوض', 'دش']):
            if unit in ['unit', 'count', 'عدد']:
                # Sanitary fixtures: typically 1-10 for residential
                if not (1 <= quantity <= 10):
                    errors.append(
                        f"Sanitary fixture quantity {quantity} seems unreasonable "
                        f"(expected 1-10 for residential projects)"
                    )
    
    return len(errors) == 0, errors


def calculate_expected_quantity(
    item_name: str,
    unit: str,
    project_area: float,
    item_category: Optional[str] = None
) -> Optional[float]:
    """
    Calculate expected quantity for an item based on project area and consumption rates.
    
    Args:
        item_name: Name of the item
        unit: Unit of measurement
        project_area: Project area in square meters
        item_category: Optional category hint
    
    Returns:
        Expected quantity or None if calculation not applicable
    """
    name_lower = item_name.lower()
    unit_lower = unit.lower()
    
    # Area-based items: quantity should match project area
    if unit_lower in ['m²', 'm2', 'م²']:
        if any(keyword in name_lower for keyword in ['flooring', 'tile', 'ceramic', 'porcelain', 'paint', 'plaster', 'أرضيات', 'دهان', 'بياض']):
            # Apply waste factor for tiles
            if any(keyword in name_lower for keyword in ['tile', 'ceramic', 'porcelain', 'سيراميك', 'بورسلين']):
                return project_area * CONSUMPTION_RATES['tiles_waste_factor']
            return project_area
    
    # Material consumption calculations
    if any(keyword in name_lower for keyword in ['cement', 'أسمنت']):
        if unit_lower in ['kg', 'كيلو', 'كجم']:
            return project_area * CONSUMPTION_RATES['cement_plastering']
        elif unit_lower in ['sack', 'bag', 'كيس', 'شيكارة']:
            return (project_area * CONSUMPTION_RATES['cement_plastering']) / 50  # 50 kg per sack
    
    if any(keyword in name_lower for keyword in ['paint', 'دهان']):
        if unit_lower in ['liter', 'l', 'لتر']:
            return project_area * CONSUMPTION_RATES['paint']
    
    if any(keyword in name_lower for keyword in ['sand', 'رمل']):
        if unit_lower in ['m³', 'm3', 'م³']:
            return project_area * CONSUMPTION_RATES['sand_plastering']
    
    return None

