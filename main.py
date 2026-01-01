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
    elif ticker.isdigit() and len(ticker) == 6:
        return "CNY"  # 纯数字6位代码默认为A股/基金
    else:
        return "USD"  # 美股/加密货币/默认

def get_price_from_akshare(ticker_symbol, spot_cache=None, etf_cache=None):
    """
    使用 akshare 获取中国基金价格/净值
    修复：支持场外基金（00开头等），不再限制前缀。
    """
    if not AKSHARE_AVAILABLE:
        return None
    
    # 1. 优先查缓存 (ETF/A股 实时行情)
    # 这部分逻辑保留，因为 update_portfolio 传入了缓存，利用起来效率最高
    if etf_cache is not None and ticker_symbol in etf_cache:
        row = etf_cache[ticker_symbol]
        for field in ['最新价', '收盘', '现价', 'close', 'current']:
            val = row.get(field)
            if val is not None and val != '-' and val != '':
                try:
                    return float(val)
                except:
                    continue

    if spot_cache is not None and ticker_symbol in spot_cache:
        row = spot_cache[ticker_symbol]
        for field in ['最新价', '收盘', '现价', 'current', 'close']:
            val = row.get(field)
            if val is not None and val != '-' and val != '':
                try:
                    return float(val)
                except:
                    continue

    # 2. 尝试 ETF/LOF 实时行情 (针对场内交易基金)
    # 通常以 51, 50, 15, 16, 10 开头
    if ticker_symbol.startswith(('51', '50', '15', '16', '10')):
        try:
            # 如果缓存没命中，尝试请求 ETF 实时 (虽然 update_portfolio 预加载了，但以防万一)
            if etf_cache is None:
                df = ak.fund_etf_spot_em()
                if df is not None and not df.empty:
                    match = df[df['代码'] == ticker_symbol]
                    if not match.empty:
                        price = match.iloc[0].get('最新价')
                        if price and str(price) != '-':
                            return float(price)
        except:
            pass
            
        try:
            # 尝试 A股 实时行情 (有些 LOF/分级基金在这里)
            if spot_cache is None:
                df = ak.stock_zh_a_spot_em()
                if df is not None and not df.empty:
                    match = df[df['代码'] == ticker_symbol]
                    if not match.empty:
                        price = match.iloc[0].get('最新价')
                        if price and str(price) != '-':
                            return float(price)
        except:
            pass

    # 3. 尝试作为【场外基金/开放式基金】获取净值
    # 适用于 00 开头，或者上面 ETF 没查到的情况
    try:
        # 接口 A: 单个基金的历史净值详情 (最准确)
        # indicator="单位净值走势" 获取最新的一条
        # print(f" [查询净值: {ticker_symbol}]", end="", flush=True)
        df = ak.fund_open_fund_info_em(fund=ticker_symbol, indicator="单位净值走势")
        if df is not None and not df.empty:
            # 数据通常按日期排序，取最后一行
            # 列名通常是 '净值日期', '单位净值', '日增长率'
            for field in ['单位净值', 'nav', 'y']:
                if field in df.columns:
                    nav = df[field].iloc[-1]
                    if nav is not None:
                        try:
                            return float(nav)
                        except:
                            continue
    except Exception as e:
        pass

    try:
        # 接口 B: 开放式基金实时估值 (备选)
        # 注意：ak.fund_open_fund_daily_em() 下载全量数据，较慢，仅在必要时尝试
        # 如果是 00 开头且上面失败了，可能需要这个
        # 但为了防止每次都下载全量，这里我们假设 info_em 应该能覆盖大多数情况
        # 如果确实需要，可以取消注释，但要注意性能
        # df = ak.fund_open_fund_daily_em()
        # if df is not None and not df.empty:
        #     match = df[df['基金代码'] == ticker_symbol]
        #     if not match.empty:
        #         nav = match.iloc[0].get('单位净值')
        #         if nav: return float(nav)
        pass
    except:
        pass

    try:
        # 接口 C: 货币基金
        # ak.fund_money_fund_daily_em()
        # 货币基金通常净值为 1.0
        # 简单的判断：如果是 00 开头且前面都没查到，可能是货币基金？
        # 或者直接返回 None，由用户手动设置
        pass
    except:
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
    hk_cache = {}
    
    if AKSHARE_AVAILABLE:
        print("🚀 正在预加载 A股/ETF/港股 行情数据 (加速查询)...")
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
            
        try:
            # 获取所有港股实时行情
            df_hk = ak.stock_hk_spot_em()
            if df_hk is not None and not df_hk.empty:
                hk_cache = {str(row['代码']): row for _, row in df_hk.iterrows()}
            print(f"   - 已缓存 {len(hk_cache)} 只港股行情")
        except Exception as e:
            print(f"   ⚠️ 预加载港股行情失败: {e}")

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
            # 注意：yfinance 有时会返回 0.0 (例如暂停交易或数据缺失)，这也应该视为失败
            if (current_price is None or (isinstance(current_price, (int, float)) and current_price == 0)) and calc_currency == "CNY":
                # 检查是否是基金代码（只要是6位数字，都尝试去查，包括00开头的场外基金）
                if ticker_symbol.isdigit() and len(ticker_symbol) == 6:
                    try:
                        # 传入缓存进行查询
                        akshare_price = get_price_from_akshare(ticker_symbol, spot_cache=spot_cache, etf_cache=etf_cache)
                        if akshare_price:
                            current_price = akshare_price
                            print(f" [使用akshare]", end="", flush=True)
                    except:
                        pass
            
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
                
                # 高速本地查A股/港股名称和现价 (使用已有的缓存)
                def get_name_price(symbol, currency):
                    # A股
                    if currency == "CNY":
                        if symbol in spot_cache:
                            row = spot_cache[symbol]; return row.get('名称', ''), row.get('最新价', None)
                        if symbol in etf_cache:
                            row = etf_cache[symbol]; return row.get('名称', ''), row.get('最新价', None)
                    # 港股
                    if currency == "HKD":
                        hk_code = symbol.replace(".HK", "").zfill(5)
                        if hk_code in hk_cache:
                            row = hk_cache[hk_code]; return row.get('名称', ''), row.get('最新价', None)
                    return '', None
                
                stock_name, current_price_a = get_name_price(ticker_symbol, calc_currency)
                
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
                                except:
                                    pass
                        # 检查 ETF etf_cache (虽然通常没有，但以防万一)
                        if pe_ratio is None and ticker_symbol in etf_cache:
                            val = etf_cache[ticker_symbol].get('市盈率-动态') or etf_cache[ticker_symbol].get('市盈率')
                            if val is not None:
                                try:
                                    pe_ratio = float(val)
                                except:
                                    pass

                # 尝试获取港股 PE (从 Akshare 缓存)
                if calc_currency == 'HKD' and pe_ratio is None:
                    hk_code = ticker_symbol.replace(".HK", "").zfill(5)
                    if hk_code in hk_cache:
                        val = hk_cache[hk_code].get('市盈率-动态') or hk_cache[hk_code].get('市盈率')
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
