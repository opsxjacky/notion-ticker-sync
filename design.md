# Notion Ticker Sync 设计文档

## 项目概述

自动同步股票/基金/ETF行情数据到 Notion 数据库的工具。支持 A股、港股、美股、加密货币和场内/场外基金。

主要功能：
- **实时行情同步**：获取股票/基金/ETF的最新价格
- **估值指标**：PE、PB、ROE、PEG 等财务指标
- **历史百分位**：计算 PE 的历史百分位（基于近10年数据）
- **汇率转换**：自动获取 USD/CNY、HKD/CNY 实时汇率
- **卖出后跟踪**：自动计算已卖出股票的后续涨跌幅
- **组合管理**：同步特定账户的持仓到账户总览
- **债券ETF收益率**：自动更新国债ETF的到期收益率

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
├── akshare_cache/              # Akshare 行情数据缓存目录（运行时生成）
├── pe_cache/                   # PE 历史数据缓存目录（运行时生成）
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
| `现价` | number | 当前价格 |
| `汇率` | number | 当前汇率（基于 CNY） |
| `PE` | number | 市盈率（TTM） |
| `PE百分位` | number | PE 历史百分位（基于近10年数据） |
| `PB` | number | 市净率 |
| `ROE` | number | 净资产收益率（%） |
| `PEG` | number | 市盈增长比率 |

#### 1.3 卖出后跟踪功能

系统会自动更新「交易流水表」中卖出记录的「卖出后涨跌幅」字段。

**数据库结构**：

本项目使用 Notion 多数据源数据库，包含以下三张表：

| 数据源 | ID | 说明 |
|--------|-----|------|
| 股票投资组合 | `2da4538c-fc22-8055-9417-000b9595ad21` | 持仓记录，包含现价等数据 |
| 交易流水表 | `2db4538c-fc22-8082-a3b1-000bf0590459` | 交易记录，包含卖出后涨跌幅 |
| 账户总览 | `2dc4538c-fc22-80a4-bf4c-000bbc82b1aa` | 账户汇总信息 |

**交易流水表字段**：

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `交易日期` | title | 交易日期 |
| `动作类型` | select | 买入/卖出 |
| `成交单价` | number | 交易时的成交价格 |
| `变动股数` | number | 交易数量 |
| `关联标的` | relation | 关联到股票投资组合 |
| `卖出后涨跌幅` | number | 卖出后价格涨跌幅（小数形式，自动计算） |

**计算公式**：
```
卖出后涨跌幅 = (当前价格 - 成交单价) / 成交单价
```

> 注：存储为小数形式，如 `0.05` 表示 5%。在 Notion 中可设置字段格式为百分比显示。

**使用场景**：
- 跟踪已卖出股票的后续表现
- 评估卖出决策是否正确
- 正值表示卖出后股价上涨（卖早了），负值表示卖出后股价下跌（卖对了）

**工作流程**：
1. 在交易流水表中记录卖出交易，设置「动作类型」为"卖出"
2. 填写「成交单价」为卖出时的实际价格
3. 通过「关联标的」关联到对应的股票
4. 运行脚本后，系统自动获取关联股票的现价并计算「卖出后涨跌幅」

#### 1.3.1 买入后跟踪功能

系统会自动更新「交易流水表」中买入记录的「买入后涨跌幅」字段。

**停止追踪条件**：当某只股票在「股票投资组合」中的「持仓数量（自动）」为 0 时（即已清仓），该股票的所有「买入」记录将不再更新「买入后涨跌幅」字段，由卖出追踪逻辑接管。

> 注：部分卖出（未清仓）时，买入记录仍会继续追踪涨跌幅。

**计算公式**：
```
买入后涨跌幅 = (当前价格 - 成交单价) / 成交单价
```

> 注：存储为小数形式，如 `0.05` 表示 5%。正值表示买入后股价上涨（买对了），负值表示买入后股价下跌（被套了）。

**交易流水表新增字段**：

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `买入后涨跌幅` | number | 买入后价格涨跌幅（小数形式，自动计算） |

**工作流程**：
1. 在交易流水表中记录买入交易，设置「动作类型」为"买入"
2. 填写「成交单价」为买入时的实际价格
3. 通过「关联标的」关联到对应的股票
4. 运行脚本后，系统检查该股票的持仓数量：
   - 如果持仓数量 > 0（未清仓）→ 自动计算并更新「买入后涨跌幅」
   - 如果持仓数量 = 0（已清仓）→ 跳过买入追踪（由卖出追踪接管）

#### 1.4 代码自动识别规则

| 代码格式 | 市场 | 处理方式 |
|----------|------|----------|
| `60xxxx` | A股上海 | 添加 `.SS` 后缀 |
| `00xxxx` / `30xxxx` | A股深圳 | 添加 `.SZ` 后缀 |
| `5xxxxx` / `1xxxxx` | ETF | 使用 akshare 获取 |
| `0xxxxx` (6位) | 场外基金 | 使用 akshare fund_name_em |
| `BTC` 等 | 加密货币 | 添加 `-USD` 后缀 |
| 其他 | 美股 | 直接使用 yfinance |

#### 1.5 ETF 指数映射

ETF 会自动映射到对应指数获取 PE/PB：

```python
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

    # 创业板系列 - 使用中证1000作为PE代理
    # ⚠️ 注意：创业板指(399006)是深交所指数，中证指数API不提供其PE数据
    # 中证1000与创业板指权重结构差异较大，PE数据仅供参考
    '159915': '932000',  # 创业板ETF → 中证1000指数（PE代理）
    '159949': '932000',  # 创业板ETF → 中证1000指数（PE代理）

    # 红利系列
    '510880': '000922',  # 红利ETF → 中证红利指数

    # 券商系列
    '512000': '399975',  # 券商ETF → 证券公司指数
    '512880': '399975',  # 券商ETF → 证券公司指数

    # 银行系列
    '512800': '399986',  # 银行ETF → 中证银行指数
}
```

#### 1.5.1 QDII ETF 映射（中国QDII ETF → 美股ETF）

用于获取纳指、标普500等美股指数的 PE 数据：

```python
QDII_ETF_MAPPING = {
    '159941': 'QQQ',    # 纳指ETF → QQQ (Invesco QQQ Trust)
    '513500': 'SPY',    # 标普500ETF → SPY (SPDR S&P 500 ETF)
    '513100': 'QQQ',    # 纳指100ETF → QQQ
    '513050': 'SPY',    # 标普500ETF(另一只) → SPY
}
```

#### 1.6 港股 ETF 特殊处理

以下港股 ETF 使用恒生指数 PE/PB：

```python
HK_ETF_INDEX_MAPPING = {
    '2800.HK': 'HSI',      # 盈富基金 → 恒生指数
    '02800.HK': 'HSI',     # 盈富基金 → 恒生指数
    '2828.HK': 'HSCE',     # 恒生中国企业ETF → 恒生国企指数
    '02828.HK': 'HSCE',    # 恒生中国企业ETF → 恒生国企指数
    '3067.HK': 'HSTECH',   # 恒生科技ETF → 恒生科技指数
    '03067.HK': 'HSTECH',  # 恒生科技ETF → 恒生科技指数
    '159920': 'HSI',       # A股恒生ETF → 恒生指数
}
```

**PE 数据获取说明**：
- 恒生指数 PE 从乐咕乐股网爬取（`legulegu.com`）
- 支持恒生指数（HSI）、恒生国企指数（HSCE）、恒生科技指数（HSTECH）
- PE 百分位基于历史最高/最低计算，如无法获取则使用恒生指数历史范围（6.2-38.1）

**PB 数据获取说明**：由于恒生指数 PB 数据难以通过免费 API 获取，使用 2800.HK（盈富基金）的 `priceToBook` 作为恒生指数 PB 的代理值。

#### 1.7 汇率获取

使用 yfinance 实时获取汇率（Yahoo Finance 数据源）：
- USD/CNY（代码：`CNY=X`）
- HKD/CNY（代码：`HKDCNY=X`）

汇率数据会缓存到 `akshare_cache/exchange_rates.json`，当天有效。

如果 yfinance 未安装或获取失败，使用默认汇率：
- USD/CNY: 7.28
- HKD/CNY: 0.93

#### 1.8 场外基金净值增长率计算

对于 0 开头的6位数字代码（场外基金），会自动计算净值增长率：

| 周期 | 说明 |
|------|------|
| 1m | 近1个月增长率 |
| 3m | 近3个月增长率 |
| 6m | 近6个月增长率 |
| 1y | 近1年增长率（年化收益参考） |

> 注：增长率目前仅在日志中输出，如需写入 Notion，可在代码中取消注释相关行。

#### 1.9 加密货币支持

支持以下常见加密货币（自动添加 `-USD` 后缀）：

```python
CRYPTO_SYMBOLS = {
    'BTC', 'ETH', 'BNB', 'ADA', 'SOL', 'XRP', 'DOGE', 'DOT', 'MATIC',
    'AVAX', 'SHIB', 'TRX', 'LTC', 'UNI', 'ATOM', 'ETC', 'XLM', 'ALGO',
    'VET', 'FIL', 'ICP', 'EOS', 'AAVE', 'THETA', 'SAND', 'AXS', 'MANA',
    'GALA', 'ENJ', 'CHZ', 'FLOW', 'NEAR', 'FTM', 'CRV', 'MKR', 'COMP',
    'SNX', 'SUSHI', 'YFI', '1INCH', 'BAT', 'ZRX', 'LINK', 'GRT'
}
```

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

#### 固定收益率品种

| 代码 | 收益率 | 说明 |
|------|--------|------|
| `102277` | 2.33% | 特别国债 |

#### 数据源

使用 akshare `bond_zh_us_rate()` API 获取中美国债收益率，数据列名：
- `中国国债收益率5年`
- `中国国债收益率10年`
- `中国国债收益率30年`

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

- **定时任务**（周一至周五）: 
  - UTC 07:00 (北京时间 15:00) - A股收盘后
  - UTC 21:00 (北京时间 05:00) - 美股收盘后
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

| 缓存文件 | 内容 | 有效期 | 数据源 API |
|----------|------|--------|-----------|
| `spot_cache.pkl` | A股实时行情 | 当天 | `ak.stock_zh_a_spot_em()` |
| `etf_cache.pkl` | ETF实时行情 | 当天 | `ak.fund_etf_spot_em()` |
| `hk_cache.pkl` | 港股实时行情 | 当天 | `ak.stock_hk_spot_em()` |
| `open_fund_cache.pkl` | 开放式基金名称 | 当天 | `ak.fund_name_em()` |
| `exchange_rates.json` | 汇率数据 | 当天 | yfinance |

### PE 历史数据缓存

目录: `pe_cache/`

| 缓存文件 | 内容 | 数据源 API |
|----------|------|-----------|
| `{symbol}_pe.csv` | A股历史 PE | `ak.stock_a_lg_indicator()` |
| `{symbol}_pe.csv` | 港股历史 PE | `ak.stock_hk_indicator()` |

用于计算 PE 百分位的历史数据缓存，包含 `date` 和 `pe_ttm`（A股）或 `trade_date` 和 `pe_ratio`（港股）字段。

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
| `交易流水表` | relation | 关联到交易流水表 |

### 交易流水表字段

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `交易日期` | title | 交易日期 |
| `动作类型` | select | 买入/卖出 |
| `成交单价` | number | 交易时的成交价格 |
| `变动股数` | number | 交易数量 |
| `关联标的` | relation | 关联到股票投资组合 |
| `手续费` | number | 交易手续费 |
| `卖出后涨跌幅` | number | 卖出后价格涨跌幅（小数形式，自动计算） |

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

### 添加新的 QDII ETF 映射

在 `main.py` 的 `QDII_ETF_MAPPING` 字典中添加：

```python
QDII_ETF_MAPPING = {
    '中国QDII代码': '美股ETF代码',
    # ...
}
```

### 添加新的港股 ETF 映射

在 `main.py` 的 `HK_ETF_INDEX_MAPPING` 字典中添加：

```python
HK_ETF_INDEX_MAPPING = {
    'ETF代码': '指数代码',  # HSI/HSCE/HSTECH
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

### 添加新账户的组合同步

参考 `scripts/update_pingan_portfolio.py` 实现类似脚本，主要修改：
1. 账户名称过滤条件
2. 账户总览页面查找条件

---

## 常见问题

### Q: 为什么某些股票价格获取失败？

可能原因：
1. 股票已退市
2. 代码格式不正确
3. 数据源暂时不可用
4. 场外基金需要特殊处理（程序会自动尝试多种 API）

### Q: PE百分位如何计算？

- **A股/港股**：使用 akshare 获取历史 PE 数据，计算当前 PE 在历史分布中的百分位
- **美股**：使用 yfinance 获取近5年月度价格，结合 EPS 计算历史 PE 百分位
- **指数 ETF**：使用中证指数接口获取近10年数据计算百分位

### Q: 如何添加新账户的组合同步？

参考 `scripts/update_pingan_portfolio.py` 实现类似脚本。

### Q: 场外基金价格获取的优先级是什么？

程序会按以下顺序尝试获取场外基金（0开头6位数字）价格：
1. `ak.fund_open_fund_info_em()` - 单位净值走势
2. `ak.fund_etf_hist_em()` - ETF 历史数据
3. `ak.fund_etf_hist_sina()` - 新浪接口
4. `ak.fund_etf_fund_info_em()` - ETF 基金净值
5. `ak.fund_open_fund_daily_em()` - 开放式基金日数据
6. `ak.fund_money_fund_daily_em()` - 货币基金
7. `ak.fund_financial_fund_daily_em()` - 理财型基金

### Q: 支持哪些 Notion API 版本？

当前使用 `notion_version="2025-09-03"`，支持多数据源数据库（Multi-Datasource Database）。

---

## 技术细节

### Notion API 集成

使用多数据源数据库查询方式：

```python
database = notion.databases.retrieve(database_id=DATABASE_ID)
if 'data_sources' in database and database['data_sources']:
    data_source_id = database['data_sources'][0]['id']
    response = notion.data_sources.query(data_source_id=data_source_id)
```

### 价格获取优先级

1. **yfinance**：美股、港股、加密货币首选
2. **akshare 缓存**：A股、港股、ETF 使用预加载的缓存数据
3. **akshare API**：场外基金使用专门的 API

### 估值指标获取

| 指标 | A股 | 港股 | 美股 |
|------|-----|------|------|
| PE | akshare 缓存/历史数据 | akshare 缓存/yfinance | yfinance |
| PB | - | yfinance | yfinance |
| ROE | `ak.stock_financial_analysis_indicator()` | akshare 缓存/yfinance | yfinance |
| PEG | `ak.stock_financial_analysis_indicator()` | akshare 缓存/yfinance | yfinance |

### 依赖库版本要求

详见 `requirements.txt`，主要依赖：
- `notion-client`: Notion API 客户端
- `yfinance`: 美股/港股/加密货币行情
- `akshare`: A股/ETF/港股/基金行情
- `pandas`: 数据处理
- `requests`: HTTP 请求
- `beautifulsoup4`: HTML 解析（恒生指数数据爬取）