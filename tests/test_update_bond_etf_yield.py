import unittest
from unittest.mock import patch, MagicMock
import pandas as pd
import os
import sys

# Add scripts directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))

from update_bond_etf_yield import (
    get_china_bond_yield,
    get_china_10y_bond_yield,
    get_china_5y_bond_yield,
    get_china_30y_bond_yield,
)


class TestBondYieldUpdate(unittest.TestCase):

    @patch('update_bond_etf_yield.ak.bond_zh_us_rate')
    def test_get_china_10y_bond_yield_success(self, mock_akshare):
        """Test successful fetching of 10-year bond yield."""
        mock_data = {
            '日期': ['2025-12-30', '2025-12-31'],
            '中国国债收益率10年': [1.85, 1.8473],
            '中国国债收益率5年': [1.62, 1.6309],
            '中国国债收益率30年': [2.25, 2.2674],
        }
        mock_df = pd.DataFrame(mock_data)
        mock_akshare.return_value = mock_df

        result = get_china_10y_bond_yield()

        self.assertEqual(result, 1.8473)
        mock_akshare.assert_called_once()

    @patch('update_bond_etf_yield.ak.bond_zh_us_rate')
    def test_get_china_5y_bond_yield_success(self, mock_akshare):
        """Test successful fetching of 5-year bond yield."""
        mock_data = {
            '日期': ['2025-12-30', '2025-12-31'],
            '中国国债收益率10年': [1.85, 1.8473],
            '中国国债收益率5年': [1.62, 1.6309],
            '中国国债收益率30年': [2.25, 2.2674],
        }
        mock_df = pd.DataFrame(mock_data)
        mock_akshare.return_value = mock_df

        result = get_china_5y_bond_yield()

        self.assertEqual(result, 1.6309)

    @patch('update_bond_etf_yield.ak.bond_zh_us_rate')
    def test_get_china_30y_bond_yield_success(self, mock_akshare):
        """Test successful fetching of 30-year bond yield."""
        mock_data = {
            '日期': ['2025-12-30', '2025-12-31'],
            '中国国债收益率10年': [1.85, 1.8473],
            '中国国债收益率5年': [1.62, 1.6309],
            '中国国债收益率30年': [2.25, 2.2674],
        }
        mock_df = pd.DataFrame(mock_data)
        mock_akshare.return_value = mock_df

        result = get_china_30y_bond_yield()

        self.assertEqual(result, 2.2674)

    @patch('update_bond_etf_yield.ak.bond_zh_us_rate')
    def test_get_china_bond_yield_exception(self, mock_akshare):
        """Test handling of exceptions during data fetching."""
        mock_akshare.side_effect = Exception("Network error")

        result = get_china_10y_bond_yield()

        self.assertIsNone(result)

    @patch('update_bond_etf_yield.ak.bond_zh_us_rate')
    def test_get_china_bond_yield_empty_data(self, mock_akshare):
        """Test handling of empty data."""
        mock_data = {
            '日期': ['2025-12-31'],
            '中国国债收益率10年': [None],
            '中国国债收益率5年': [None],
            '中国国债收益率30年': [None],
        }
        mock_df = pd.DataFrame(mock_data)
        mock_akshare.return_value = mock_df

        result = get_china_10y_bond_yield()

        self.assertIsNone(result)


if __name__ == '__main__':
    unittest.main()
