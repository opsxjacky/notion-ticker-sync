import os
import akshare as ak
from notion_client import Client

# Configuration
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("DATABASE_ID")

# Initialize Notion client
notion = None
if NOTION_TOKEN:
    notion = Client(auth=NOTION_TOKEN, notion_version="2025-09-03")

def get_china_10y_bond_yield():
    """
    Fetches the latest 10-year China government bond yield using akshare.
    Uses bond_zh_us_rate API which provides up-to-date data.
    """
    try:
        # Fetch bond yield data from akshare (中美国债收益率)
        df = ak.bond_zh_us_rate()

        # Filter out rows with NaN values for China 10Y yield
        df_valid = df.dropna(subset=['中国国债收益率10年'])

        if df_valid.empty:
            print("No valid data found for China 10Y bond yield")
            return None

        # Get the most recent valid data point
        latest_data = df_valid.iloc[-1]

        # Extract the 10-year yield value
        yield_value = latest_data['中国国债收益率10年']

        return float(yield_value)
    except Exception as e:
        print(f"Error fetching bond yield: {e}")
        return None

def find_page_id_by_ticker(ticker):
    """
    Searches the Notion database for a page with the specific ticker name.
    Uses multi-datasource query (same as main.py).
    """
    if not notion:
        print("Notion client not initialized")
        return None

    try:
        # Get database info
        database = notion.databases.retrieve(database_id=DATABASE_ID)

        # Check if it has data sources (multi-datasource database)
        if 'data_sources' in database and database['data_sources']:
            data_source_id = database['data_sources'][0]['id']
            response = notion.data_sources.query(data_source_id=data_source_id)
            pages = response.get("results", [])
        else:
            raise Exception("Single datasource database not supported")

        # Find the page with matching ticker
        for page in pages:
            props = page.get("properties", {})
            # Try both "股票代码" and "Ticker" as title property
            ticker_obj = props.get("股票代码") or props.get("Ticker")
            if ticker_obj and ticker_obj.get("title"):
                ticker_list = ticker_obj["title"]
                if ticker_list and ticker_list[0].get("text", {}).get("content") == ticker:
                    return page["id"]

        print(f"No page found for ticker: {ticker}")
        return None
    except Exception as e:
        print(f"Error searching Notion database: {e}")
        return None

def update_notion_yield(page_id, yield_value):
    """
    Updates the 'Yield' property of a specific Notion page.
    """
    if not notion:
        print("Notion client not initialized")
        return False

    try:
        notion.pages.update(
            page_id=page_id,
            properties={
                "Yield": {"number": yield_value}
            }
        )
        return True
    except Exception as e:
        print(f"Error updating Notion page: {e}")
        return False

if __name__ == "__main__":
    # Bond ETFs that use 10-year China government bond yield
    TARGET_TICKERS = ["511520", "511260"]

    print(f"Fetching 10-year China bond yield...")
    current_yield = get_china_10y_bond_yield()

    if current_yield is not None:
        print(f"Current Yield: {current_yield}%")

        for ticker in TARGET_TICKERS:
            print(f"\nSearching for page {ticker} in Notion...")
            page_id = find_page_id_by_ticker(ticker)

            if page_id:
                print(f"Found page ID: {page_id}. Updating Yield field...")
                success = update_notion_yield(page_id, current_yield)

                if success:
                    print(f"Successfully updated {ticker} Yield field.")
                else:
                    print(f"Failed to update {ticker} Yield field.")
            else:
                print(f"Skipping {ticker} due to missing page ID.")
    else:
        print("Process aborted due to missing yield data.")
