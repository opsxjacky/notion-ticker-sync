import os
import sys
import time
import datetime
import json
import pickle

# --- 虚拟环境检查 ---
# 强烈建议在虚拟环境中运行，以避免与系统库冲突
# 在 CI/CD 或 Docker 环境中，可以设置环境变量 SKIP_VENV_CHECK=1 来跳过
if os.getenv("SKIP_VENV_CHECK") != "1" and sys.prefix == sys.base_prefix:
    print("🛑 错误: 检测到您正在使用系统 Python 环境。")
    print("为了避免依赖冲突，请在虚拟环境中运行此脚本。")
    print("\n请按照以下步骤操作:")
    print("1. 创建虚拟环境 (在项目根目录): python3 -m venv venv")
    print("2. 激活虚拟环境: source venv/bin/activate")
    print("3. 安装依赖: pip install -r requirements.txt")
    print("4. 运行脚本: python3 main.py\n")
    sys.exit(1)

try:
    import pandas as pd
except ImportError:
    print("🛑 错误: 'pandas' 模块未找到。请在激活虚拟环境后，运行 'pip install -r requirements.txt' 安装依赖。")
    sys.exit(1)

try:
    import yfinance as yf
except ImportError:
    yf = None
    print("⚠️ yfinance 未安装，将无法获取美股/港股/加密货币数据（可选安装: pip install yfinance）")

from notion_client import Client

# 尝试导入 akshare（用于获取中国ETF基金数据）
try:
    import akshare as ak
    AKSHARE_AVAILABLE = True
except ImportError:
    ak = None
    AKSHARE_AVAILABLE = False
    print("⚠️ akshare 未安装，将跳过中国ETF基金数据获取（可选安装: pip install akshare）")

# --- 环境变量配置 (CI/CD 注入) ---
# 本地测试时，可以在终端 export 或者直接把字符串填在这里测试(测试完记得删掉)
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("DATABASE_ID")

# 初始化 Notion (允许为空，以便单元测试导入此文件时不报错)
if NOTION_TOKEN and DATABASE_ID:
    notion = Client(auth=NOTION_TOKEN, notion_version="2025-09-03")
else:
    notion = None
    print("⚠️ 环境变量未设置，Notion 客户端未初始化 (仅供测试或本地开发)")

# 常见数字货币代码列表（需要添加 -USD 后缀）
CRYPTO_SYMBOLS = {
    'BTC', 'ETH', 'BNB', 'ADA', 'SOL', 'XRP', 'DOGE', 'DOT', 'MATIC', 
    'AVAX', 'SHIB', 'TRX', 'LTC', 'UNI', 'ATOM', 'ETC', 'XLM', 'ALGO',
    'VET', 'FIL', 'ICP', 'EOS', 'AAVE', 'THETA', 'SAND', 'AXS', 'MANA',
    'GALA', 'ENJ', 'CHZ', 'FLOW', 'NEAR', 'FTM', 'CRV', 'MKR', 'COMP',
    'SNX', 'SUSHI', 'YFI', '1INCH', 'BAT', 'ZRX', 'LINK', 'GRT'
}

# ETF到指数的映射表（用于获取指数PE作为ETF估值参考）
ETF_INDEX_MAPPING = {
    # 沪深300系列
    '510300': '000300',  # 沪深300ETF → 沪深300指数
    '159919': '000300',  # 沪深300ETF → 沪深300指数
    '510330': '000300',  # 沪深300ETF → 沪深300指数

    # 中证500系列
    '510500': '000905',  # 中证500ETF → 中证500指数
    '159922': '000905',  # 中证500ETF → 中证500指数

    # 上证50系列
    '510050': '000016',  # 上证50ETF → 上证50指数
    '510710': '000016',  # 上证50ETF → 上证50指数

    # 科创50系列
    '588000': '000688',  # 科创50ETF → 科创50指数
    '588080': '000688',  # 科创50ETF → 科创50指数

    # 创业板系列 - 使用乐咕乐股的创业板市场整体PE数据
    # 注：创业板指(399006)是深交所指数，中证指数API不提供其PE数据
    # 使用 stock_market_pe_lg('创业板') 获取创业板整体市场PE，更准确反映创业板指的估值
    '159915': 'LG_CYB_MARKET',  # 创业板ETF → 创业板市场整体（乐咕乐股）
    '159949': 'LG_CYB_MARKET',  # 创业板ETF → 创业板市场整体（乐咕乐股）

    # 红利系列
    '510880': '000922',  # 红利ETF → 中证红利指数

    # 券商系列
    '512000': '399975',  # 券商ETF → 证券公司指数
    '512880': '399975',  # 券商ETF → 证券公司指数

    # 银行系列
    '512800': '399986',  # 银行ETF → 中证银行指数

    # 其他行业ETF可以继续添加...
}

# 中国QDII ETF到美股ETF的映射表（用于获取美股PE数据）
QDII_ETF_MAPPING = {
    '159941': 'QQQ',    # 纳指ETF → QQQ (Invesco QQQ Trust)
    '513500': 'SPY',    # 标普500ETF → SPY (SPDR S&P 500 ETF)
    '513100': 'QQQ',    # 纳指100ETF → QQQ
    '513050': 'SPY',    # 标普500ETF(另一只) → SPY
}

# 港股ETF到恒生指数的映射表（用于获取恒生指数PE数据）
HK_ETF_INDEX_MAPPING = {
    '2800.HK': 'HSI',      # 盈富基金 → 恒生指数
    '02800.HK': 'HSI',     # 盈富基金 → 恒生指数
    '2828.HK': 'HSCE',     # 恒生中国企业ETF → 恒生国企指数
    '02828.HK': 'HSCE',    # 恒生中国企业ETF → 恒生国企指数
    '3067.HK': 'HSTECH',   # 恒生科技ETF → 恒生科技指数
    '03067.HK': 'HSTECH',  # 恒生科技ETF → 恒生科技指数
    '159920': 'HSI',       # A股恒生ETF → 恒生指数
}

# PE 缓存目录
CACHE_DIR = "./pe_cache"
# Akshare 数据缓存目录
AKSHARE_CACHE_DIR = "./akshare_cache"

def get_exchange_rates():
    """
    获取实时汇率 (基准: CNY)
    返回: {'USD': 7.28, 'HKD': 0.93, 'CNY': 1.0}
    """
    print("💱 正在获取实时汇率...")
    
    # 检查缓存
    os.makedirs(AKSHARE_CACHE_DIR, exist_ok=True)
    rates_cache_file = os.path.join(AKSHARE_CACHE_DIR, "exchange_rates.json")
    
    try:
        if os.path.exists(rates_cache_file):
            # 检查文件修改时间是否是今天
            mod_time = os.path.getmtime(rates_cache_file)
            if datetime.date.fromtimestamp(mod_time) == datetime.date.today():
                with open(rates_cache_file, 'r') as f:
                    rates = json.load(f)
                print("   - 从缓存加载汇率")
                return rates
    except Exception:
        pass # 缓存读取失败，则重新获取

    rates = {"CNY": 1.0}
    
    if yf is None:
        print("   ⚠️ yfinance 未安装，使用默认汇率")
        rates["USD"] = 7.28
        rates["HKD"] = 0.93
        return rates
    
    # 定义汇率代码 (Yahoo Finance)
    pairs = {
        "USD": "CNY=X",   # 美元 -> 人民币
        "HKD": "HKDCNY=X" # 港币 -> 人民币
    }
    
    for currency, ticker_code in pairs.items():
        try:
            ticker = yf.Ticker(ticker_code)
            price = ticker.fast_info.last_price
            rates[currency] = price
            print(f"   - {currency}/CNY: {price:.4f}")
        except Exception as e:
            print(f"   ⚠️ 获取 {currency} 汇率失败, 使用默认值")
            if currency == "USD": rates["USD"] = 7.28
            if currency == "HKD": rates["HKD"] = 0.93
    
    # 写入缓存
    try:
        with open(rates_cache_file, 'w') as f:
            json.dump(rates, f)
    except Exception:
        pass # 缓存写入失败，不影响主流程
            
    return rates

def auto_detect_currency(ticker_name):
    """
    根据股票代码后缀，自动判断使用什么货币结算
    """
    ticker = ticker_name.upper()
    if ".SS" in ticker or ".SZ" in ticker:
        return "CNY"  # A股
    elif ".HK" in ticker:
        return "HKD"  # 港股
    elif ticker.isdigit() and len(ticker) == 6:
        return "CNY"  # 纯数字6位代码默认为A股/基金
    else:
        return "USD"  # 美股/加密货币/默认

def get_price_from_akshare(ticker_symbol, spot_cache=None, etf_cache=None):
    """
    使用 akshare 获取中国基金价格（备选数据源）
    适用于 yfinance 无法获取的基金代码（ETF、债券基金等）
    支持：51/50开头（上海ETF）、15/16开头（深圳ETF）、10开头（债券基金等）
    
    优化：支持传入 spot_cache 和 etf_cache (dict) 避免重复全量请求
    """
    if not AKSHARE_AVAILABLE:
        return None
    
    try:
        # 判断是上海还是深圳，构建完整代码
        full_code = ""
        if ticker_symbol.startswith('51') or ticker_symbol.startswith('50'):
            # 上海ETF基金
            full_code = f"sh{ticker_symbol}"
        elif ticker_symbol.startswith('15') or ticker_symbol.startswith('16'):
            # 深圳ETF基金
            full_code = f"sz{ticker_symbol}"
        elif ticker_symbol.startswith('10'):
            # 10开头可能是债券基金或其他类型基金（通常是上海）
            full_code = f"sh{ticker_symbol}"
        
        # 方法1: 尝试使用实时行情接口（东方财富 - ETF基金）
        # 优先查缓存
        if etf_cache is not None and ticker_symbol in etf_cache:
            row = etf_cache[ticker_symbol]
            for field in ['最新价', '收盘', '现价', 'close', 'current']:
                val = row.get(field)
                if val is not None and val != '-' and val != '':
                    try:
                        return float(val)
                    except:
                        continue
        
        # 如果缓存没命中且没传缓存，才去请求
        if etf_cache is None:
            try:
                df = ak.fund_etf_spot_em()
                if df is not None and not df.empty:
                    # 查找匹配的代码（精确匹配）
                    match = df[df['代码'] == ticker_symbol]
                    if match.empty:
                        # 如果精确匹配失败，尝试模糊匹配
                        match = df[df['代码'].str.contains(ticker_symbol, na=False)]
                    if not match.empty:
                        # 尝试多个可能的字段名
                        for field in ['最新价', '收盘', '现价', 'close', 'current']:
                            price = match.iloc[0].get(field)
                            if price is not None and price != '-' and price != '':
                                try:
                                    return float(price)
                                except:
                                    continue
            except Exception as e:
                pass
        
        # 方法1b: 尝试使用债券基金实时行情（如果是10开头）
        if ticker_symbol.startswith('10'):
            try:
                # 尝试获取债券基金行情（使用股票接口，因为债券基金可能也在那里）
                df = ak.bond_zh_hs_daily(symbol=ticker_symbol)
                if df is not None and not df.empty:
                    for field in ['收盘', 'close', '收盘价', '最新价']:
                        if field in df.columns:
                            close_price = df[field].iloc[-1]
                            if close_price is not None:
                                try:
                                    return float(close_price)
                                except:
                                    continue
            except:
                pass
        
        # 方法2: 尝试使用股票实时行情（有些ETF和债券基金可能在这里）
        if spot_cache is not None and ticker_symbol in spot_cache:
            row = spot_cache[ticker_symbol]
            for field in ['最新价', '收盘', '现价', 'current', 'close']:
                val = row.get(field)
                if val is not None and val != '-' and val != '':
                    try:
                        return float(val)
                    except:
                        continue
        
        if spot_cache is None:
            try:
                df = ak.stock_zh_a_spot_em()
                if df is not None and not df.empty:
                    match = df[df['代码'] == ticker_symbol]
                    if not match.empty:
                        for field in ['最新价', '收盘', '现价', 'current', 'close']:
                            price = match.iloc[0].get(field)
                            if price is not None and price != '-' and price != '':
                                try:
                                    return float(price)
                                except:
                                    continue
            except:
                pass
        
        # --- 优化：针对 0 开头的代码（通常是开放式基金），优先尝试开放式基金接口 ---
        # 如果上面的 spot_cache (股票) 没命中，且是 0 开头，很大概率是场外基金
        if ticker_symbol.startswith('0'):
            # 场外基金：使用 fund_open_fund_info_em 获取净值走势（注意：参数名是 symbol 不是 fund）
            try:
                df = ak.fund_open_fund_info_em(symbol=ticker_symbol, indicator="单位净值走势")
                if df is not None and not df.empty:
                    # 尝试多个可能的字段名
                    for field in ['净值', 'y', 'nav', '单位净值']:
                        if field in df.columns:
                            nav = df[field].iloc[-1]
                            if nav is not None and str(nav) != 'nan':
                                try:
                                    price = float(nav)
                                    print(f"      [场外基金] 从 fund_open_fund_info_em 获取净值: {price}")
                                    return price
                                except:
                                    continue
                    print(f"      [场外基金] fund_open_fund_info_em 数据字段: {df.columns.tolist()}")
                    print(f"      [场外基金] 未找到有效净值字段")
                else:
                    print(f"      [场外基金] fund_open_fund_info_em 返回空数据")
            except Exception as e:
                print(f"      [场外基金] fund_open_fund_info_em 失败: {e}")

        # 方法3: 尝试获取历史数据（东方财富 - 推荐方法）
        # 注意：对于场外基金，这个接口可能很慢或不支持，所以放在后面
        try:
            # 使用 fund_etf_hist_em 获取最近的数据
            from datetime import timedelta
            end_date = datetime.datetime.now().strftime("%Y%m%d")
            start_date = (datetime.datetime.now() - timedelta(days=5)).strftime("%Y%m%d")
            
            df = ak.fund_etf_hist_em(
                symbol=ticker_symbol,
                period="daily",
                start_date=start_date,
                end_date=end_date,
                adjust=""
            )
            if df is not None and not df.empty:
                # 尝试多个可能的字段名
                for field in ['收盘', 'close', '收盘价']:
                    if field in df.columns:
                        close_price = df[field].iloc[-1]
                        if close_price is not None:
                            try:
                                return float(close_price)
                            except:
                                continue
        except Exception as e:
            pass
        
        # 方法4: 尝试使用新浪接口（备选）
        if full_code:
            try:
                df = ak.fund_etf_hist_sina(symbol=full_code, period="daily", adjust="qfq")
                if df is not None and not df.empty:
                    # 返回最新收盘价
                    for field in ['close', '收盘', '收盘价']:
                        if field in df.columns:
                            close_price = df[field].iloc[-1]
                            if close_price is not None:
                                try:
                                    return float(close_price)
                                except:
                                    continue
            except:
                pass
        
        # 方法5: 尝试使用ETF基金净值接口
        try:
            df = ak.fund_etf_fund_info_em(fund=ticker_symbol, indicator="单位净值走势")
            if df is not None and not df.empty:
                # 获取最新净值
                for field in ['净值', '单位净值', 'nav']:
                    if field in df.columns:
                        nav = df[field].iloc[-1]
                        if nav is not None:
                            try:
                                return float(nav)
                            except:
                                continue
        except:
            pass

        # 方法6: 尝试作为开放式基金获取净值 (通用兜底，不限制代码前缀)
        # 即使上面针对0开头尝试过，如果失败了，这里作为最后的兜底再试一次也无妨
        # 且对于非0开头的开放式基金（极少见但可能存在），这里是唯一入口
        try:
            df = ak.fund_open_fund_daily_em(symbol=ticker_symbol)
            if df is not None and not df.empty:
                for field in ['单位净值', 'nav']:
                    if field in df.columns:
                        nav = df[field].iloc[-1]
                        if nav is not None:
                            try:
                                return float(nav)
                            except:
                                continue
        except:
            pass
        
        try:
            df = ak.fund_open_fund_info_em(fund=ticker_symbol, indicator="单位净值走势")
            if df is not None and not df.empty:
                for field in ['y', 'nav', '单位净值']:
                    if field in df.columns:
                        nav = df[field].iloc[-1]
                        if nav is not None:
                            try:
                                return float(nav)
                            except:
                                continue
        except:
            pass
        
        # 方法7: 尝试作为货币基金获取净值 (针对货币基金)
        try:
            df = ak.fund_money_fund_daily_em(symbol=ticker_symbol)
            if df is not None and not df.empty:
                # 货币基金通常净值为1
                return 1.0
        except:
            pass

        # 方法8: 尝试作为理财型基金
        try:
            df = ak.fund_financial_fund_daily_em(symbol=ticker_symbol)
            if df is not None and not df.empty:
                for field in ['单位净值', 'nav']:
                    if field in df.columns:
                        nav = df[field].iloc[-1]
                        if nav is not None:
                            try:
                                return float(nav)
                            except:
                                continue
        except:
            pass
            
    except Exception as e:
        # 静默失败，返回 None
        pass
    
    return None


def get_hk_pe_series_cached(symbol):
    """从 akshare 获取港股历史 PE 数据并缓存到本地"""
    symbol = symbol.replace(".HK", "").zfill(5)
    cache_file = os.path.join(CACHE_DIR, f"{symbol}_pe.csv")
    if os.path.exists(cache_file):
        df = pd.read_csv(cache_file)
        return df['pe_ratio']
    
    try:
        if hasattr(ak, 'stock_hk_indicator'):
            df = ak.stock_hk_indicator(symbol=symbol)
            if not df.empty:
                df[['trade_date', 'pe_ratio']].to_csv(cache_file, index=False)
                return df['pe_ratio']
    except Exception as e:
        print(f"抓取港股{symbol}历史PE失败：{e}")
    
    return pd.Series([])


def get_pe_series_cached(symbol):
    """从 akshare 获取历史 PE 数据并缓存到本地"""
    # 过滤非股票代码（简单的判断：ETF/基金通常以1, 5开头，债券基金等）
    # A股股票通常以 0, 3, 6, 4, 8 开头
    if not (symbol.startswith('0') or symbol.startswith('3') or symbol.startswith('6') or symbol.startswith('4') or symbol.startswith('8')):
         return pd.Series([])

    cache_file = os.path.join(CACHE_DIR, f"{symbol}_pe.csv")
    if os.path.exists(cache_file):
        df = pd.read_csv(cache_file)
        return df['pe_ttm']
    
    try:
        if hasattr(ak, 'stock_a_lg_indicator'):
            df = ak.stock_a_lg_indicator(symbol=symbol)
            if not df.empty:
                df[['date', 'pe_ttm']].to_csv(cache_file, index=False)
                return df['pe_ttm']
    except Exception as e:
        print(f"抓取{symbol}历史PE失败：{e}")
    
    return pd.Series([])


def get_hk_etf_index_pe(etf_code):
    """
    获取港股ETF对应的恒生指数PE和PE百分位
    参数：
        etf_code: 港股ETF代码，如'2800.HK'
    返回：
        (pe, pe_percentile) 二元组
    """
    # 检查是否有映射
    index_code = HK_ETF_INDEX_MAPPING.get(etf_code)
    if not index_code:
        return None, None

    try:
        import requests
        from bs4 import BeautifulSoup
        import re

        # 恒生指数数据URL（乐咕乐股网）
        index_urls = {
            'HSI': 'https://legulegu.com/stockdata/market/hsi',                     # 恒生指数
            'HSCE': 'https://legulegu.com/stockdata/market/hscei',                  # 恒生国企指数
            'HSTECH': 'https://legulegu.com/stockdata/hsi-theme-index?indexCode=HSTECH'  # 恒生科技指数
        }

        url = index_urls.get(index_code)
        if not url:
            return None, None

        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }

        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        # 解析HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        text = soup.get_text()

        # 提取当前PE
        pe_match = re.search(r'市盈率[：:]\s*([0-9.]+)', text)
        if not pe_match:
            return None, None

        pe = float(pe_match.group(1))

        # 提取历史最高/最低PE计算百分位
        max_pe_match = re.search(r'历史最高[：:]?\s*([0-9.]+)', text)
        min_pe_match = re.search(r'历史最低[：:]?\s*([0-9.]+)', text)

        pe_percentile = None
        if max_pe_match and min_pe_match:
            max_pe = float(max_pe_match.group(1))
            min_pe = float(min_pe_match.group(1))
            pe_percentile = (pe - min_pe) / (max_pe - min_pe) * 100
        else:
            # 使用恒生指数的历史范围作为默认值
            # 基于1973-2025年的历史数据：最高38.1，最低6.2
            if index_code == 'HSI':
                pe_percentile = (pe - 6.2) / (38.1 - 6.2) * 100

        print(f"      [恒生指数] {index_code} PE={pe:.2f}", end="")
        if pe_percentile is not None:
            print(f", 百分位={pe_percentile:.2f}%")
        else:
            print()

        return pe, pe_percentile

    except Exception as e:
        print(f"      [恒生指数] 获取{index_code}失败: {e}")
        return None, None


def get_hk_index_pb_from_etf(index_code):
    """
    通过港股 ETF 获取恒生指数的 PB（市净率）
    由于恒生指数 PB 数据难以通过免费 API 获取，使用 2800.HK（盈富基金）的 PB 作为代理

    参数：
        index_code: 指数代码，如 'HSI'
    返回：
        pb: 市净率，如果无法获取则返回 None
    """
    if index_code != 'HSI':
        # 目前只支持恒生指数
        return None

    try:
        import yfinance as yf

        # 使用盈富基金 2800.HK 的 PB 作为恒生指数 PB 的代理
        ticker = yf.Ticker('2800.HK')
        info = ticker.info
        pb = info.get('priceToBook')

        if pb is not None:
            pb = float(pb)
            print(f"      [恒生指数] 从 2800.HK ETF 获取 PB={pb:.2f}")
            return pb

        return None
    except Exception as e:
        print(f"      [恒生指数] 获取 PB 失败: {e}")
        return None


def _get_pe_from_legulegu(symbol, index_name):
    """
    从乐咕乐股获取指数PE数据
    参数：
        symbol: 乐咕乐股指数名称，如'创业板50'
        index_name: 用于日志的指数名称
    返回：
        (pe, pb, pe_percentile, pb_percentile) 四元组
    """
    pe = None
    pb = None
    pe_percentile = None
    pb_percentile = None

    try:
        df = ak.stock_index_pe_lg(symbol=symbol)
        if df is not None and not df.empty:
            # 获取最新滚动市盈率
            pe = df['滚动市盈率'].iloc[-1]
            if pe is not None:
                try:
                    pe = float(pe)
                except:
                    pe = None

            # 计算PE百分位
            if pe is not None and '滚动市盈率' in df.columns:
                try:
                    pe_series = df['滚动市盈率'].dropna()
                    if len(pe_series) > 0:
                        years = len(pe_series) / 252  # 约252个交易日/年
                        pe_percentile = float((pe_series < pe).sum()) / len(pe_series) * 100
                        print(f"      [乐咕乐股-{index_name}] PE={pe:.2f}, 百分位={pe_percentile:.2f}% (基于{years:.1f}年数据)")
                except Exception as e:
                    print(f"      [乐咕乐股-{index_name}] PE百分位计算失败: {e}")
    except Exception as e:
        print(f"      [乐咕乐股-{index_name}] 获取PE失败: {e}")

    # 尝试获取PB数据
    try:
        df_pb = ak.stock_index_pb_lg(symbol=symbol)
        if df_pb is not None and not df_pb.empty:
            pb = df_pb['市净率'].iloc[-1]
            if pb is not None:
                try:
                    pb = float(pb)
                    # 计算PB百分位
                    pb_series = df_pb['市净率'].dropna()
                    if len(pb_series) > 0:
                        years = len(pb_series) / 252
                        pb_percentile = float((pb_series < pb).sum()) / len(pb_series) * 100
                        print(f"      [乐咕乐股-{index_name}] PB={pb:.2f}, 百分位={pb_percentile:.2f}% (基于{years:.1f}年数据)")
                except Exception as e:
                    pb = None
    except Exception as e:
        pass  # PB数据不是所有指数都有，失败不影响PE

    return pe, pb, pe_percentile, pb_percentile


def _get_market_pe_from_legulegu(symbol, market_name):
    """
    从乐咕乐股获取市场整体PE数据（使用 stock_market_pe_lg 接口）
    """
    pe = None
    pb = None
    pe_percentile = None
    pb_percentile = None

    try:
        df = ak.stock_market_pe_lg(symbol=symbol)
        if df is not None and not df.empty:
            pe = df['平均市盈率'].iloc[-1]
            if pe is not None:
                try:
                    pe = float(pe)
                except:
                    pe = None

            if pe is not None and '平均市盈率' in df.columns:
                try:
                    pe_series = df['平均市盈率'].dropna()
                    if len(pe_series) > 0:
                        years = len(pe_series) / 12
                        pe_percentile = float((pe_series < pe).sum()) / len(pe_series) * 100
                        print(f"      [乐咕乐股-{market_name}] PE={pe:.2f}, 百分位={pe_percentile:.2f}% (基于{years:.1f}年数据)")
                except Exception as e:
                    print(f"      [乐咕乐股-{market_name}] PE百分位计算失败: {e}")
    except Exception as e:
        print(f"      [乐咕乐股-{market_name}] 获取PE失败: {e}")

    return pe, pb, pe_percentile, pb_percentile


def get_etf_index_pe_pb(etf_code):
    """
    获取ETF对应指数的PE、PB和PE/PB百分位
    参数：
        etf_code: ETF代码，如'510300'
    返回：
        (pe, pb, pe_percentile, pb_percentile) 四元组
    """
    if not AKSHARE_AVAILABLE:
        return None, None, None, None

    # 检查是否有映射
    index_code = ETF_INDEX_MAPPING.get(etf_code)
    if not index_code:
        return None, None, None, None

    # 乐咕乐股指数映射（使用 stock_index_pe_lg 接口）
    LG_INDEX_MAPPING = {
        'LG_CYB50': '创业板50',
    }

    # 乐咕乐股市场映射（使用 stock_market_pe_lg 接口，用于获取整体市场PE）
    LG_MARKET_MAPPING = {
        'LG_CYB_MARKET': '创业板',
    }

    # 检查是否使用乐咕乐股接口
    if index_code.startswith('LG_'):
        # 优先检查市场整体PE（stock_market_pe_lg）
        lg_market_symbol = LG_MARKET_MAPPING.get(index_code)
        if lg_market_symbol:
            return _get_market_pe_from_legulegu(lg_market_symbol, f"{lg_market_symbol}市场")

        # 其次检查指数PE（stock_index_pe_lg）
        lg_symbol = LG_INDEX_MAPPING.get(index_code)
        if lg_symbol:
            return _get_pe_from_legulegu(lg_symbol, f"{lg_symbol}指数")

    pe = None
    pb = None
    pe_percentile = None
    pb_percentile = None

    # === 1. 获取PE和PE百分位（使用中证指数API，10年数据）===
    try:
        from datetime import datetime, timedelta
        # 获取10年历史数据
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=3650)).strftime('%Y%m%d')  # 10年前

        df = ak.stock_zh_index_hist_csindex(symbol=index_code, start_date=start_date, end_date=end_date)
        if df is not None and not df.empty:
            latest = df.iloc[-1]
            pe = latest.get('滚动市盈率')
            if pe is not None:
                try:
                    pe = float(pe)
                except:
                    pe = None

            # 计算PE百分位（10年数据）
            if pe is not None and '滚动市盈率' in df.columns:
                try:
                    pe_series = df['滚动市盈率'].dropna()
                    if len(pe_series) > 0:
                        years = len(pe_series) / 252  # 约252个交易日/年
                        pe_percentile = float((pe_series < pe).sum()) / len(pe_series) * 100
                        print(f"      [指数PE] PE={pe:.2f}, 百分位={pe_percentile:.2f}% (基于{years:.1f}年数据)")
                except Exception as e:
                    print(f"      [指数PE百分位] 计算失败: {e}")
    except Exception as e:
        print(f"      [指数PE] 获取失败: {e}")

    # === 2. 获取PB和PB百分位 ===
    try:
        # 获取沪深300等主要指数的PB数据
        index_name_map = {
            '000300': '沪深300',
            '000905': '中证500',
            '000016': '上证50',
            # 其他指数暂时不支持PB
        }
        index_name = index_name_map.get(index_code)

        if index_name:
            df_pb = ak.stock_index_pb_lg(symbol=index_name)
            if df_pb is not None and not df_pb.empty:
                latest_pb = df_pb.iloc[-1]['市净率']
                if latest_pb is not None:
                    try:
                        pb = float(latest_pb)

                        # 计算PB百分位
                        pb_series = df_pb['市净率'].dropna()
                        if len(pb_series) > 0:
                            years = len(pb_series) / 252
                            pb_percentile = float((pb_series < pb).sum()) / len(pb_series) * 100
                            print(f"      [指数PB] PB={pb:.2f}, 百分位={pb_percentile:.2f}% (基于{years:.1f}年数据)")
                    except Exception as e:
                        print(f"      [指数PB] 解析失败: {e}")
    except Exception as e:
        pass  # PB数据不是所有指数都有，失败不影响PE

    return pe, pb, pe_percentile, pb_percentile


def get_pb_ratio(ticker_symbol, calc_currency, stock):
    """
    获取市净率（PB）
    参数：
        ticker_symbol: 股票/ETF代码
        calc_currency: 货币类型
        stock: yfinance Ticker对象（可选）
    返回：
        pb: 市净率，如果无法获取则返回 None
    """
    pb_ratio = None

    # 方法1: 从yfinance获取（适用于美股、港股）
    if stock and calc_currency in ['USD', 'HKD']:
        try:
            stock_info = stock.info
            pb_ratio = stock_info.get('priceToBook')
            if pb_ratio is not None:
                try:
                    pb_ratio = float(pb_ratio)
                    print(f"      [yfinance] 获取PB: {pb_ratio:.2f}")
                except:
                    pb_ratio = None
        except Exception as e:
            pass

    # 方法2: 对于A股ETF，如果有指数映射，可以尝试获取指数PB
    # （目前akshare的中证指数接口不提供PB，这里预留扩展）

    return pb_ratio


def get_roe(ticker_symbol, calc_currency, stock, spot_cache, hk_cache):
    """
    获取净资产收益率（ROE）
    参数：
        ticker_symbol: 股票/ETF代码
        calc_currency: 货币类型
        stock: yfinance Ticker对象（可选）
        spot_cache: A股行情缓存（未使用，保留参数兼容性）
        hk_cache: 港股行情缓存
    返回：
        roe: ROE百分比，如果无法获取则返回 None
    """
    roe = None

    # 方法1: 从yfinance获取（适用于美股、港股）
    if stock and calc_currency in ['USD', 'HKD']:
        try:
            stock_info = stock.info
            roe_value = stock_info.get('returnOnEquity')
            if roe_value is not None:
                try:
                    roe_float = float(roe_value)
                    # yfinance的ROE格式不统一：
                    # - 小于1时是小数形式（如0.15表示15%）
                    # - 大于1时可能已经是百分比形式（如1.71表示171%）
                    # 为了统一，如果值在0-1之间，乘以100；否则直接使用
                    if 0 < roe_float <= 1:
                        roe = roe_float * 100
                    else:
                        # 直接使用原值（可能是百分比形式或异常高的ROE）
                        roe = roe_float
                    print(f"      [yfinance] 获取ROE: {roe:.2f}%")
                except:
                    roe = None
        except Exception as e:
            pass

    # 方法2: 从akshare获取A股ROE（使用财务指标接口）
    # 注意：spot_cache中没有ROE字段，所以直接使用财务指标接口
    if roe is None and calc_currency == 'CNY' and AKSHARE_AVAILABLE:
        try:
            # 使用股票财务指标接口获取ROE
            df = ak.stock_financial_analysis_indicator(symbol=ticker_symbol)
            if df is not None and not df.empty:
                # 获取最新的ROE数据（优先使用加权净资产收益率）
                for field in ['加权净资产收益率(%)', '净资产收益率(%)', 'ROE']:
                    if field in df.columns:
                        latest_roe = df.iloc[-1].get(field) if len(df) > 0 else None
                        if latest_roe is not None and str(latest_roe) != 'nan' and latest_roe != '-':
                            try:
                                roe = float(latest_roe)
                                print(f"      [A股] 从财务指标获取ROE: {roe:.2f}%")
                                break
                            except:
                                continue
        except Exception as e:
            pass  # 静默失败，很多股票可能没有财务数据

    # 方法3: 从akshare获取港股ROE（hk_cache可能有ROE字段）
    if roe is None and calc_currency == 'HKD' and AKSHARE_AVAILABLE:
        hk_code = ticker_symbol.replace(".HK", "").zfill(5)
        if hk_code in hk_cache:
            try:
                row = hk_cache[hk_code]
                for field in ['ROE', 'roe', '净资产收益率', '加权净资产收益率']:
                    roe_value = row.get(field)
                    if roe_value is not None and roe_value != '-' and str(roe_value) != 'nan':
                        try:
                            roe = float(roe_value)
                            print(f"      [港股] 从hk_cache获取ROE: {roe:.2f}%")
                            break
                        except:
                            continue
            except Exception as e:
                pass

    return roe


def get_peg(ticker_symbol, calc_currency, stock, spot_cache, hk_cache):
    """
    获取PEG比率（Price/Earnings to Growth ratio，市盈率相对盈利增长比率）
    PEG = PE / 盈利增长率，用于评估股票估值是否合理
    参数：
        ticker_symbol: 股票/ETF代码
        calc_currency: 货币类型
        stock: yfinance Ticker对象（可选）
        spot_cache: A股行情缓存（未使用，保留参数兼容性）
        hk_cache: 港股行情缓存
    返回：
        peg: PEG比率，如果无法获取则返回 None
    """
    peg = None

    # 方法1: 从yfinance获取（适用于美股、港股）
    if stock and calc_currency in ['USD', 'HKD']:
        try:
            stock_info = stock.info
            # 优先使用trailingPegRatio，因为pegRatio通常为None
            peg_value = stock_info.get('trailingPegRatio') or stock_info.get('pegRatio')
            if peg_value is not None:
                try:
                    peg = float(peg_value)
                    print(f"      [yfinance] 获取PEG: {peg:.2f}")
                except:
                    peg = None
        except Exception as e:
            pass

    # 方法2: 从akshare获取A股PEG（使用财务指标接口）
    # 注意：spot_cache中没有PEG字段，所以直接使用财务指标接口
    if peg is None and calc_currency == 'CNY' and AKSHARE_AVAILABLE:
        try:
            # 使用股票财务指标接口获取PEG
            df = ak.stock_financial_analysis_indicator(symbol=ticker_symbol)
            if df is not None and not df.empty:
                # 获取最新的PEG数据
                for field in ['PEG比率', 'PEG', 'peg']:
                    if field in df.columns:
                        latest_peg = df.iloc[-1].get(field) if len(df) > 0 else None
                        if latest_peg is not None and str(latest_peg) != 'nan' and latest_peg != '-':
                            try:
                                peg = float(latest_peg)
                                print(f"      [A股] 从财务指标获取PEG: {peg:.2f}")
                                break
                            except:
                                continue
        except Exception as e:
            pass  # 静默失败，很多股票可能没有财务数据

    # 方法3: 从akshare获取港股PEG（hk_cache可能有PEG字段）
    if peg is None and calc_currency == 'HKD' and AKSHARE_AVAILABLE:
        hk_code = ticker_symbol.replace(".HK", "").zfill(5)
        if hk_code in hk_cache:
            try:
                row = hk_cache[hk_code]
                for field in ['PEG', 'peg', 'PEG比率']:
                    peg_value = row.get(field)
                    if peg_value is not None and peg_value != '-' and str(peg_value) != 'nan':
                        try:
                            peg = float(peg_value)
                            print(f"      [港股] 从hk_cache获取PEG: {peg:.2f}")
                            break
                        except:
                            continue
            except Exception as e:
                pass

    return peg


def calculate_fund_nav_growth(fund_code):
    """
    计算基金净值增长率
    参数：
        fund_code: 基金代码，如'003847'
    返回：
        dict: {'1m': 增长率%, '3m': 增长率%, '6m': 增长率%, '1y': 增长率%}
        如果无法计算则返回空字典
    """
    if not AKSHARE_AVAILABLE:
        return {}

    # 只处理场外基金（0开头的6位数字）
    if not (fund_code.startswith('0') and len(fund_code) == 6 and fund_code.isdigit()):
        return {}

    try:
        import pandas as pd
        from datetime import datetime, timedelta

        df = ak.fund_open_fund_info_em(symbol=fund_code, indicator='单位净值走势')
        if df is None or df.empty:
            return {}

        df['净值日期'] = pd.to_datetime(df['净值日期'])
        latest = df.iloc[-1]
        latest_date = latest['净值日期']
        latest_nav = float(latest['单位净值'])

        periods = [
            (30, '1m'),
            (90, '3m'),
            (180, '6m'),
            (365, '1y'),
        ]

        growth_rates = {}
        for days, label in periods:
            target_date = latest_date - timedelta(days=days)
            past_data = df[df['净值日期'] <= target_date]
            if not past_data.empty:
                past_nav = float(past_data.iloc[-1]['单位净值'])
                growth = (latest_nav - past_nav) / past_nav * 100
                growth_rates[label] = round(growth, 2)

        if growth_rates:
            print(f"      [基金] 净值增长率: {growth_rates}")

        return growth_rates
    except Exception as e:
        print(f"      [基金] 净值增长率计算失败: {e}")
        return {}


def get_name_price(symbol, currency, spot_cache, etf_cache, hk_cache, open_fund_cache):
    """高速本地查A股/港股名称和现价 (使用已有的缓存)"""
    # A股
    if currency == "CNY":
        if symbol in spot_cache:
            row = spot_cache[symbol]; return row.get('名称', ''), row.get('最新价', None)
        if symbol in etf_cache:
            row = etf_cache[symbol]; return row.get('名称', ''), row.get('最新价', None)
        if symbol in open_fund_cache:
            # 开放式基金列表没有实时价格，只有名称
            row = open_fund_cache[symbol]; return row.get('基金简称', ''), None
    # 港股
    if currency == "HKD":
        hk_code = symbol.replace(".HK", "").zfill(5)
        if hk_code in hk_cache:
            row = hk_cache[hk_code]; return row.get('名称', ''), row.get('最新价', None)
    return '', None


def update_portfolio():
    if not notion:
        raise ValueError("❌ 错误: 未找到 NOTION_TOKEN 或 DATABASE_ID 环境变量")

    # 1. 获取汇率
    rates = get_exchange_rates()
    
    # 2. 预加载 Akshare 行情数据 (加速查询)
    spot_cache = {}
    etf_cache = {}
    hk_cache = {}
    open_fund_cache = {}
    
    if AKSHARE_AVAILABLE:
        print("🚀 正在预加载 A股/ETF/港股 行情数据 (加速查询)...")
        os.makedirs(AKSHARE_CACHE_DIR, exist_ok=True)
        
        # --- A股行情缓存 ---
        spot_cache_file = os.path.join(AKSHARE_CACHE_DIR, "spot_cache.pkl")
        try:
            if os.path.exists(spot_cache_file) and datetime.date.fromtimestamp(os.path.getmtime(spot_cache_file)) == datetime.date.today():
                with open(spot_cache_file, 'rb') as f:
                    spot_cache = pickle.load(f)
                print(f"   - (缓存) 已加载 {len(spot_cache)} 只A股行情")
            else:
                df_spot = ak.stock_zh_a_spot_em()
                if df_spot is not None and not df_spot.empty:
                    spot_cache = {str(row['代码']): row for _, row in df_spot.iterrows()}
                    with open(spot_cache_file, 'wb') as f: pickle.dump(spot_cache, f)
                print(f"   - (实时) 已缓存 {len(spot_cache)} 只A股行情")
        except Exception as e:
            print(f"   ⚠️ 预加载A股行情失败: {e}")

        # --- ETF行情缓存 ---
        etf_cache_file = os.path.join(AKSHARE_CACHE_DIR, "etf_cache.pkl")
        try:
            if os.path.exists(etf_cache_file) and datetime.date.fromtimestamp(os.path.getmtime(etf_cache_file)) == datetime.date.today():
                with open(etf_cache_file, 'rb') as f:
                    etf_cache = pickle.load(f)
                print(f"   - (缓存) 已加载 {len(etf_cache)} 只ETF行情")
            else:
                df_etf = ak.fund_etf_spot_em()
                if df_etf is not None and not df_etf.empty:
                    etf_cache = {str(row['代码']): row for _, row in df_etf.iterrows()}
                    with open(etf_cache_file, 'wb') as f: pickle.dump(etf_cache, f)
                print(f"   - (实时) 已缓存 {len(etf_cache)} 只ETF行情")
        except Exception as e:
            print(f"   ⚠️ 预加载ETF行情失败: {e}")
            
        # --- 港股行情缓存 ---
        hk_cache_file = os.path.join(AKSHARE_CACHE_DIR, "hk_cache.pkl")
        try:
            if os.path.exists(hk_cache_file) and datetime.date.fromtimestamp(os.path.getmtime(hk_cache_file)) == datetime.date.today():
                with open(hk_cache_file, 'rb') as f:
                    hk_cache = pickle.load(f)
                print(f"   - (缓存) 已加载 {len(hk_cache)} 只港股行情")
            else:
                df_hk = ak.stock_hk_spot_em()
                if df_hk is not None and not df_hk.empty:
                    hk_cache = {str(row['代码']): row for _, row in df_hk.iterrows()}
                    with open(hk_cache_file, 'wb') as f: pickle.dump(hk_cache, f)
                print(f"   - (实时) 已缓存 {len(hk_cache)} 只港股行情")
        except Exception as e:
            print(f"   ⚠️ 预加载港股行情失败: {e}")
            
        # --- 开放式基金名称缓存 ---
        open_fund_cache_file = os.path.join(AKSHARE_CACHE_DIR, "open_fund_cache.pkl")
        try:
            if os.path.exists(open_fund_cache_file) and datetime.date.fromtimestamp(os.path.getmtime(open_fund_cache_file)) == datetime.date.today():
                with open(open_fund_cache_file, 'rb') as f:
                    open_fund_cache = pickle.load(f)
                print(f"   - (缓存) 已加载 {len(open_fund_cache)} 只开放式基金名称")
            else:
                df_open_fund = ak.fund_name_em()
                if df_open_fund is not None and not df_open_fund.empty:
                    open_fund_cache = {str(row['基金代码']): row for _, row in df_open_fund.iterrows()}
                    with open(open_fund_cache_file, 'wb') as f: pickle.dump(open_fund_cache, f)
                print(f"   - (实时) 已缓存 {len(open_fund_cache)} 只开放式基金名称")
        except Exception as e:
            print(f"   ⚠️ 预加载开放式基金列表失败: {e}")

    # 3. 查询 Notion 数据库
    print(f"📥 正在查询 Notion 数据库: {DATABASE_ID} ...")
    try:
        # 先获取数据库信息
        database = notion.databases.retrieve(database_id=DATABASE_ID)
        # 检查是否有数据源（多数据源数据库）
        if 'data_sources' in database and database['data_sources']:
            # 使用多数据源查询方式
            data_source_id = database['data_sources'][0]['id']
            response = notion.data_sources.query(data_source_id=data_source_id)
            pages = response.get("results", [])
        else:
            # 单数据源数据库，尝试使用 search 或其他方法
            # 注意：新版 API 可能不再支持直接 query，需要查询页面
            raise Exception("单数据源数据库暂不支持，请使用多数据源数据库")
    except Exception as e:
        print(f"❌ Notion 连接失败: {e}")
        return

    print(f"🔍 找到 {len(pages)} 条持仓记录，开始更新...")

    # 准备 PE 缓存目录
    os.makedirs(CACHE_DIR, exist_ok=True)

    # 4. 遍历更新股票价格
    for page in pages:
        page_id = page["id"]
        props = page["properties"]
        
        # --- 解析股票代码 ---
        try:
            # 兼容 "股票代码" 和 "Ticker" 两种列名
            ticker_obj = props.get("股票代码") or props.get("Ticker")
            if not ticker_obj:
                continue
            ticker_list = ticker_obj["title"]
            if not ticker_list:
                continue  # 跳过空行
            ticker_symbol = ticker_list[0]["text"]["content"]
        except (KeyError, IndexError, AttributeError):
            print("⚠️ 跳过无法识别的行 (缺少股票代码)")
            continue
        
        # --- 确定货币类型 ---
        current_currency_name = "USD"  # 默认
        try:
            currency_prop = props.get("货币")
            if currency_prop and currency_prop.get("select"):
                current_currency_name = currency_prop["select"]["name"]
            else:
                # 如果为空，自动判断
                current_currency_name = auto_detect_currency(ticker_symbol)
        except:
            current_currency_name = auto_detect_currency(ticker_symbol)
        
        # 简单的清洗逻辑：只要包含 "CNY" 或 "人民币" 就当做 CNY
        if "CNY" in current_currency_name or "人民币" in current_currency_name or "🇨🇳" in current_currency_name:
            calc_currency = "CNY"
        elif "HKD" in current_currency_name or "港币" in current_currency_name or "🇭🇰" in current_currency_name:
            calc_currency = "HKD"
        else:
            calc_currency = "USD"
        
        # 确定汇率
        target_rate = rates.get(calc_currency, 1.0)

        # --- 核心逻辑：获取并更新股票价格 ---
        try:
            print(f"🔄 处理: {ticker_symbol} ({calc_currency})...", end="", flush=True)
            
            # 处理不同类型的代码
            yf_ticker = ticker_symbol.upper()  # 转换为大写
            
            # 0. 处理点号：yfinance 需要连字符而不是点号（如 BRK.B -> BRK-B）
            if '.' in yf_ticker:
                yf_ticker = yf_ticker.replace('.', '-')
            
            # 1. 处理数字货币：添加 -USD 后缀
            if yf_ticker in CRYPTO_SYMBOLS:
                yf_ticker = f"{yf_ticker}-USD"
            # 2. 处理 A 股代码：自动添加市场后缀
            # 60开头是上海（.SS），00/30开头是深圳（.SZ）
            elif ticker_symbol.isdigit() and len(ticker_symbol) == 6:
                if ticker_symbol.startswith('60'):
                    yf_ticker = f"{ticker_symbol}.SS"
                elif ticker_symbol.startswith(('00', '30')):
                    yf_ticker = f"{ticker_symbol}.SZ"
            
            # 抓取股价
            stock = None
            if yf:
                stock = yf.Ticker(yf_ticker)
            
            # 尝试多种方式获取价格
            current_price = None
            
            # 方法1: 使用 yfinance 的 fast_info
            try:
                if stock:
                    current_price = stock.fast_info.last_price
            except:
                pass
            
            # 方法2: 如果 fast_info 失败，尝试获取历史数据
            if current_price is None:
                try:
                    if stock:
                        hist = stock.history(period="1d")
                        if not hist.empty:
                            current_price = hist['Close'].iloc[-1]
                except:
                    pass
            
            # 方法3: 如果是中国基金代码且yfinance失败，尝试使用akshare
            # 注意：yfinance 有时会返回 0.0 (例如暂停交易或数据缺失)，这也应该视为失败
            if (current_price is None or (isinstance(current_price, (int, float)) and current_price == 0)) and calc_currency == "CNY":
                # 检查是否是基金代码（只要是6位数字，都尝试去查，包括00开头的场外基金）
                if ticker_symbol.isdigit() and len(ticker_symbol) == 6:
                    try:
                        print(f"\n   [尝试akshare获取 {ticker_symbol}]")
                        # 传入缓存进行查询
                        akshare_price = get_price_from_akshare(ticker_symbol, spot_cache=spot_cache, etf_cache=etf_cache)
                        if akshare_price:
                            current_price = akshare_price
                            print(f" [使用akshare成功: {akshare_price}]", end="", flush=True)
                        else:
                            print(f"   [akshare返回None]")
                    except Exception as e:
                        print(f"   [akshare异常: {e}]")
            
            # 方法4: 如果是港股且yfinance失败，尝试使用akshare
            if (current_price is None or (isinstance(current_price, (int, float)) and current_price == 0)) and calc_currency == "HKD":
                # 尝试从 hk_cache 获取
                # Akshare 港股代码通常是 5位数字，例如 00700
                # Notion/Yfinance 可能是 0700 或 00700
                hk_code = ticker_symbol.replace(".HK", "")
                if len(hk_code) < 5:
                    hk_code = hk_code.zfill(5)
                
                if hk_code in hk_cache:
                    row = hk_cache[hk_code]
                    for field in ['最新价', '收盘', '现价', 'current', 'close']:
                        val = row.get(field)
                        if val is not None and val != '-' and val != '':
                            try:
                                current_price = float(val)
                                print(f" [使用akshare-hk]", end="", flush=True)
                                break
                            except:
                                continue

            # 如果仍然无法获取价格，抛出异常
            if current_price is None or (isinstance(current_price, float) and current_price == 0):
                raise ValueError(f"无法获取 {ticker_symbol} 的价格数据，可能是基金代码或已退市")
            
            # 更新 Notion（使用中文列名）
            # 获取股票名称、PE和PE百分位
            stock_name = ""
            pe_ratio = None
            pe_percentile = None
            
            try:
                stock_name, current_price_a = get_name_price(ticker_symbol, calc_currency, spot_cache, etf_cache, hk_cache, open_fund_cache)
                
                # 若行情查不到则降级原逻辑 (但通常缓存应该有了)
                if not stock_name:
                    try:
                        # 尝试模糊匹配或其他方式，这里简单处理，如果缓存没有，可能就是没有
                        pass
                    except:
                        pass
                
                # 批量缓存A股历史PE并计算百分位
                pe_ratio = None
                pe_percentile = None
                
                # 仅当货币为 CNY 时才尝试作为 A 股获取 PE
                if calc_currency == 'CNY':
                    # 1. 尝试获取历史PE计算百分位
                    try:
                        pe_series = get_pe_series_cached(ticker_symbol)
                        pe_series = pe_series.dropna()
                        if not pe_series.empty:
                            pe_ratio = float(pe_series.iloc[-1])
                            pe_percentile = float((pe_series < pe_ratio).sum()) / len(pe_series) * 100
                    except Exception as e:
                        print(f"{ticker_symbol} 百分位计算异常: {e}")
                    
                    # 2. 如果历史PE获取失败，尝试从实时行情中获取当前PE
                    if pe_ratio is None:
                        # 检查 A股 spot_cache
                        if ticker_symbol in spot_cache:
                            val = spot_cache[ticker_symbol].get('市盈率-动态')
                            if val is not None:
                                try:
                                    pe_ratio = float(val)
                                    print(f"      [A股] 从spot_cache获取PE: {pe_ratio}")
                                except:
                                    pass
                        # 检查 ETF etf_cache
                        if pe_ratio is None and ticker_symbol in etf_cache:
                            # 注意：大多数ETF本身没有PE，但可以尝试查找
                            val = etf_cache[ticker_symbol].get('市盈率-动态') or etf_cache[ticker_symbol].get('市盈率')
                            if val is not None and val != '-' and str(val) != 'nan':
                                try:
                                    pe_ratio = float(val)
                                    print(f"      [ETF] 从etf_cache获取PE: {pe_ratio}")
                                except Exception as e:
                                    print(f"      [ETF] PE转换失败: {val}, 错误: {e}")
                            else:
                                print(f"      [ETF] {ticker_symbol} 缓存中无PE数据（ETF通常无PE指标）")

                        # 3. 如果A股ETF仍然没有PE，尝试从恒生指数获取（如159920）
                        if pe_ratio is None and ticker_symbol in HK_ETF_INDEX_MAPPING:
                            index_pe, index_pe_percentile = get_hk_etf_index_pe(ticker_symbol)
                            if index_pe is not None:
                                pe_ratio = index_pe
                                if index_pe_percentile is not None:
                                    pe_percentile = index_pe_percentile

                # 尝试获取港股 PE (从 Akshare 缓存)
                if calc_currency == 'HKD':
                    # 1. 尝试获取历史PE计算百分位
                    try:
                        pe_series = get_hk_pe_series_cached(ticker_symbol)
                        pe_series = pe_series.dropna()
                        if not pe_series.empty:
                            pe_ratio = float(pe_series.iloc[-1])
                            pe_percentile = float((pe_series < pe_ratio).sum()) / len(pe_series) * 100
                    except Exception as e:
                        print(f"{ticker_symbol} 港股百分位计算异常: {e}")

                    # 2. 如果历史PE获取失败，尝试从实时行情中获取当前PE
                    if pe_ratio is None:
                        hk_code = ticker_symbol.replace(".HK", "").zfill(5)
                        if hk_code in hk_cache:
                            val = hk_cache[hk_code].get('市盈率-动态') or hk_cache[hk_code].get('市盈率')
                            if val is not None:
                                try:
                                    pe_ratio = float(val)
                                except:
                                    pass

                    # 3. 如果港股ETF仍然没有PE，尝试从恒生指数获取
                    if pe_ratio is None and ticker_symbol in HK_ETF_INDEX_MAPPING:
                        index_pe, index_pe_percentile = get_hk_etf_index_pe(ticker_symbol)
                        if index_pe is not None:
                            pe_ratio = index_pe
                            if index_pe_percentile is not None:
                                pe_percentile = index_pe_percentile

                # 尝试使用 yfinance 补充名称、PE、PE百分位
                if stock:
                    try:
                        stock_info = stock.info
                        if not stock_name:
                            stock_name = stock_info.get("shortName", "") or stock_info.get("longName", "")
                        
                        import numpy as np
                        # 如果 PE 未获取到，则从 yfinance 获取
                        if pe_ratio is None:
                            pe_ratio = stock_info.get("trailingPE") or stock_info.get("forwardPE")
                            if pe_ratio is not None:
                                try:
                                    pe_ratio = float(pe_ratio)
                                except (ValueError, TypeError):
                                    pe_ratio = None
                        
                        # 如果 PE 百分位未获取到，则从 yfinance 计算
                        if pe_percentile is None and pe_ratio is not None and pe_ratio > 0:
                            try:
                                hist = stock.history(period="5y", interval="1mo")
                                if hist is not None and not hist.empty:
                                    # 方法1: 使用 trailingEps（如果有）
                                    trailing_eps = stock_info.get("trailingEps")
                                    if trailing_eps is not None and trailing_eps != 0:
                                        hist_pe_ratios = hist['Close'] / float(trailing_eps)
                                        hist_pe_ratios = hist_pe_ratios[hist_pe_ratios > 0]
                                        if not hist_pe_ratios.empty:
                                            pe_percentile = float(np.sum(hist_pe_ratios < pe_ratio)) / len(hist_pe_ratios) * 100
                                            print(f"      [美股] 计算PE百分位(用EPS): {pe_percentile:.2f}%")
                                    else:
                                        # 方法2: 如果没有EPS，使用当前价格和PE反推EPS，然后计算历史PE
                                        # EPS = 当前价格 / 当前PE
                                        current_price_for_calc = hist['Close'].iloc[-1]
                                        if current_price_for_calc > 0:
                                            estimated_eps = current_price_for_calc / pe_ratio
                                            hist_pe_ratios = hist['Close'] / estimated_eps
                                            hist_pe_ratios = hist_pe_ratios[hist_pe_ratios > 0]
                                            if not hist_pe_ratios.empty:
                                                pe_percentile = float(np.sum(hist_pe_ratios < pe_ratio)) / len(hist_pe_ratios) * 100
                                                print(f"      [美股] 计算PE百分位(估算EPS): {pe_percentile:.2f}%")
                            except Exception as e:
                                print(f"      [美股] PE百分位计算失败: {e}")
                            # yfinance 无法直接获取中国A股和无季报历史EPS，港美股可用该方法
                    except:
                        pass
            except Exception as e:
                pass

            # 优先使用加速缓存获取的A股/港股现价
            final_price = current_price
            if calc_currency == "CNY" and current_price_a is not None:
                final_price = current_price_a
            elif calc_currency == "HKD" and current_price_a is not None:
                # 如果 yfinance 失败了，或者我们想优先用 akshare (这里逻辑是如果 yfinance 拿到了就用 yfinance，除非 yfinance 没拿到)
                # 但上面的逻辑是：如果 yfinance 拿到 current_price，就用它。
                # 如果没拿到，才去查 akshare。
                # 所以这里 final_price = current_price 即可，因为 current_price 已经被 akshare 填充了（如果 yfinance 失败）
                pass

            update_props = {
                "现价": {"number": round(final_price, 2) if final_price is not None else None},
                "汇率": {"number": round(target_rate, 4)},
                "货币": {"select": {"name": current_currency_name}}
            }
            if stock_name:
                update_props["股票名称"] = {"rich_text": [{"text": {"content": stock_name}}]}
            
            # 更新 PE 和 PE 百分位 (如果获取不到则清空)
            update_props["PE"] = {"number": round(pe_ratio, 2) if pe_ratio is not None else None}
            update_props["PE百分位"] = {"number": round(pe_percentile, 2) if pe_percentile is not None else None}

            # === 新增：获取PB市净率 ===
            pb_ratio = get_pb_ratio(ticker_symbol, calc_currency, stock)

            # 对于恒生 ETF（如 159920），如果 PB 未获取到，尝试从 2800.HK ETF 获取
            if pb_ratio is None and ticker_symbol in HK_ETF_INDEX_MAPPING:
                index_code = HK_ETF_INDEX_MAPPING.get(ticker_symbol)
                if index_code == 'HSI':
                    pb_ratio = get_hk_index_pb_from_etf(index_code)

            if pb_ratio is not None:
                update_props["PB"] = {"number": round(pb_ratio, 2)}

            # === 新增：获取ROE净资产收益率 ===
            roe = get_roe(ticker_symbol, calc_currency, stock, spot_cache, hk_cache)
            if roe is not None:
                update_props["ROE"] = {"number": round(roe, 2)}

            # === 新增：获取PEG比率 ===
            peg = get_peg(ticker_symbol, calc_currency, stock, spot_cache, hk_cache)
            if peg is not None:
                update_props["PEG"] = {"number": round(peg, 2)}

            # === 新增：对于A股ETF，尝试获取对应指数的PE/PB和百分位（作为估值参考）===
            if calc_currency == "CNY" and pe_ratio is None and ticker_symbol in ETF_INDEX_MAPPING:
                index_pe, index_pb, index_pe_percentile, index_pb_percentile = get_etf_index_pe_pb(ticker_symbol)
                if index_pe is not None:
                    index_name = ETF_INDEX_MAPPING.get(ticker_symbol, '')
                    print(f"      [ETF] 使用指数({index_name})")
                    # 使用指数PE作为ETF的参考PE
                    update_props["PE"] = {"number": round(index_pe, 2)}
                    # 如果有PE百分位，也更新
                    if index_pe_percentile is not None:
                        pe_percentile = index_pe_percentile
                        update_props["PE百分位"] = {"number": round(index_pe_percentile, 2)}
                    # 如果有指数PB，也更新
                    if index_pb is not None and pb_ratio is None:
                        pb_ratio = index_pb
                        update_props["PB"] = {"number": round(index_pb, 2)}

            # === 新增：对于QDII ETF（如纳指ETF/标普500ETF），使用美股对应ETF的PE数据 ===
            if ticker_symbol in QDII_ETF_MAPPING:
                us_etf_ticker = QDII_ETF_MAPPING[ticker_symbol]
                print(f"      [QDII ETF] 使用美股ETF({us_etf_ticker})数据")
                try:
                    if yf:
                        us_etf_stock = yf.Ticker(us_etf_ticker)
                        us_etf_info = us_etf_stock.info

                        # 获取PE
                        us_pe = us_etf_info.get("trailingPE") or us_etf_info.get("forwardPE")
                        if us_pe is not None:
                            try:
                                us_pe = float(us_pe)
                                pe_ratio = us_pe
                                update_props["PE"] = {"number": round(us_pe, 2)}
                                print(f"      [QDII ETF] 获取{us_etf_ticker} PE: {us_pe:.2f}")

                                # 计算PE百分位（使用5年历史数据）
                                import numpy as np
                                hist = us_etf_stock.history(period="5y", interval="1mo")
                                if hist is not None and not hist.empty:
                                    trailing_eps = us_etf_info.get("trailingEps")
                                    if trailing_eps is not None and trailing_eps != 0:
                                        hist_pe_ratios = hist['Close'] / float(trailing_eps)
                                        hist_pe_ratios = hist_pe_ratios[hist_pe_ratios > 0]
                                        if not hist_pe_ratios.empty:
                                            us_pe_percentile = float(np.sum(hist_pe_ratios < us_pe)) / len(hist_pe_ratios) * 100
                                            pe_percentile = us_pe_percentile
                                            update_props["PE百分位"] = {"number": round(us_pe_percentile, 2)}
                                            print(f"      [QDII ETF] 计算{us_etf_ticker} PE百分位: {us_pe_percentile:.2f}%")
                                    else:
                                        # 使用当前价格和PE反推EPS
                                        current_price_for_calc = hist['Close'].iloc[-1]
                                        if current_price_for_calc > 0 and us_pe > 0:
                                            estimated_eps = current_price_for_calc / us_pe
                                            hist_pe_ratios = hist['Close'] / estimated_eps
                                            hist_pe_ratios = hist_pe_ratios[hist_pe_ratios > 0]
                                            if not hist_pe_ratios.empty:
                                                us_pe_percentile = float(np.sum(hist_pe_ratios < us_pe)) / len(hist_pe_ratios) * 100
                                                pe_percentile = us_pe_percentile
                                                update_props["PE百分位"] = {"number": round(us_pe_percentile, 2)}
                                                print(f"      [QDII ETF] 计算{us_etf_ticker} PE百分位(估算): {us_pe_percentile:.2f}%")
                            except Exception as e:
                                print(f"      [QDII ETF] 处理PE数据失败: {e}")
                except Exception as e:
                    print(f"      [QDII ETF] 获取{us_etf_ticker}数据失败: {e}")

            # === 新增：对于场外基金，计算净值增长率 ===
            growth_rates = {}
            if ticker_symbol.startswith('0') and len(ticker_symbol) == 6 and ticker_symbol.isdigit():
                growth_rates = calculate_fund_nav_growth(ticker_symbol)
                # 计算增长率仅用于日志输出，不写入Notion
                # 如果需要写入，请在Notion添加"年化收益"字段并取消下面的注释：
                # if growth_rates and '1y' in growth_rates:
                #     update_props["年化收益"] = {"number": round(growth_rates['1y'], 2)}

            # 如果 Notion 数据库中有"最后更新时间"字段，取消下面的注释并修改字段名
            # update_props["最后更新时间"] = {"date": {"start": datetime.datetime.now().isoformat()}}

            notion.pages.update(
                page_id=page_id,
                properties=update_props
            )
            
            log_message = f"价格: {final_price:.2f} | 汇率: {target_rate:.4f}"
            if pe_ratio is not None:
                log_message += f" | PE: {pe_ratio:.2f}"
            if pe_percentile is not None:
                log_message += f" | PE百分位: {pe_percentile:.2f}%"
            if pb_ratio is not None:
                log_message += f" | PB: {pb_ratio:.2f}"
            if roe is not None:
                log_message += f" | ROE: {roe:.2f}%"
            if peg is not None:
                log_message += f" | PEG: {peg:.2f}"

            if ticker_symbol.startswith('0') and len(ticker_symbol) == 6 and growth_rates and '1y' in growth_rates:
                log_message += f" | 年化: {growth_rates['1y']:.2f}%"

            print(f" ✅ 成功 ({log_message})")
            
        except Exception as e:
            error_msg = str(e)
            # 如果只是字段不存在，给出更友好的提示
            if "is not a property that exists" in error_msg:
                print(f" ❌ 失败: 字段不存在，请检查 Notion 数据库中的字段名")
            elif "无法获取" in error_msg or "currentTradingPeriod" in error_msg or "Not Found" in error_msg:
                print(f" ❌ 失败: 无法获取价格数据（可能是基金代码、已退市或数据源不支持）")
            else:
                print(f" ❌ 失败: {e}")
        
        # 礼貌性延时，防止 API 速率限制
        time.sleep(0.5)

    # === 卖出后涨跌幅更新 (交易流水表) ===
    print("\n📊 正在更新交易流水表中的卖出后涨跌幅...")
    try:
        # 交易流水表数据源 ID
        TRADE_LOG_DATA_SOURCE_ID = "2db4538c-fc22-8082-a3b1-000bf0590459"
        
        # 查询交易流水表
        trade_response = notion.data_sources.query(data_source_id=TRADE_LOG_DATA_SOURCE_ID)
        trade_pages = trade_response.get("results", [])
        
        # 重新查询股票投资组合表，获取最新的现价数据
        # (因为上面的循环已经更新了现价，但本地 pages 变量是旧数据)
        fresh_response = notion.data_sources.query(data_source_id=data_source_id)
        fresh_pages = fresh_response.get("results", [])
        
        # 构建股票 page_id -> 现价 的映射（使用最新数据）
        stock_prices = {}
        for page in fresh_pages:
            page_id = page["id"]
            props = page["properties"]
            current_price = None
            if "现价" in props and props["现价"].get("number") is not None:
                current_price = props["现价"]["number"]
            stock_prices[page_id] = current_price
        
        sell_count = 0
        update_count = 0
        
        for trade_page in trade_pages:
            trade_props = trade_page["properties"]
            
            # 检查动作类型是否为卖出
            action_val = None
            if "动作类型" in trade_props:
                action_prop = trade_props["动作类型"]
                if action_prop.get("type") == "select" and action_prop.get("select"):
                    action_val = action_prop["select"]["name"]
            
            if not action_val or "卖出" not in action_val:
                continue
            
            sell_count += 1
            
            # 获取交易日期作为标识
            trade_date = ""
            if "交易日期" in trade_props:
                t = trade_props["交易日期"]
                if t.get("title") and len(t["title"]) > 0:
                    trade_date = t["title"][0]["text"]["content"]
            
            # 获取成交单价
            sold_price = None
            if "成交单价" in trade_props:
                p = trade_props["成交单价"]
                if p.get("number") is not None:
                    sold_price = float(p["number"])
            
            if sold_price is None or sold_price <= 0:
                print(f"   ⚠️ {trade_date}: 成交单价无效，跳过")
                continue
            
            # 获取关联标的的现价
            current_price = None
            related_id = None
            if "关联标的" in trade_props:
                r = trade_props["关联标的"]
                if r.get("relation") and len(r["relation"]) > 0:
                    related_id = r["relation"][0]["id"]
                    current_price = stock_prices.get(related_id)
            
            if current_price is None:
                print(f"   ⚠️ {trade_date}: 无法获取关联股票现价，跳过")
                continue
            
            # 计算卖出后涨跌幅 (小数形式，如 0.05 表示 5%)
            sold_change_percent = (current_price - sold_price) / sold_price
            
            # 更新交易流水表
            notion.pages.update(
                page_id=trade_page["id"],
                properties={
                    "卖出后涨跌幅": {"number": round(sold_change_percent, 4)}
                }
            )
            update_count += 1
            print(f"   ✅ {trade_date}: 成交价 {sold_price:.2f} → 现价 {current_price:.2f} = {sold_change_percent:+.2%}")
            time.sleep(0.3)
        
        print(f"📈 卖出后涨跌幅更新完成: 共 {sell_count} 条卖出记录，更新 {update_count} 条")
    except Exception as e:
        print(f"⚠️ 卖出后涨跌幅更新失败: {e}")

    # === 买入后涨跌幅更新 (交易流水表) ===
    print("\n📊 正在更新交易流水表中的买入后涨跌幅...")
    try:
        # 交易流水表数据源 ID (已在上方定义)
        # TRADE_LOG_DATA_SOURCE_ID = "2db4538c-fc22-8082-a3b1-000bf0590459"
        
        # 如果 trade_pages 未定义（上面 try 块失败），重新查询
        if 'trade_pages' not in dir() or trade_pages is None:
            trade_response = notion.data_sources.query(data_source_id=TRADE_LOG_DATA_SOURCE_ID)
            trade_pages = trade_response.get("results", [])
        
        # 如果 stock_prices 未定义，重新构建
        if 'stock_prices' not in dir() or stock_prices is None:
            fresh_response = notion.data_sources.query(data_source_id=data_source_id)
            fresh_pages = fresh_response.get("results", [])
            stock_prices = {}
            for page in fresh_pages:
                page_id = page["id"]
                props = page["properties"]
                current_price = None
                if "现价" in props and props["现价"].get("number") is not None:
                    current_price = props["现价"]["number"]
                stock_prices[page_id] = current_price
        
        # 1. 构建 股票page_id -> 持仓数量 的映射（用于判断是否清仓）
        # 只有持仓数量为0（清仓）的股票才停止买入追踪
        stocks_fully_sold = set()  # 已清仓的股票
        for page in fresh_pages:
            page_id = page["id"]
            props = page["properties"]
            
            # 获取持仓数量（自动）字段
            position_qty = None
            if "持仓数量 (自动)" in props:
                rollup = props["持仓数量 (自动)"]
                if rollup.get("rollup") and rollup["rollup"].get("number") is not None:
                    position_qty = rollup["rollup"]["number"]
            
            # 如果持仓数量为0，标记为已清仓
            if position_qty is not None and position_qty == 0:
                stocks_fully_sold.add(page_id)
        
        print(f"   已识别 {len(stocks_fully_sold)} 只已清仓的股票，其买入记录将跳过")
        
        # 2. 遍历买入记录，更新买入后涨跌幅
        buy_count = 0
        buy_update_count = 0
        skip_count = 0
        
        for trade_page in trade_pages:
            trade_props = trade_page["properties"]
            
            # 检查动作类型是否为买入
            action_val = None
            if "动作类型" in trade_props:
                action_prop = trade_props["动作类型"]
                if action_prop.get("type") == "select" and action_prop.get("select"):
                    action_val = action_prop["select"]["name"]
            
            if not action_val or "买入" not in action_val:
                continue
            
            buy_count += 1
            
            # 获取交易日期作为标识
            trade_date = ""
            if "交易日期" in trade_props:
                t = trade_props["交易日期"]
                if t.get("title") and len(t["title"]) > 0:
                    trade_date = t["title"][0]["text"]["content"]
            
            # 获取关联标的 ID
            related_id = None
            if "关联标的" in trade_props:
                r = trade_props["关联标的"]
                if r.get("relation") and len(r["relation"]) > 0:
                    related_id = r["relation"][0]["id"]
            
            # 检查该股票是否已清仓 → 跳过
            if related_id and related_id in stocks_fully_sold:
                skip_count += 1
                continue
            
            # 获取成交单价
            buy_price = None
            if "成交单价" in trade_props:
                p = trade_props["成交单价"]
                if p.get("number") is not None:
                    buy_price = float(p["number"])
            
            if buy_price is None or buy_price <= 0:
                print(f"   ⚠️ {trade_date}: 成交单价无效，跳过")
                continue
            
            # 获取关联标的的现价
            current_price = None
            if related_id:
                current_price = stock_prices.get(related_id)
            
            if current_price is None:
                print(f"   ⚠️ {trade_date}: 无法获取关联股票现价，跳过")
                continue
            
            # 计算买入后涨跌幅 (小数形式，如 0.05 表示 5%)
            buy_change_percent = (current_price - buy_price) / buy_price
            
            # 更新交易流水表
            notion.pages.update(
                page_id=trade_page["id"],
                properties={
                    "买入后涨跌幅": {"number": round(buy_change_percent, 4)}
                }
            )
            buy_update_count += 1
            print(f"   ✅ {trade_date}: 成交价 {buy_price:.2f} → 现价 {current_price:.2f} = {buy_change_percent:+.2%}")
            time.sleep(0.3)
        
        print(f"📈 买入后涨跌幅更新完成: 共 {buy_count} 条买入记录，更新 {buy_update_count} 条，跳过 {skip_count} 条（已清仓）")
    except Exception as e:
        print(f"⚠️ 买入后涨跌幅更新失败: {e}")

    print("🎉 所有任务执行完毕。")

if __name__ == "__main__":
    # 1. 更新所有股票价格、PE、PB等数据
    update_portfolio()

    # 2. 同步平安证券股票组合到账户总览
    try:
        from scripts.update_pingan_portfolio import main as sync_pingan_portfolio
        print("\n" + "="*60)
        sync_pingan_portfolio()
    except ImportError as e:
        print(f"\n⚠️  跳过平安证券组合同步: 模块导入失败 ({e})")
    except Exception as e:
        print(f"\n⚠️  平安证券组合同步失败: {e}")
