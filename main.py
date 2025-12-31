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

def update_portfolio():
    # 1. 查询 Notion 数据库
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
            ticker_list = props["股票代码"]["title"]
            if not ticker_list: continue # 跳过空行
            ticker_symbol = ticker_list[0]["text"]["content"]
        except KeyError:
            print("⚠️ 跳过无法识别的行 (缺少股票代码)")
            continue

        # --- 核心逻辑：获取并更新股票价格 ---
        try:
            print(f"🔄 处理: {ticker_symbol}...", end="", flush=True)
            
            # 处理不同类型的代码
            yf_ticker = ticker_symbol.upper()  # 转换为大写
            
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
            
            # 更新 Notion
            update_props = {
                "现价": {"number": round(current_price, 2)}
            }
            
            # 如果 Notion 数据库中有"最后更新时间"字段，取消下面的注释并修改字段名
            # update_props["最后更新时间"] = {"date": {"start": datetime.datetime.now().isoformat()}}
            
            notion.pages.update(
                page_id=page_id,
                properties=update_props
            )
            print(f" ✅ 成功 (价格: {current_price:.2f})")
            
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