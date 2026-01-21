from app.agent.tools import search_materials, search_standards
import json

def test_tools():
    print("Testing Material Search...")
    # Test 1: Search for 'cement'
    res_mat = search_materials("cement")
    print(f"Query 'cement': {res_mat[:200]}...") # Print first 200 chars
    
    # Test 2: Search for something from Markdown ingestion, e.g., 'Glass' or 'Wood'
    res_md = search_materials("Glass")
    print(f"Query 'Glass': {res_md[:200]}...")

    print("\nTesting Standards Search...")
    # Test 3: Search for 'BIM' (should be in Egyptian Code)
    res_know = search_standards("BIM")
    print(f"Query 'BIM': {res_know[:200]}...")

if __name__ == "__main__":
    test_tools()
