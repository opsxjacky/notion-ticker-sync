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
            
            # 抓取股价
            stock = yf.Ticker(ticker_symbol)
            current_price = stock.fast_info.last_price
            
            # 更新 Notion
            notion.pages.update(
                page_id=page_id,
                properties={
                    "Price": {"number": round(current_price, 2)},
                    "Last Updated": {"date": {"start": datetime.datetime.now().isoformat()}}
                }
            )
            print(f" ✅ 成功 (价格: {current_price:.2f})")
            
        except Exception as e:
            print(f" ❌ 失败: {e}")
        
        # 礼貌性延时，防止 API 速率限制
        time.sleep(0.5)

    print("🎉 所有任务执行完毕。")

if __name__ == "__main__":
    update_portfolio()