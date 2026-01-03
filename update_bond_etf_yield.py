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

def get_china_bond_yield(years=10):
    """
    Fetches the latest China government bond yield using akshare.
    Uses bond_zh_us_rate API which provides up-to-date data.

    Args:
        years: Bond maturity in years (5 or 10)
    """
    column_name = f'中国国债收益率{years}年'
    try:
        # Fetch bond yield data from akshare (中美国债收益率)
        df = ak.bond_zh_us_rate()

        # Filter out rows with NaN values for the specified yield
        df_valid = df.dropna(subset=[column_name])

        if df_valid.empty:
            print(f"No valid data found for China {years}Y bond yield")
            return None

        # Get the most recent valid data point
        latest_data = df_valid.iloc[-1]

        # Extract the yield value
        yield_value = latest_data[column_name]

        return float(yield_value)
    except Exception as e:
        print(f"Error fetching bond yield: {e}")
        return None


def get_china_10y_bond_yield():
    """Fetches the latest 10-year China government bond yield."""
    return get_china_bond_yield(10)


def get_china_5y_bond_yield():
    """Fetches the latest 5-year China government bond yield."""
    return get_china_bond_yield(5)


def get_china_30y_bond_yield():
    """Fetches the latest 30-year China government bond yield."""
    return get_china_bond_yield(30)


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
    # Bond ETFs grouped by bond maturity
    TICKERS_10Y = ["511520", "511260"]  # Use 10-year bond yield
    TICKERS_5Y = ["511010"]  # Use 5-year bond yield
    TICKERS_30Y = ["511090"]  # Use 30-year bond yield

    # Fetch 10-year bond yield
    print("Fetching 10-year China bond yield...")
    yield_10y = get_china_10y_bond_yield()

    if yield_10y is not None:
        print(f"10Y Yield: {yield_10y}%")
        for ticker in TICKERS_10Y:
            print(f"\nSearching for page {ticker} in Notion...")
            page_id = find_page_id_by_ticker(ticker)
            if page_id:
                print(f"Found page ID: {page_id}. Updating Yield field...")
                success = update_notion_yield(page_id, yield_10y)
                if success:
                    print(f"Successfully updated {ticker} Yield field with 10Y rate.")
                else:
                    print(f"Failed to update {ticker} Yield field.")
            else:
                print(f"Skipping {ticker} due to missing page ID.")
    else:
        print("Failed to fetch 10-year bond yield.")

    # Fetch 5-year bond yield
    print("\nFetching 5-year China bond yield...")
    yield_5y = get_china_5y_bond_yield()

    if yield_5y is not None:
        print(f"5Y Yield: {yield_5y}%")
        for ticker in TICKERS_5Y:
            print(f"\nSearching for page {ticker} in Notion...")
            page_id = find_page_id_by_ticker(ticker)
            if page_id:
                print(f"Found page ID: {page_id}. Updating Yield field...")
                success = update_notion_yield(page_id, yield_5y)
                if success:
                    print(f"Successfully updated {ticker} Yield field with 5Y rate.")
                else:
                    print(f"Failed to update {ticker} Yield field.")
            else:
                print(f"Skipping {ticker} due to missing page ID.")
    else:
        print("Failed to fetch 5-year bond yield.")

    # Fetch 30-year bond yield
    print("\nFetching 30-year China bond yield...")
    yield_30y = get_china_30y_bond_yield()

    if yield_30y is not None:
        print(f"30Y Yield: {yield_30y}%")
        for ticker in TICKERS_30Y:
            print(f"\nSearching for page {ticker} in Notion...")
            page_id = find_page_id_by_ticker(ticker)
            if page_id:
                print(f"Found page ID: {page_id}. Updating Yield field...")
                success = update_notion_yield(page_id, yield_30y)
                if success:
                    print(f"Successfully updated {ticker} Yield field with 30Y rate.")
                else:
                    print(f"Failed to update {ticker} Yield field.")
            else:
                print(f"Skipping {ticker} due to missing page ID.")
    else:
        print("Failed to fetch 30-year bond yield.")
