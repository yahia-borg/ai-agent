from app.agent.tools import create_quotation
import json

def test_export():
    print("Testing Quotation Export...")
    
    items = [
        {"name": "Portland Cement", "quantity": 50, "unit_price": 140.0, "unit": "sack"},
        {"name": "Red Brick", "quantity": 1000, "unit_price": 1.5, "unit": "piece"},
        {"name": "Labor (Mason)", "quantity": 10, "unit_price": 200.0, "unit": "hour"}
    ]
    
    items_json = json.dumps(items)
    
    result = create_quotation(items_json)
    print(result)

if __name__ == "__main__":
    test_export()
