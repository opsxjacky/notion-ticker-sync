import unittest
from unittest.mock import patch, MagicMock
import pandas as pd
import os
import sys

# Ensure the script can be imported from the current directory
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from update_bond_etf_yield import (
    get_china_10y_bond_yield,
    find_page_id_by_ticker,
    update_notion_yield
)

class TestBondYieldUpdate(unittest.TestCase):

    @patch('update_bond_etf_yield.ak.bond_china_yield')
    def test_get_china_10y_bond_yield_success(self, mock_akshare):
        """Test successful fetching of bond yield."""
        # Create a mock DataFrame similar to what akshare returns
        mock_data = {
            '10年期': [2.35, 2.40, 2.45]
        }
        mock_df = pd.DataFrame(mock_data)
        mock_akshare.return_value = mock_df

        result = get_china_10y_bond_yield()

        self.assertEqual(result, 2.45)
        mock_akshare.assert_called_once()

    @patch('update_bond_etf_yield.ak.bond_china_yield')
    def test_get_china_10y_bond_yield_exception(self, mock_akshare):
        """Test handling of exceptions during data fetching."""
        mock_akshare.side_effect = Exception("Network error")

        result = get_china_10y_bond_yield()

        self.assertIsNone(result)

    @patch('update_bond_etf_yield.requests.post')
    def test_find_page_id_by_ticker_success(self, mock_post):
        """Test successfully finding a page ID by ticker."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [{"id": "test-page-id-123"}]
        }
        mock_post.return_value = mock_response

        result = find_page_id_by_ticker("511520")

        self.assertEqual(result, "test-page-id-123")
        mock_post.assert_called_once()

    @patch('update_bond_etf_yield.requests.post')
    def test_find_page_id_by_ticker_not_found(self, mock_post):
        """Test case where ticker is not found in database."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": []
        }
        mock_post.return_value = mock_response

        result = find_page_id_by_ticker("999999")

        self.assertIsNone(result)

    @patch('update_bond_etf_yield.requests.patch')
    def test_update_notion_yield_success(self, mock_patch):
        """Test successful update of Notion page."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_patch.return_value = mock_response

        result = update_notion_yield("test-page-id", 2.5)

        self.assertTrue(result)
        mock_patch.assert_called_once()

    @patch('update_bond_etf_yield.requests.patch')
    def test_update_notion_yield_failure(self, mock_patch):
        """Test handling of exceptions during Notion update."""
        mock_patch.side_effect = Exception("Update failed")

        result = update_notion_yield("test-page-id", 2.5)

        self.assertFalse(result)

if __name__ == '__main__':
    unittest.main()
