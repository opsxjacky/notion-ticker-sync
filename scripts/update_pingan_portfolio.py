import os
import sys
from notion_client import Client

# 环境变量配置
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("DATABASE_ID")

# 初始化 Notion 客户端
if not NOTION_TOKEN or not DATABASE_ID:
    print("❌ 错误: 未找到环境变量")
    sys.exit(1)

notion = Client(auth=NOTION_TOKEN, notion_version="2025-09-03")

def get_pingan_stock_pages():
    """从数据库查询账户=平安证券的所有记录（返回page ID和股票代码）"""
    print("📥 正在查询平安证券的股票...")

    try:
        database = notion.databases.retrieve(database_id=DATABASE_ID)

        if 'data_sources' in database and database['data_sources']:
            data_source_id = database['data_sources'][0]['id']
            response = notion.data_sources.query(data_source_id=data_source_id)
            pages = response.get("results", [])
        else:
            raise Exception("不支持单数据源数据库")

        print(f"🔍 找到 {len(pages)} 条记录")

        stock_pages = []  # 存储 (page_id, stock_code) 元组
        for page in pages:
            page_id = page["id"]
            props = page["properties"]

            # 获取账户字段
            account_prop = props.get("账户")
            if account_prop:
                account_name = ""
                if account_prop.get("select"):
                    account_name = account_prop["select"]["name"]
                elif account_prop.get("rich_text") and len(account_prop["rich_text"]) > 0:
                    account_name = account_prop["rich_text"][0]["text"]["content"]

                # 判断是否为平安证券
                if "平安证券" in account_name or "平安" in account_name:
                    # 获取股票代码
                    ticker_obj = props.get("股票代码")
                    if ticker_obj and ticker_obj.get("title"):
                        ticker_list = ticker_obj["title"]
                        if ticker_list:
                            stock_code = ticker_list[0]["text"]["content"]
                            stock_pages.append((page_id, stock_code))
                            print(f"   ✓ {stock_code} (ID: {page_id[:8]}...)")

        print(f"\n📊 共找到 {len(stock_pages)} 条平安证券记录")
        return stock_pages

    except Exception as e:
        print(f"❌ 查询失败: {e}")
        return []

def find_overview_page_with_pingan():
    """找到包含'平安证券总仓'字段的账户总览页面"""
    print("\n🔍 正在查找平安证券总仓页面...")

    try:
        database = notion.databases.retrieve(database_id=DATABASE_ID)

        if 'data_sources' in database and database['data_sources']:
            data_source_id = database['data_sources'][0]['id']
            response = notion.data_sources.query(data_source_id=data_source_id)
            pages = response.get("results", [])
        else:
            raise Exception("不支持单数据源数据库")

        # 遍历查找有账户总览关联的记录
        for page in pages:
            props = page["properties"]
            overview_prop = props.get("账户总览")

            if overview_prop and overview_prop.get("relation") and len(overview_prop["relation"]) > 0:
                # 获取关联的页面ID
                related_page_id = overview_prop["relation"][0]["id"]

                try:
                    # 获取关联页面的详细信息
                    related_page = notion.pages.retrieve(page_id=related_page_id)

                    # 检查是否有"平安证券总仓"字段
                    if "平安证券总仓" in related_page["properties"]:
                        print(f"✓ 找到平安证券总仓页面: {related_page_id[:8]}...")

                        # 检查是否有"股票投资组合"字段
                        if "股票投资组合" in related_page["properties"]:
                            print("✓ 确认该页面有'股票投资组合'字段")
                            return related_page_id
                except:
                    continue

        print("❌ 未找到平安证券总仓页面")
        return None

    except Exception as e:
        print(f"❌ 查找失败: {e}")
        return None

def update_portfolio_field(page_id, stock_pages):
    """更新页面的股票投资组合字段（relation类型）"""
    print(f"\n📝 正在更新股票投资组合字段...")

    try:
        # 将page ID列表转换为relation格式
        relation_items = [{"id": pid} for pid, _ in stock_pages]

        # 更新字段（relation类型）
        update_props = {
            "股票投资组合": {
                "relation": relation_items
            }
        }

        notion.pages.update(
            page_id=page_id,
            properties=update_props
        )

        stock_codes = [code for _, code in stock_pages]
        print(f"✅ 成功更新! 写入了 {len(stock_pages)} 条记录")
        print(f"   股票代码: {', '.join(stock_codes)}")
        return True

    except Exception as e:
        print(f"❌ 更新失败: {e}")
        return False

def main():
    print("=" * 60)
    print("同步平安证券股票代码到账户总览")
    print("=" * 60)

    # 1. 获取平安证券的股票记录（page ID + 股票代码）
    stock_pages = get_pingan_stock_pages()
    if not stock_pages:
        print("\n⚠️  未找到平安证券的股票记录")
        return

    # 2. 找到平安证券总仓的账户总览页面
    overview_page_id = find_overview_page_with_pingan()
    if not overview_page_id:
        print("\n⚠️  未找到平安证券总仓页面")
        return

    # 3. 更新股票投资组合字段（使用relation）
    success = update_portfolio_field(overview_page_id, stock_pages)

    if success:
        print("\n🎉 任务完成!")
    else:
        print("\n❌ 任务失败")

if __name__ == "__main__":
    main()
