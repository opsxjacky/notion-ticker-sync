#!/usr/bin/env python3
"""
测试脚本：测试场外基金价格获取
用于调试 003847 和 003864 两个基金代码
"""
import sys
import os

# 确保能导入主模块
sys.path.insert(0, os.path.dirname(__file__))

try:
    import akshare as ak
    AKSHARE_AVAILABLE = True
    print("✓ akshare 已安装")
except ImportError:
    AKSHARE_AVAILABLE = False
    print("✗ akshare 未安装，请运行: pip install akshare")
    sys.exit(1)

try:
    import yfinance as yf
    YF_AVAILABLE = True
    print("✓ yfinance 已安装")
except ImportError:
    yf = None
    YF_AVAILABLE = False
    print("✗ yfinance 未安装（可选）")

print("\n" + "="*60)
print("测试场外基金价格获取")
print("="*60)

# 测试基金代码列表
test_funds = ['003847', '003864']

for fund_code in test_funds:
    print(f"\n📊 测试基金代码: {fund_code}")
    print("-" * 60)

    # 方法1: fund_open_fund_daily_em
    print("\n[方法1] ak.fund_open_fund_daily_em()")
    try:
        df = ak.fund_open_fund_daily_em(symbol=fund_code)
        if df is not None and not df.empty:
            print(f"  ✓ 成功获取数据，共 {len(df)} 条记录")
            print(f"  列名: {df.columns.tolist()}")
            if '单位净值' in df.columns:
                latest_nav = df['单位净值'].iloc[-1]
                print(f"  最新净值: {latest_nav}")
            else:
                print("  ✗ 未找到'单位净值'字段")
                print(f"  数据样例:\n{df.tail(2)}")
        else:
            print("  ✗ 返回数据为空")
    except Exception as e:
        print(f"  ✗ 失败: {type(e).__name__}: {e}")

    # 方法2: fund_open_fund_info_em
    print("\n[方法2] ak.fund_open_fund_info_em(indicator='单位净值走势')")
    try:
        df = ak.fund_open_fund_info_em(fund=fund_code, indicator="单位净值走势")
        if df is not None and not df.empty:
            print(f"  ✓ 成功获取数据，共 {len(df)} 条记录")
            print(f"  列名: {df.columns.tolist()}")
            for field in ['y', 'nav', '单位净值']:
                if field in df.columns:
                    latest_value = df[field].iloc[-1]
                    print(f"  最新{field}: {latest_value}")
                    break
            else:
                print("  ✗ 未找到净值字段")
                print(f"  数据样例:\n{df.tail(2)}")
        else:
            print("  ✗ 返回数据为空")
    except Exception as e:
        print(f"  ✗ 失败: {type(e).__name__}: {e}")

    # 方法3: fund_name_em (仅获取基金名称)
    print("\n[方法3] ak.fund_name_em() - 查找基金名称")
    try:
        df = ak.fund_name_em()
        if df is not None and not df.empty:
            match = df[df['基金代码'] == fund_code]
            if not match.empty:
                fund_name = match.iloc[0]['基金简称']
                print(f"  ✓ 找到基金: {fund_name}")
            else:
                print(f"  ✗ 在基金列表中未找到 {fund_code}")
        else:
            print("  ✗ fund_name_em 返回空数据")
    except Exception as e:
        print(f"  ✗ 失败: {type(e).__name__}: {e}")

    # 方法4: yfinance (通常不支持中国场外基金)
    if YF_AVAILABLE:
        print("\n[方法4] yfinance (不太可能支持场外基金)")
        try:
            ticker = yf.Ticker(fund_code)
            price = ticker.fast_info.last_price
            if price and price > 0:
                print(f"  ✓ yfinance 价格: {price}")
            else:
                print("  ✗ yfinance 无法获取价格")
        except Exception as e:
            print(f"  ✗ yfinance 失败: {type(e).__name__}: {e}")

print("\n" + "="*60)
print("测试完成")
print("="*60)
