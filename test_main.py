@patch('main.ak.fund_etf_spot_em')
@patch('main.ak.stock_zh_a_spot_em')
@patch('main.ak.fund_etf_hist_em')
def test_get_price_from_akshare_success(self, mock_fund_etf_hist_em, mock_stock_zh_a_spot_em, mock_fund_etf_spot_em):
    # Mocking ak.fund_etf_spot_em
    mock_fund_etf_spot_em.return_value = pd.DataFrame({
        '代码': ['510050'],
        '最新价': [3.50]
    })

    # Mocking ak.stock_zh_a_spot_em
    mock_stock_zh_a_spot_em.return_value = pd.DataFrame()

    # Mocking ak.fund_etf_hist_em
    mock_fund_etf_hist_em.return_value = pd.DataFrame()

@patch('main.ak.fund_etf_spot_em')
@patch('main.ak.stock_zh_a_spot_em')
@patch('main.ak.fund_etf_hist_em')
def test_get_price_from_akshare_failure(self, mock_fund_etf_hist_em, mock_stock_zh_a_spot_em, mock_fund_etf_spot_em):
    # Mocking ak.fund_etf_spot_em to return an empty DataFrame
    mock_fund_etf_spot_em.return_value = pd.DataFrame()

    # Mocking ak.stock_zh_a_spot_em
    mock_stock_zh_a_spot_em.return_value = pd.DataFrame()

    # Mocking ak.fund_etf_hist_em
    mock_fund_etf_hist_em.return_value = pd.DataFrame()

@patch('main.AKSHARE_AVAILABLE', False)
def test_get_price_from_akshare_akshare_unavailable(self):
    price = get_price_from_akshare('510050')
    self.assertIsNone(price)

if __name__ == '__main__':
    unittest.main()
