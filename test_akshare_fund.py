import time
import akshare as ak

def test_fund_speed(symbol):
    print(f"🚀 Testing fetching speed for Fund Code: {symbol} ...")
    print("-" * 50)
    
    # Test 1: Open Fund Daily (Usually fastest for OTC funds)
    start = time.time()
    try:
        df = ak.fund_open_fund_daily_em(symbol=symbol)
        success = df is not None and not df.empty
        print(f"1. [fund_open_fund_daily_em] Time: {time.time() - start:.4f}s | Success: {success}")
        if success:
            print(f"   -> Latest Data: {df.iloc[-1].to_dict()}")
    except Exception as e:
        print(f"1. [fund_open_fund_daily_em] Time: {time.time() - start:.4f}s | Error: {e}")

    print("-" * 20)

    # Test 2: Open Fund Info (Net Value Trend)
    start = time.time()
    try:
        df = ak.fund_open_fund_info_em(fund=symbol, indicator="单位净值走势")
        success = df is not None and not df.empty
        print(f"2. [fund_open_fund_info_em]  Time: {time.time() - start:.4f}s | Success: {success}")
    except Exception as e:
        print(f"2. [fund_open_fund_info_em]  Time: {time.time() - start:.4f}s | Error: {e}")

    print("-" * 20)

    # Test 3: ETF History (This is slow for OTC funds and often fails)
    start = time.time()
    try:
        # Using a small date range to minimize data
        import datetime
        end_date = datetime.datetime.now().strftime("%Y%m%d")
        start_date = (datetime.datetime.now() - datetime.timedelta(days=10)).strftime("%Y%m%d")
        
        df = ak.fund_etf_hist_em(symbol=symbol, period="daily", start_date=start_date, end_date=end_date)
        success = df is not None and not df.empty
        print(f"3. [fund_etf_hist_em]        Time: {time.time() - start:.4f}s | Success: {success}")
    except Exception as e:
        print(f"3. [fund_etf_hist_em]        Time: {time.time() - start:.4f}s | Error: {e}")

if __name__ == "__main__":
    # Test with a common open-ended fund code
    test_fund_speed("003847")
