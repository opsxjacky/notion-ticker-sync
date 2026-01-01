import os
import time
import datetime
import yfinance as yf
from notion_client import Client

# --- 环境变量配置 (CI/CD 注入) ---
# 本地测试时，可以在终端 export 或者直接把字符串填在这里测试(测试完记得删掉)
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("DATABASE_ID")

if not NOTION_TOKEN or not DATABASE_ID:
    raise ValueError("❌ 错误: 未找到 NOTION_TOKEN 或 DATABASE_ID 环境变量")

# 初始化 Notion
notion = Client(auth=NOTION_TOKEN)

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

def update_portfolio():
    # 1. 获取汇率
    rates = get_exchange_rates()
    
    # 2. 查询 Notion 数据库
    print(f"📥 正在查询 Notion 数据库: {DATABASE_ID} ...")
    try:
        response = notion.databases.query(database_id=DATABASE_ID)
        pages = response.get("results", [])
    except Exception as e:
        print(f"❌ Notion 连接失败: {e}")
        return

    print(f"🔍 找到 {len(pages)} 条持仓记录，开始更新...")

    # 2. 遍历更新股票价格
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
            stock = yf.Ticker(yf_ticker)
            current_price = stock.fast_info.last_price
            
            # 更新 Notion（使用中文列名）
            update_props = {
                "现价": {"number": round(current_price, 2)},
                "汇率": {"number": round(target_rate, 4)},
                "货币": {"select": {"name": current_currency_name}}
            }
            
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
            else:
                print(f" ❌ 失败: {e}")
        
        # 礼貌性延时，防止 API 速率限制
        time.sleep(0.5)

    print("🎉 所有任务执行完毕。")

if __name__ == "__main__":
    update_portfolio()