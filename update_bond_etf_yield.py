import os
import akshare as ak
import requests

# Configuration
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("DATABASE_ID")
NOTION_VERSION = "2022-06-28"

def get_china_10y_bond_yield():
    """
    Fetches the latest 10-year China government bond yield using akshare.
    """
    try:
        # Fetch bond yield data from akshare
        df = ak.bond_china_yield()
        
        # Get the most recent data point (last row)
        latest_data = df.iloc[-1]
        
        # Extract the 10-year yield value
        # The column name in akshare for 10-year is typically '10年期'
        yield_value = latest_data['10年期']
        
        return float(yield_value)
    except Exception as e:
        print(f"Error fetching bond yield: {e}")
        return None

def find_page_id_by_ticker(ticker):
    """
    Searches the Notion database for a page with the specific ticker name.
    Assumes the ticker is stored in the 'Name' (title) property.
    """
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json"
    }
    
    payload = {
        "filter": {
            "property": "Name",
            "title": {
                "equals": ticker
            }
        }
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        
        if data.get("results"):
            return data["results"][0]["id"]
        else:
            print(f"No page found for ticker: {ticker}")
            return None
    except Exception as e:
        print(f"Error searching Notion database: {e}")
        return None

def update_notion_yield(page_id, yield_value):
    """
    Updates the 'Yield' property of a specific Notion page.
    """
    url = f"https://api.notion.com/v1/pages/{page_id}"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json"
    }
    
    payload = {
        "properties": {
            "Yield": {
                "number": yield_value
            }
        }
    }
    
    try:
        response = requests.patch(url, headers=headers, json=payload)
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"Error updating Notion page: {e}")
        return False

if __name__ == "__main__":
    TARGET_TICKER = "511520"
    
    print(f"Fetching 10-year China bond yield...")
    current_yield = get_china_10y_bond_yield()
    
    if current_yield is not None:
        print(f"Current Yield: {current_yield}%")
        
        print(f"Searching for page {TARGET_TICKER} in Notion...")
        page_id = find_page_id_by_ticker(TARGET_TICKER)
        
        if page_id:
            print(f"Found page ID: {page_id}. Updating Yield field...")
            success = update_notion_yield(page_id, current_yield)
            
            if success:
                print("Successfully updated Yield field.")
            else:
                print("Failed to update Yield field.")
        else:
            print("Process aborted due to missing page ID.")
    else:
        print("Process aborted due to missing yield data.")
