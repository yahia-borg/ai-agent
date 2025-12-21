"""
CSV Exporter for Materials, Labor Rates, and Knowledge Items
"""
import csv
import os
from typing import List, Dict, Any


def export_materials_to_csv(materials: List[Dict[str, Any]], output_path: str):
    """
    Export materials to CSV file.
    
    Columns: name, category, unit, price_per_unit, currency, source_document
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        fieldnames = ['name', 'category', 'unit', 'price_per_unit', 'currency', 'source_document']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        
        writer.writeheader()
        for material in materials:
            writer.writerow({
                'name': material.get('name', ''),
                'category': material.get('category', 'General'),
                'unit': material.get('unit', 'unit'),
                'price_per_unit': material.get('price_per_unit', 0),
                'currency': material.get('currency', 'EGP'),
                'source_document': material.get('source_document', '')
            })
    
    print(f"Exported {len(materials)} materials to {output_path}")


def export_labor_to_csv(labor_rates: List[Dict[str, Any]], output_path: str):
    """
    Export labor rates to CSV file.
    
    Columns: role, hourly_rate, currency, source_document
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        fieldnames = ['role', 'hourly_rate', 'currency', 'source_document']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        
        writer.writeheader()
        for labor in labor_rates:
            writer.writerow({
                'role': labor.get('role', ''),
                'hourly_rate': labor.get('hourly_rate', 0),
                'currency': labor.get('currency', 'EGP'),
                'source_document': labor.get('source_document', '')
            })
    
    print(f"Exported {len(labor_rates)} labor rates to {output_path}")


def export_knowledge_to_csv(knowledge_items: List[Dict[str, Any]], output_path: str):
    """
    Export knowledge items to CSV file.
    
    Columns: topic, content, source_document, page_number
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        fieldnames = ['topic', 'content', 'source_document', 'page_number']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        
        writer.writeheader()
        for item in knowledge_items:
            writer.writerow({
                'topic': item.get('topic', ''),
                'content': item.get('content', ''),
                'source_document': item.get('source_document', ''),
                'page_number': item.get('page_number', 1)
            })
    
    print(f"Exported {len(knowledge_items)} knowledge items to {output_path}")


if __name__ == "__main__":
    # Test
    test_materials = [
        {
            "name": "Cement 50kg bag",
            "category": "Building Materials",
            "unit": "bag",
            "price_per_unit": 100,
            "currency": "EGP",
            "source_document": "test.md"
        }
    ]
    
    test_output = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../data/exports/test_materials.csv"))
    export_materials_to_csv(test_materials, test_output)

