# Notion Ticker Sync 设计文档

## 项目概述

自动同步股票/基金/ETF行情数据到 Notion 数据库的工具。支持 A股、港股、美股、加密货币和场内/场外基金。

## 目录结构

```
notion-ticker-sync/
├── main.py                     # 主程序：更新投资组合数据
├── requirements.txt            # Python 依赖
├── design.md                   # 设计文档（本文件）
├── README.md                   # 项目说明
├── ETF_VALUATION_GUIDE.md      # ETF 估值指南
├── .github/
│   └── workflows/
│       └── sync.yml            # GitHub Actions 工作流程
├── scripts/                    # 辅助脚本
│   ├── __init__.py
│   ├── update_bond_etf_yield.py    # 更新债券ETF到期收益率
│   └── update_pingan_portfolio.py  # 同步平安证券组合到账户总览
└── tests/                      # 单元测试
    ├── test_main.py
    ├── test_akshare_fund.py
    ├── test_fund_price.py
    └── test_update_bond_etf_yield.py
```

## 环境配置

### 环境变量

| 变量名 | 说明 |
|--------|------|
| `NOTION_TOKEN` | Notion API Token |
| `DATABASE_ID` | Notion 数据库 ID |
| `SKIP_VENV_CHECK` | 设为 `1` 跳过虚拟环境检查（CI 环境用） |

### 依赖库

- `notion-client`: Notion API 客户端
- `yfinance`: 美股/港股/加密货币行情
- `akshare`: A股/ETF/港股/基金行情
- `pandas`: 数据处理

---

## 核心功能模块

### 1. main.py - 主程序

#### 1.1 数据源

| 数据源 | 支持的标的 | 说明 |
|--------|-----------|------|
| akshare | A股、ETF、港股、场外基金 | 优先使用，数据更准确 |
| yfinance | 美股、港股、加密货币 | 备用数据源 |

#### 1.2 更新的 Notion 字段

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `股票代码` | title | 股票/基金代码（必填） |
| `股票名称` | rich_text | 股票名称（自动获取） |
| `货币` | select | 货币类型：CNY/HKD/USD |
| `PE` | number | 市盈率 |
| `PE百分位` | number | PE 历史百分位 |
| `PB` | number | 市净率 |
| `ROE` | number | 净资产收益率 (%) |
| `PEG` | number | 市盈增长比率 |

#### 1.3 代码自动识别规则

| 代码格式 | 市场 | 处理方式 |
|----------|------|----------|
| `60xxxx` | A股上海 | 添加 `.SS` 后缀 |
| `00xxxx` / `30xxxx` | A股深圳 | 添加 `.SZ` 后缀 |
| `5xxxxx` / `1xxxxx` | ETF | 使用 akshare 获取 |
| `0xxxxx` (6位) | 场外基金 | 使用 akshare fund_name_em |
| `BTC` 等 | 加密货币 | 添加 `-USD` 后缀 |
| 其他 | 美股 | 直接使用 yfinance |

#### 1.4 ETF 指数映射

ETF 会自动映射到对应指数获取 PE/PB：

```python
ETF_INDEX_MAPPING = {
    '510300': '000300',  # 沪深300ETF → 沪深300指数
    '510500': '000905',  # 中证500ETF → 中证500指数
    '510050': '000016',  # 上证50ETF → 上证50指数
    '588000': '000688',  # 科创50ETF → 科创50指数
    '159915': '399006',  # 创业板ETF → 创业板指
    '510880': '000922',  # 红利ETF → 中证红利指数
    # ... 更多映射
}
```

#### 1.5 港股 ETF 特殊处理

以下港股 ETF 使用恒生指数 PE/PB：

```python
HK_ETF_INDEX_MAPPING = {
    '159920': 'HSI',   # A股恒生ETF → 恒生指数
    '513660': 'HSI',   # 恒生ETF → 恒生指数
    '513380': 'HSTECH', # 恒生科技ETF → 恒生科技指数
    # ...
}
```

**PB 数据获取说明**：由于恒生指数 PB 数据难以通过免费 API 获取，使用 2800.HK（盈富基金）的 `priceToBook` 作为恒生指数 PB 的代理值。

#### 1.6 汇率获取

使用 akshare 实时获取汇率：
- USD/CNY
- HKD/CNY

---

### 2. scripts/update_bond_etf_yield.py - 债券ETF收益率

#### 功能

获取中国国债到期收益率，写入债券 ETF 的 `Yield` 字段。

#### 支持的债券 ETF

| ETF代码 | 国债期限 | 说明 |
|---------|----------|------|
| `511520` | 10年期 | 10年期国债ETF |
| `511260` | 10年期 | 10年期国债ETF |
| `511010` | 5年期 | 5年期国债ETF |
| `511090` | 30年期 | 30年期国债ETF |

#### 数据源

使用 akshare `bond_zh_us_rate()` API 获取中美国债收益率。

---

### 3. scripts/update_pingan_portfolio.py - 平安证券组合同步

#### 功能

将账户为"平安证券"的所有股票记录，关联到账户总览页面的"股票投资组合"字段。

#### 流程

1. 查询数据库中账户="平安证券"的所有记录
2. 查找有"平安证券总仓"字段的账户总览页面
3. 更新账户总览页面的"股票投资组合"字段（relation 类型）

---

## GitHub Actions 自动化

### 工作流程 (.github/workflows/sync.yml)

#### 触发条件

- **定时任务**: UTC 21:00 (北京时间 05:00)，周一至周五
- **手动触发**: workflow_dispatch

#### 执行步骤

1. 检出代码
2. 设置 Python 3.11
3. 安装依赖 (`requirements.txt`)
4. 运行单元测试
5. 执行 `main.py`（注入 Secrets）
6. 执行 `scripts/update_bond_etf_yield.py` 更新债券ETF到期收益率

---

## 缓存机制

### 行情数据缓存

目录: `akshare_cache/`

| 缓存文件 | 内容 | 有效期 |
|----------|------|--------|
| `spot_cache.pkl` | A股实时行情 | 当天 |
| `etf_cache.pkl` | ETF实时行情 | 当天 |
| `hk_cache.pkl` | 港股实时行情 | 当天 |
| `open_fund_cache.pkl` | 开放式基金名称 | 当天 |

### PE 历史数据缓存

目录: `pe_cache/`

用于计算 PE 百分位的历史数据缓存。

---

## Notion 数据库要求

### 必需字段

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `股票代码` | title | 股票/基金代码 |

### 可选字段

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `股票名称` | rich_text | 自动填充 |
| `货币` | select | CNY/HKD/USD |
| `PE` | number | 市盈率 |
| `PE百分位` | number | PE历史百分位 |
| `PB` | number | 市净率 |
| `ROE` | number | 净资产收益率 |
| `PEG` | number | 市盈增长比率 |
| `Yield` | number | 债券ETF到期收益率 |
| `账户` | select | 账户名称（用于组合同步） |
| `账户总览` | relation | 关联到账户总览页面 |
| `股票投资组合` | relation | 股票组合（账户总览用） |

---

## 扩展指南

### 添加新的 ETF 指数映射

在 `main.py` 的 `ETF_INDEX_MAPPING` 字典中添加：

```python
ETF_INDEX_MAPPING = {
    'ETF代码': '指数代码',
    # ...
}
```

### 添加新的债券 ETF

在 `scripts/update_bond_etf_yield.py` 中：

```python
TICKERS_10Y = ["511520", "511260"]  # 10年期
TICKERS_5Y = ["511010"]             # 5年期
TICKERS_30Y = ["511090"]            # 30年期

# 固定收益率品种
FIXED_YIELD_TICKERS = {
    "102277": 2.33,  # 特别国债
}
```

### 添加新的加密货币

在 `main.py` 的 `CRYPTO_SYMBOLS` 集合中添加。

---

## 常见问题

### Q: 为什么某些股票价格获取失败？

可能原因：
1. 股票已退市
2. 代码格式不正确
3. 数据源暂时不可用

### Q: PE百分位如何计算？

使用近5年的 PE 历史数据，计算当前 PE 在历史分布中的百分位。

### Q: 如何添加新账户的组合同步？

参考 `scripts/update_pingan_portfolio.py` 实现类似脚本。