import unittest
from unittest.mock import patch, MagicMock, mock_open
import pandas as pd
import datetime
import json

from main import get_price_from_akshare, get_exchange_rates

class TestAkshare(unittest.TestCase):

    @patch('main.AKSHARE_AVAILABLE', True)
    @patch('main.ak.fund_etf_spot_em')
    def test_get_price_from_akshare_success_from_etf_spot(self, mock_fund_etf_spot_em):
        """Test successful price retrieval from ETF spot data."""
        mock_fund_etf_spot_em.return_value = pd.DataFrame({
            '代码': ['510050'],
            '最新价': [3.50]
        })
        # Note: we call without cache to trigger the API call mock
        price = get_price_from_akshare('510050', etf_cache=None)
        self.assertEqual(price, 3.50)
        mock_fund_etf_spot_em.assert_called_once()

    @patch('main.AKSHARE_AVAILABLE', True)
    @patch('main.ak.fund_financial_fund_daily_em')
    @patch('main.ak.fund_money_fund_daily_em')
    @patch('main.ak.fund_etf_fund_info_em')
    @patch('main.ak.fund_etf_hist_sina')
    @patch('main.ak.fund_etf_hist_em')
    @patch('main.ak.fund_open_fund_info_em')
    @patch('main.ak.fund_open_fund_daily_em')
    @patch('main.ak.stock_zh_a_spot_em')
    @patch('main.ak.bond_zh_hs_daily')
    @patch('main.ak.fund_etf_spot_em')
    def test_get_price_from_akshare_failure(self, mock_etf_spot, mock_bond_daily, mock_stock_spot, mock_open_daily, mock_open_info, mock_etf_hist, mock_etf_sina, mock_etf_info, mock_money_daily, mock_financial_daily):
        """Test graceful failure when all akshare sources fail."""
        # Mock all akshare calls to return empty dataframes or raise exceptions
        mock_etf_spot.return_value = pd.DataFrame()
        mock_bond_daily.side_effect = Exception("API error")
        mock_stock_spot.return_value = pd.DataFrame()
        mock_open_daily.side_effect = Exception("API error")
        mock_open_info.side_effect = Exception("API error")
        mock_etf_hist.side_effect = Exception("API error")
        mock_etf_sina.side_effect = Exception("API error")
        mock_etf_info.side_effect = Exception("API error")
        mock_money_daily.side_effect = Exception("API error")
        mock_financial_daily.side_effect = Exception("API error")

        price = get_price_from_akshare('999999')
        self.assertIsNone(price)

    @patch('main.AKSHARE_AVAILABLE', False)
    def test_get_price_from_akshare_akshare_unavailable(self):
        """Test behavior when akshare is not installed."""
        price = get_price_from_akshare('510050')
        self.assertIsNone(price)


class TestExchangeRates(unittest.TestCase):
    """Test cases for the get_exchange_rates function with caching."""

    @patch('main.yf.Ticker')
    @patch('os.path.exists')
    @patch('os.path.getmtime')
    @patch('builtins.open', new_callable=mock_open, read_data=json.dumps({'USD': 7.1, 'HKD': 0.91, 'CNY': 1.0}))
    def test_loads_from_valid_cache(self, mock_file, mock_getmtime, mock_exists, mock_ticker):
        """Should load rates from a valid (today's) cache file."""
        mock_exists.return_value = True
        mock_getmtime.return_value = datetime.datetime.now().timestamp()

        rates = get_exchange_rates()

        self.assertEqual(rates, {'USD': 7.1, 'HKD': 0.91, 'CNY': 1.0})
        mock_file.assert_called_once_with('./akshare_cache/exchange_rates.json', 'r')
        mock_ticker.assert_not_called()

    @patch('main.yf.Ticker')
    @patch('os.path.exists')
    @patch('os.path.getmtime')
    @patch('builtins.open', new_callable=mock_open)
    def test_fetches_when_cache_is_stale(self, mock_file, mock_getmtime, mock_exists, mock_ticker):
        """Should fetch new rates if the cache file is from a previous day."""
        mock_exists.return_value = True
        one_day_ago = (datetime.datetime.now() - datetime.timedelta(days=1)).timestamp()
        mock_getmtime.return_value = one_day_ago

        # Mock yfinance Ticker responses
        mock_usd_ticker = MagicMock()
        mock_usd_ticker.fast_info.last_price = 7.25
        mock_hkd_ticker = MagicMock()
        mock_hkd_ticker.fast_info.last_price = 0.92
        mock_ticker.side_effect = lambda code: {'CNY=X': mock_usd_ticker, 'HKDCNY=X': mock_hkd_ticker}.get(code)

        rates = get_exchange_rates()

        self.assertEqual(rates, {'CNY': 1.0, 'USD': 7.25, 'HKD': 0.92})
        self.assertEqual(mock_ticker.call_count, 2)
        mock_file.assert_called_with('./akshare_cache/exchange_rates.json', 'w')

    @patch('main.yf.Ticker')
    @patch('os.path.exists')
    @patch('builtins.open', new_callable=mock_open)
    def test_fetches_when_no_cache(self, mock_file, mock_exists, mock_ticker):
        """Should fetch new rates if no cache file exists."""
        mock_exists.return_value = False

        # Mock yfinance Ticker responses
        mock_usd_ticker = MagicMock()
        mock_usd_ticker.fast_info.last_price = 7.28
        mock_hkd_ticker = MagicMock()
        mock_hkd_ticker.fast_info.last_price = 0.93
        mock_ticker.side_effect = lambda code: {'CNY=X': mock_usd_ticker, 'HKDCNY=X': mock_hkd_ticker}.get(code)

        rates = get_exchange_rates()

        self.assertEqual(rates, {'CNY': 1.0, 'USD': 7.28, 'HKD': 0.93})
        self.assertEqual(mock_ticker.call_count, 2)
        mock_file.assert_called_with('./akshare_cache/exchange_rates.json', 'w')


if __name__ == '__main__':
    unittest.main()
