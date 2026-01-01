import os
import time
import datetime
import pandas as pd

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

def get_exchange_rates():
    """
    获取实时汇率 (基准: CNY)
    返回: {'USD': 7.28, 'HKD': 0.93, 'CNY': 1.0}
    """
    print("💱 正在获取实时汇率...")
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
        
        # 方法3: 尝试获取历史数据（东方财富 - 推荐方法）
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
        
        # 方法5: 尝试使用基金净值接口
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

        # 方法6: 尝试作为开放式基金获取净值 (针对 00xxxx 等场外基金)
        try:
            df = ak.fund_open_fund_daily_em(symbol=ticker_symbol)
            if df is not None and not df.empty:
                # 字段通常是 '单位净值'
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

def update_portfolio():
    if not notion:
        raise ValueError("❌ 错误: 未找到 NOTION_TOKEN 或 DATABASE_ID 环境变量")

    # 1. 获取汇率
    rates = get_exchange_rates()
    
    # 2. 预加载 Akshare 行情数据 (加速查询)
    spot_cache = {}
    etf_cache = {}
    if AKSHARE_AVAILABLE:
        print("🚀 正在预加载 A股/ETF 行情数据 (加速查询)...")
        try:
            # 获取所有A股实时行情
            df_spot = ak.stock_zh_a_spot_em()
            if df_spot is not None and not df_spot.empty:
                spot_cache = {str(row['代码']): row for _, row in df_spot.iterrows()}
            print(f"   - 已缓存 {len(spot_cache)} 只A股行情")
        except Exception as e:
            print(f"   ⚠️ 预加载A股行情失败: {e}")

        try:
            # 获取所有ETF实时行情
            df_etf = ak.fund_etf_spot_em()
            if df_etf is not None and not df_etf.empty:
                etf_cache = {str(row['代码']): row for _, row in df_etf.iterrows()}
            print(f"   - 已缓存 {len(etf_cache)} 只ETF行情")
        except Exception as e:
            print(f"   ⚠️ 预加载ETF行情失败: {e}")

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
    CACHE_DIR = "./pe_cache"
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
            if current_price is None and calc_currency == "CNY":
                # 检查是否是基金代码（5开头ETF、1开头ETF/债券基金、10开头债券基金、0开头开放式基金）
                if ticker_symbol.isdigit() and (
                    ticker_symbol.startswith('5') or 
                    ticker_symbol.startswith('1') or 
                    ticker_symbol.startswith('10') or
                    ticker_symbol.startswith('0')
                ):
                    try:
                        # 传入缓存进行查询
                        akshare_price = get_price_from_akshare(ticker_symbol, spot_cache=spot_cache, etf_cache=etf_cache)
                        if akshare_price:
                            current_price = akshare_price
                            print(f" [使用akshare]", end="", flush=True)
                    except:
                        pass
            
            # 如果仍然无法获取价格，抛出异常
            if current_price is None or (isinstance(current_price, float) and current_price == 0):
                raise ValueError(f"无法获取 {ticker_symbol} 的价格数据，可能是基金代码或已退市")
            
            # 更新 Notion（使用中文列名）
            # 获取股票名称、PE和PE百分位
            stock_name = ""
            pe_ratio = None
            pe_percentile = None
            
            try:
                # -------PE持久缓存--------
                def get_pe_series_cached(symbol):
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
                
                # 高速本地查A股名称和现价 (使用已有的缓存)
                def get_name_price(symbol):
                    if symbol in spot_cache:
                        row = spot_cache[symbol]; return row.get('名称', ''), row.get('最新价', None)
                    if symbol in etf_cache:
                        row = etf_cache[symbol]; return row.get('名称', ''), row.get('最新价', None)
                    return '', None
                
                stock_name, current_price_a = get_name_price(ticker_symbol)
                
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
                        if ticker_symbol in spot_cache:
                            val = spot_cache[ticker_symbol].get('市盈率-动态')
                            if val is not None:
                                try:
                                    pe_ratio = float(val)
                                except:
                                    pass

                # 如果 PE 未获取到（非A股或A股获取失败），尝试使用 yfinance
                if pe_ratio is None:
                    # 美股/港股等使用yfinance
                    try:
                        if stock:
                            stock_info = stock.info
                            if not stock_name:
                                stock_name = stock_info.get("shortName", "") or stock_info.get("longName", "")
                            
                            import numpy as np
                            # 获取PE（优先使用trailingPE，如果没有则使用forwardPE）
                            pe_ratio = stock_info.get("trailingPE") or stock_info.get("forwardPE")
                            if pe_ratio is not None:
                                try:
                                    pe_ratio = float(pe_ratio)
                                except (ValueError, TypeError):
                                    pe_ratio = None
                            # 获取PE百分位（基于历史5年1个月的数据）
                            pe_percentile = None
                            try:
                                hist = stock.history(period="5y", interval="1mo")
                                if hist is not None and not hist.empty and pe_ratio is not None and pe_ratio > 0:
                                    # 使用 info 的 trailingEps 作为近似，即所有历史点都用这个最新eps，近似即可
                                    trailing_eps = stock_info.get("trailingEps")
                                    if trailing_eps is not None and trailing_eps != 0:
                                        hist_pe_ratios = hist['Close'] / float(trailing_eps)
                                        hist_pe_ratios = hist_pe_ratios[hist_pe_ratios > 0]
                                        if not hist_pe_ratios.empty:
                                            pe_percentile = float(np.sum(hist_pe_ratios < pe_ratio)) / len(hist_pe_ratios) * 100
                            except Exception as e:
                                pass
                            # yfinance 无法直接获取中国A股和无季报历史EPS，港美股可用该方法

                    except:
                        pass
            except Exception as e:
                pass

            # 优先使用加速缓存获取的A股现价
            final_price = current_price_a if (calc_currency == "CNY" and current_price_a is not None) else current_price
            update_props = {
                "现价": {"number": round(final_price, 2) if final_price is not None else None},
                "汇率": {"number": round(target_rate, 4)},
                "货币": {"select": {"name": current_currency_name}}
            }
            if stock_name:
                update_props["股票名称"] = {"rich_text": [{"text": {"content": stock_name}}]}
            if pe_ratio is not None:
                update_props["PE"] = {"number": round(pe_ratio, 2)}
            if pe_percentile is not None:
                update_props["PE百分位"] = {"number": round(pe_percentile, 2)}
            
            # 如果 Notion 数据库中有"最后更新时间"字段，取消下面的注释并修改字段名
            # update_props["最后更新时间"] = {"date": {"start": datetime.datetime.now().isoformat()}}
            
            notion.pages.update(
                page_id=page_id,
                properties=update_props
            )
            print(f" ✅ 成功 (价格: {current_price:.2f} | 汇率: {target_rate:.4f})")
            
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

    print("🎉 所有任务执行完毕。")

if __name__ == "__main__":
    update_portfolio()
