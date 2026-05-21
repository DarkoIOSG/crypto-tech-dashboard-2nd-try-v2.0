# 加密货币技术指标分析 Dashboard — 详细实施计划

## 一、项目背景与目标

将现有 Jupyter Notebook 中的量化技术指标分析流程，转化为一个可部署到 Mac 服务器上的实时网页应用。用户可以查看 CoinGecko Market Cap Top 200 代币的技术指标强度、趋势/反转评分及排名。

**核心参考文件：**
- `1_First_or_not_run___Tech_Fac_Price_Mcap_volumeData.ipynb` — 数据获取、代币排除逻辑、CoinGecko API 调用模式；最后一个单元格包含 `compute_features` 完整指标源码，所有指标公式以最后一个单元格为准

**最终交付物：** 一个单机部署在 Mac 上的 Web 应用，包含后端（Python FastAPI）和前端（原生 JS + TradingView Lightweight Charts），每日 UTC+8 08:30 自动更新数据。

---

## 二、技术架构

```
crypto-tech-dashboard/
|-- backend/
|   |-- main.py                       # FastAPI 应用入口 + APScheduler 定时任务
|   |-- config.py                     # 所有常量配置（从 notebook 提取）
|   |-- data/
|   |   |-- exchange_client.py        # 统一交易所 OHLCV 获取（CCXT 封装，Binance→OKX→Bybit→Gate.io 瀑布回退）
|   |   |-- coingecko_client.py       # CoinGecko Pro API 封装（代币列表 + 市值数据）
|   |   |-- symbol_mapping.py         # CoinGecko ID <-> 各交易所交易对映射表
|   |   |-- fetcher.py                # 数据拉取调度器（全量 / 增量 / 校验）
|   |   |-- exclusion.py              # 代币排除逻辑（关键词 + ID 黑名单）
|   |   |-- local_store.py            # 本地文件缓存管理（CSV 读写，原子写入）
|   |   |-- data_validator.py         # 数据一致性校验（跨源比对、日期对齐）
|   |-- indicators/
|   |   |-- base.py                   # 抽象基类 IndicatorFamily
|   |   |-- ma_cross_sma.py           # SMA 交叉家族
|   |   |-- ma_cross_ema.py           # EMA 交叉家族
|   |   |-- macd.py                   # MACD 家族
|   |   |-- rsi.py                    # RSI 家族
|   |   |-- rsi_mr.py                 # RSI 均值回归家族
|   |   |-- kdj.py                    # KDJ 随机指标
|   |   |-- bollinger.py              # 布林带家族
|   |   |-- volume_spike.py           # 成交量异动家族
|   |   |-- momentum.py               # 动量/收益率家族
|   |   |-- mean_reversion.py         # 均值回归（skip）家族
|   |   |-- zscore_ma.py              # Z-Score vs MA50/MA30 家族
|   |   |-- price_appreciation.py     # 价格升幅 + 量价联合事件
|   |   |-- registry.py               # 家族名称 -> 类的注册表
|   |-- scoring/
|   |   |-- trend_score.py            # 趋势强度综合评分（扩充版）
|   |   |-- reversal_score.py         # 反转强度综合评分（扩充版）
|   |   |-- ranking.py                # 横截面百分位排名（2 年 / 3 年窗口）
|   |-- backtest/
|   |   |-- golden_cross.py           # 金叉/死叉简单回测
|   |-- api/
|   |   |-- routes_tokens.py          # 代币列表与详情
|   |   |-- routes_indicators.py      # 指标数据与图表数据
|   |   |-- routes_scores.py          # 评分与排名
|   |   |-- routes_backtest.py        # 回测结果
|   |   |-- routes_system.py          # 系统状态、手动刷新、数据校验
|-- frontend/
|   |-- index.html                    # 单页应用外壳
|   |-- css/styles.css                # TradingView 高端深色主题
|   |-- js/
|   |   |-- app.js                    # 主控制器
|   |   |-- api.js                    # API 客户端
|   |   |-- charts/                   # 各类图表组件（candlestick, macd, rsi 等）
|   |   |-- components/               # UI 组件（选择器、参数面板、评分卡、排名侧边栏）
|   |-- lib/                          # TradingView Lightweight Charts v4
|-- local_data/                       # 本地数据缓存目录
|   |-- ohlcv/                        # 按代币存储的 OHLCV CSV 文件（统一用 CoinGecko ID 命名）
|   |   |-- bitcoin.csv               # 格式: date,open,high,low,close,volume,source
|   |   |-- ethereum.csv              #   source 列记录数据来自哪个交易所
|   |   |-- ...
|   |-- market_cap/                   # CoinGecko 市值数据
|   |   |-- top200_mcap_latest.csv    # 最新的 Top 200 代币列表 + 市值
|   |   |-- mcap_history.csv          # 历史市值数据（用于排名计算）
|   |-- metadata/
|   |   |-- symbol_map.json           # CoinGecko ID <-> Binance 符号映射
|   |   |-- last_update.json          # 最后更新时间戳及状态
|   |   |-- data_integrity_log.json   # 数据校验日志
|-- requirements.txt
|-- run.sh
|-- .env                              # 环境变量（API Key 等）
```

**技术栈：** Python FastAPI + 原生 JS + TradingView Lightweight Charts（开源，MIT 协议）。本地文件缓存（CSV），pandas 内存计算。无需 Node.js/Webpack 构建步骤。

---

## 三、数据层（重点章节）

### 3.1 数据源分工与优先级

#### 核心原则：尽量统一数据源，避免跨源日期错位；通过多交易所瀑布回退最大化 OHLC 覆盖率

| 数据类型 | 主数据源 | 回退链 | 说明 |
|---------|---------|--------|------|
| **K 线 OHLCV** | 交易所公共 API（通过 CCXT 统一访问） | Binance → OKX → Bybit → Gate.io → CoinGecko 收盘价 | 每个代币只从一个交易所获取，保证 OHLCV 内部一致 |
| **成交量** | 与 OHLCV 同源（同一交易所同一调用） | 同上 | 保证量价数据完全同源同日期 |
| **收盘价（用于指标计算）** | 交易所 OHLCV 的 Close 字段 | 同上 | 统一使用交易所 Close，不混用 CoinGecko |
| **市值（Market Cap）** | CoinGecko Pro API `/coins/markets` | 无 | 交易所不提供市值数据，必须从 CoinGecko 获取 |
| **代币列表 + 排名** | CoinGecko Pro API `/coins/markets` | 无 | 获取 Top 200 代币列表、当前价格、市值排名 |

#### 多交易所 OHLCV 获取策略（CCXT 统一层）

通过 Python CCXT 库统一访问多个交易所，按优先级瀑布式回退：

| 优先级 | 交易所 | 公共 API 端点 | 认证 | 限速 | 符号格式 | 每次上限 |
|-------|--------|-------------|------|------|---------|---------|
| 1 | **Binance** | `/api/v3/klines` | 无需 | 6000 weight/min | BTCUSDT | 1000 根 |
| 2 | **OKX** | `/api/v5/market/candles` | 无需 | 20 req/2s | BTC-USDT | 100 根 |
| 3 | **Bybit** | `/v5/market/kline` | 无需 | 宽松 | BTCUSDT | 1000 根 |
| 4 | **Gate.io** | `/api/v4/spot/candlesticks` | 无需 | 200 req/10s | BTC_USDT | 1000 根 |
| 5（兜底） | **CoinGecko** | `/market_chart/range` | Pro Key | 500 req/min | bitcoin | 仅收盘价 |

**实现逻辑（`exchange_client.py`）：**
```python
import ccxt

EXCHANGE_PRIORITY = ['binance', 'okx', 'bybit', 'gateio']

class ExchangeOHLCVClient:
    def __init__(self):
        self.exchanges = {
            'binance': ccxt.binance(),
            'okx': ccxt.okx(),
            'bybit': ccxt.bybit(),
            'gateio': ccxt.gateio(),
        }

    def fetch_ohlcv(self, symbol: str, days: int = 1000) -> tuple[pd.DataFrame, str]:
        """
        尝试从多个交易所获取 OHLCV 数据。
        返回 (DataFrame, 数据来源交易所名称)。
        """
        for name in EXCHANGE_PRIORITY:
            try:
                # CCXT 统一符号格式: "BTC/USDT"
                ohlcv = self.exchanges[name].fetch_ohlcv(
                    symbol, timeframe='1d', limit=days
                )
                if ohlcv and len(ohlcv) > 30:  # 至少 30 天数据才算有效
                    df = pd.DataFrame(ohlcv, columns=['timestamp','open','high','low','close','volume'])
                    df['date'] = pd.to_datetime(df['timestamp'], unit='ms').dt.date
                    return df, name
            except Exception:
                continue
        return None, 'none'  # 所有交易所都失败，走 CoinGecko 兜底
```

**预期覆盖率提升：**
- 仅 Binance：约 170/200 代币（~85%）
- Binance + OKX：约 185/200 代币（~92%）
- Binance + OKX + Bybit + Gate.io：约 195/200 代币（~97%）
- 剩余 ~5 个极小众代币走 CoinGecko 兜底（仅收盘价折线图）

#### 为什么优先交易所 API 而非 CoinGecko 做价格/成交量数据

1. **日期对齐问题**：CoinGecko 的 `/market_chart/range` 返回的 timestamp 可能与 UTC 00:00 有偏移（通常是 UTC 时间的某个时刻快照），而交易所 kline 严格按 UTC 00:00 切割日线。混用会导致指标计算噪音。
2. **成交量一致性**：CoinGecko 的成交量是聚合多个交易所的"总成交量"，交易所 API 是该交易所的真实成交量。OHLCV 必须同源才能保证量价关系可靠。
3. **OHLC 真实性**：CoinGecko `/market_chart/range` 只返回收盘价，没有 Open/High/Low。KDJ 等指标需要真实 High/Low。

#### CoinGecko 兜底代币的处理（约 5 个）

只有在所有 4 个交易所都找不到的代币，才走 CoinGecko 兜底：
1. K 线图：显示为收盘价折线图（前端标注"仅收盘价数据"）
2. 技术指标：Close 可用，但 KDJ 不可用（无 High/Low）
3. 评分：KDJ 分项不参与该代币的加权，其余信号正常计算。在排名中标注"数据不完整"
4. 预期：仅约 5 个极小众代币会走到这一步

### 3.2 本地文件缓存架构

#### 为什么用本地文件而非数据库

- 启动阶段优先可调试性和透明度：CSV 文件可以直接用 Excel/pandas 打开检查
- 数据量小：200 代币 × 1095 天（3 年） × 6 列 ≈ 每个文件约 50KB，总计约 10MB
- 增量更新简单：每天 append 一行到 CSV 文件末尾
- 后续可以迁移到 SQLite 或 Parquet，但初始阶段 CSV 最直观

#### 文件结构详解

```
local_data/
|-- ohlcv/
|   |-- bitcoin.csv          # OHLCV 数据（来源: binance）
|   |-- ethereum.csv         #   格式: date,open,high,low,close,volume,source
|   |-- solana.csv           #   date 为 UTC 日期 (YYYY-MM-DD)
|   |-- pi-network.csv       #   source 列: binance/okx/bybit/gateio/coingecko
|   |-- ...                  #   约 200 个文件，统一用 CoinGecko ID 命名
|
|-- market_cap/
|   |-- top200_current.csv    # 当前 Top 200 列表
|   |                         #   格式: cg_id,symbol,name,price,mcap,mcap_rank,binance_symbol
|   |-- mcap_daily/           # 每日市值快照（用于历史排名）
|   |   |-- 2024-05-12.csv   #   格式: cg_id,mcap
|   |   |-- 2024-05-13.csv
|   |   |-- ...
|
|-- metadata/
|   |-- symbol_map.json       # CoinGecko ID <-> 多交易所交易对映射
|   |                         #   {"bitcoin":{"exchange":"binance","symbol":"BTC/USDT"},...}
|   |-- last_update.json      # {"last_ohlcv_update":"2026-05-12T08:30:00+08:00",
|   |                         #  "last_mcap_update":"2026-05-12T08:30:00+08:00",
|   |                         #  "status":"idle"|"updating"|"error",
|   |                         #  "error_detail":"..."}
|   |-- data_integrity_log.json  # 数据校验结果日志
```

#### 文件读写规则

1. **首次启动（全量拉取，可接受耗时 1 小时以上）：**
   - Step A：从 CoinGecko 获取 Top 200 代币列表 → 写入 `top200_current.csv`
   - Step B：用 CCXT 在 4 个交易所中自动探测映射 → 写入 `symbol_map.json`
   - Step C：对每个代币，按优先级从交易所获取约 1095 天（3 年）日线 OHLCV → 写入 `ohlcv/{cg_id}.csv`
   - Step D：对 CoinGecko 兜底代币（约 5 个），调用 CoinGecko `/market_chart/range` → 写入同目录
   - Step E：计算全量历史评分（1095 天 × 200 代币的横截面百分位排名）→ 写入 `scores_history.csv`
   - **拉取速度估算**：Binance ~60 秒（200 代币，无严格限速）；OKX/Bybit/Gate.io 的回退代币每个 1-3 秒；CoinGecko 兜底 1 请求/秒。OHLCV 拉取总计约 5-10 分钟。
   - **评分历史计算**：1095 天 × 200 代币 × 12 家族指标，约需 30-60 分钟。期间前端显示"正在初始化历史数据..."进度条。
   - **总计首次启动约 40-70 分钟**，后续重启从本地文件秒加载。
   - 为防止限速问题，每个交易所请求间隔 CCXT 会自动处理 `rateLimit`。额外安全措施：每 50 个代币休息 5 秒。

2. **每日增量更新（08:30 UTC+8 触发）：**
   - 检查每个 CSV 文件的最后一行日期
   - 如果缺少昨日数据：调用 Binance API 获取缺失天数的数据，append 到文件末尾
   - 重新拉取 CoinGecko Top 200 列表（可能有排名变动）
   - 保存当日市值快照到 `mcap_daily/YYYY-MM-DD.csv`
   - 更新 `last_update.json`

3. **数据加载到内存：**
   - 启动时读取所有 CSV 文件到 pandas DataFrame（按代币合并为宽表）
   - 内存中维护：`df_prices`（收盘价宽表）、`df_ohlcv`（字典：cg_id → DataFrame）、`df_volume`（成交量宽表）、`df_mcap`（市值宽表）、`df_scores_history`（每日评分历史，用于时间序列百分位）
   - 增量更新后：直接 append 新行到内存 DataFrame，无需重新读取全部文件
   - **评分历史持久化**：`local_data/scores_history.csv` 格式为 `date,coin_id,trend_score,reversal_score`。每日增量追加 1 天 × 200 代币 = 200 行。避免重启时重算全量历史。

4. **原子写入保护（防数据损坏）：**
   - CSV 增量 append 采用"读取原文件 → 追加新行 → 写入 `.tmp` 文件 → `os.rename()` 覆盖原文件"策略
   - `os.rename()` 在同一文件系统上是原子操作，即使进程被 kill 也不会产生半写入文件
   - 每次 append 前检查最后一行日期，确保不会重复写入
   - 启动时增加 CSV 完整性检查：最后一行是否完整、日期是否单调递增、列数是否正确
   - 在 `last_update.json` 中记录"已完成更新的代币列表"，支持断点续传

5. **文件备份逻辑：**
   - 每次全量拉取前，将 `ohlcv/` 目录备份为 `ohlcv_backup_YYYYMMDD/`
   - 每日增量更新不做备份（只 append 一行，原子写入保证安全）
   - 保留最近 3 个备份，自动删除更早的备份

### 3.3 代币筛选逻辑

完全移植 notebook cell 2 的排除逻辑：

**关键词排除（`exclude_keywords`）：**
```python
exclude_keywords = [
    "usd", "usdt", "usdc", "busd", "dai", "tusd", "usdp", "gusd", "lusd", "fdusd",
    "usdd", "susd", "eusd", "wrapped", "wbtc", "weth", "renbtc", "staked", "stake"
]
```

**ID 黑名单（`exclude_ids`）：**
```python
exclude_ids = [
    "bridged-wrapped-ether-starkgate", "sbtc-2", "wrapped-zenbtc", "liquid-hype-yield",
    "compound-ether", "binance-peg-sol", "bitcoin-avalanche-bridged-btc-b", "binance-peg-dogecoin",
    "tbtc", "clbtc", "tether-gold", "rocket-pool-eth", "solv-btc", "pax-gold",
    "cgeth-hashkey", "frax-ether", "resolv-usr", "jupiter-perpetual", "gho",
    "stasis-eurs", "dola-usd", "blockchain-capital",
    "ousg", "mbg-by-multibank-group", "tradable-na-rent-financing-platform-sstn",
    "kinesis-gold", "kinesis-silver", "spiko-us-t-bills-money-market-fund",
    "onyc", "tradable-singapore-fintech-ssl-2", "vaneck-treasury-fund"
]
```

**排除函数：**
```python
def is_excluded(coin: dict) -> bool:
    name = coin["name"].lower()
    symbol = coin["symbol"].lower()
    cid = coin["id"].lower()
    return (any(kw in name or kw in symbol for kw in exclude_keywords)
            or cid in exclude_ids)
```

**流程：** 获取 Market Cap Top 250 × 3 页 = 750 个代币 → 排除后取前 200 个。

### 3.4 CoinGecko ID ↔ 交易所符号映射（多交易所）

#### 映射建立方法

1. **CCXT 自动探测**：对每个代币，用 CCXT 的 `load_markets()` 在 4 个交易所中查找 `{SYMBOL}/USDT` 交易对。CCXT 内部维护了各交易所的完整交易对列表。
2. **优先级选择**：如果多个交易所都有该交易对，按 Binance → OKX → Bybit → Gate.io 优先级选择。
3. **手动补充**：部分代币的 CoinGecko symbol 与交易所不同（如 `polygon-ecosystem-token` 对应 Binance 的 `POL/USDT`），维护手动映射表覆盖。
4. **CoinGecko 兜底**：所有 4 个交易所都找不到的代币，标记为 `exchange: "coingecko"`。

#### 映射文件格式 (`symbol_map.json`)
```json
{
  "bitcoin": {"exchange": "binance", "symbol": "BTC/USDT", "method": "auto"},
  "ethereum": {"exchange": "binance", "symbol": "ETH/USDT", "method": "auto"},
  "pi-network": {"exchange": "okx", "symbol": "PI/USDT", "method": "auto"},
  "hedera-hashgraph": {"exchange": "binance", "symbol": "HBAR/USDT", "method": "manual"},
  "hashnote-usyc": {"exchange": "coingecko", "symbol": null, "method": "fallback", "reason": "not_on_any_exchange"}
}
```

### 3.5 数据一致性校验（重点）

#### 问题 1：Binance 与 CoinGecko 的日期对齐

- **Binance 日线**：严格按 UTC 00:00:00 开盘，23:59:59 收盘。日期标签为开盘时间。
- **CoinGecko 日线**：时间戳可能偏移（通常在 UTC 00:00 附近，但可能有数分钟到数小时的偏移）。
- **潜在错位**：CoinGecko 的"5月12日"数据可能对应 Binance 的"5月11日"或"5月12日"。

**校验方法：**
```python
# 启动时自动校验：取 BTC 近 30 天数据，对比两个源的收盘价
# 如果 CoinGecko[date] ≈ Binance[date] 的 close（误差 < 0.5%），说明日期对齐
# 如果 CoinGecko[date] ≈ Binance[date-1] 的 close，说明 CoinGecko 有 T+1 滞后
# 记录偏移量到 metadata/data_integrity_log.json
```

**处理方案：**
- 如果检测到 CoinGecko 市值数据存在 T+1 滞后：在读取市值数据时自动偏移一天
- 收盘价和成交量**全部统一使用 Binance 数据**，不存在跨源对齐问题
- 市值数据是唯一必须从 CoinGecko 获取的，它只用于：(a) 代币排名筛选，(b) 横截面排名的 universe 确定——对日期精度要求较低（差一天不影响 Top 200 排名）

#### 问题 2：Binance 成交量 vs CoinGecko 成交量

- Binance 成交量 = 该交易对（如 BTCUSDT）在 Binance 单个交易所的成交量
- CoinGecko 成交量 = 聚合所有交易所的总成交量
- 两者数量级可能差 2-10 倍

**处理方案：**
- 指标计算（VolumeSpike、量价联合事件）**统一使用 Binance 成交量**
- 虽然 Binance 只是单交易所数据，但对于 Top 200 代币，Binance 通常是最大的交易所之一
- 成交量异动指标（vol_ratio、vol_z）是自身历史的比较，不是跨代币比较，所以单交易所数据是可接受的
- 对于 CoinGecko 兜底代币（约 5 个），使用 CoinGecko 聚合成交量并在 UI 标注

#### 问题 3：数据缺失与异常值

- **交易所维护/停盘**：某些代币某天可能没有成交数据。检测方法：volume = 0 或该天无数据行。
- **异常价格**：闪崩/闪涨导致的极端值。检测方法：日内振幅 (high-low)/close > 50%。
- **处理**：标记为异常但不删除。指标计算中对异常天做特殊处理（如跳过该天的信号生成）。

### 3.6 更新机制详解

#### 每日自动更新流程（08:30 UTC+8）

```
08:30:00  触发更新
          |
          v
Step 1:   设置 status = "updating"
          |
          v
Step 2:   拉取 CoinGecko Top 200 列表
          - 检查是否有新代币进入 / 旧代币退出
          - 新进入的代币：创建 OHLCV 文件，全量拉取历史
          - 退出的代币：保留文件但标记为 inactive
          |
          v
Step 3:   对每个代币（通过 CCXT 多交易所瀑布回退）：
          - 读取本地 CSV 最后日期
          - 通过该代币对应的交易所拉取缺失天数的 klines（通常只差 1 天）
          - 原子 Append 到 CSV 文件（.tmp + rename）
          - Append 到内存 DataFrame
          |
          v
Step 4:   对 CoinGecko 兜底代币（约 5 个）：
          - 同上逻辑，但调用 CoinGecko API（1 req/s 限速）
          |
          v
Step 5:   保存当日市值快照
          |
          v
Step 6:   重算所有代币的技术指标
          |
          v
Step 7:   重算所有代币的趋势/反转评分和排名
          |
          v
Step 8:   运行数据一致性校验
          |
          v
Step 9:   设置 status = "idle"，记录更新时间
```

**关键约束：** Step 3-4 在后台线程执行，前端 API 在更新期间仍然返回旧数据（不阻塞）。更新完成后无缝切换到新数据。

---

## 四、12 个技术指标家族

所有公式严格移植自 `1_First_or_not_run___Tech_Fac_Price_Mcap_volumeData.ipynb` 最后一个单元格中的 `compute_features` 方法。新增 KDJ。

### 默认展示 6 个核心家族（首屏可见）

| # | 家族名称 | Notebook 来源 | 代表性图表 | 默认参数 |
|---|---------|-------------|----------|---------|
| 1 | **SMA 交叉** | 最后一个单元格, 196-306 行 | 价格线 + SMA 快线/慢线 + 金叉/死叉三角标记 | **fast=5**, slow=20 |
| 2 | **MACD** | 最后一个单元格, 427-495 行 | 柱状图（绿涨红跌）+ MACD 线 + 信号线 + 零轴 | (12,26,9) |
| 3 | **RSI** | 最后一个单元格, 331-398 行 | RSI 曲线 + 30/70 水平线 + 超买超卖着色区 | period=14 |
| 4 | **布林带** | 最后一个单元格, 497-531 行 | 价格蜡烛 + 上轨/中轨/下轨 + 带宽填充 | period=20, std=2 |
| 5 | **成交量异动** | 最后一个单元格, 599-678 行 | 成交量柱（普通灰色 / 异动黄色高亮）+ 均线 | ma_window=14 |
| 6 | **动量** | 最后一个单元格, 616-621 行 | 多周期收益率折线 + 零轴 | windows=[5,10,20,30] |

### 展开可见的 6 个附加家族

| # | 家族名称 | Notebook 来源 | 代表性图表 | 默认参数 |
|---|---------|-------------|----------|---------|
| 7 | **EMA 交叉** | 最后一个单元格, 308-328 行 | 价格线 + EMA 快线/慢线 + 交叉标记 | fast=5, slow=20 |
| 8 | **RSI 均值回归** | 最后一个单元格, 400-422 行 | RSI 超卖距离柱状图（正值 = 超卖信号强度） | period=14 |
| 9 | **KDJ 随机指标** | 新增实现 | K 线/D 线/J 线 + 20/80 超买超卖区着色 | N=9, M1=3, M2=3 |
| 10 | **均值回归(skip)** | 最后一个单元格, 533-597 行 | Z-score 曲线 + ±2σ 水平线 + 着色区 | L=40, S=16 |
| 11 | **Z-Score vs MA50** | 最后一个单元格, 680-712 行 | 价格 + MA50 线 + 偏离度面积图（绿上红下） | ma=50, z_window=40 |
| 12 | **价格升幅** | 最后一个单元格, 607-678 行 | 收益率柱 + 量价联合事件菱形标记 | threshold=5% |

### 各家族详细计算公式

#### 4.1 SMA 交叉家族

**来源：** `1_First_or_not_run___Tech_Fac_Price_Mcap_volumeData.ipynb` 最后一个单元格, 第 196-306 行

**参数（用户可调）：**
- `fast`：快线周期，默认 **5**
- `slow`：慢线周期，默认 20
- 可选的预设组合：(5,20), (7,30), (10,30), (20,50)

**计算步骤：**
```
1. sma_fast = Close.rolling(fast).mean()
2. sma_slow = Close.rolling(slow).mean()
3. diff = (sma_fast - sma_slow) / Close
4. prox = 1.0 / (1.0 + |diff| / 0.01)          # 接近度，0~1
5. slope_10d = 10日价格斜率（线性回归）
6. gate = 1 if slope_10d > 0 else 0              # 趋势门控
7. cross_strength = prox × gate                   # 交叉强度（无符号）
8. cross_strength_signed = prox × sign(diff) × gate  # 有方向的交叉强度
9. cross_up = (diff_yesterday ≤ 0) AND (diff_today > 0)  # 金叉事件
10. cross_down = (diff_yesterday ≥ 0) AND (diff_today < 0)  # 死叉事件
```

**输出指标：** `sma_prox`, `sma_cross_strength`, `sma_cross_strength_signed`, `sma_cross_up`, `sma_cross_down`

**图表展示：** 价格蜡烛/线 + SMA 快线（蓝色）+ SMA 慢线（橙色）+ 金叉三角（绿色向上）+ 死叉三角（红色向下）

#### 4.2 EMA 交叉家族

**来源：** `1_First_or_not_run___Tech_Fac_Price_Mcap_volumeData.ipynb` 最后一个单元格, 第 308-328 行

与 SMA 家族完全相同的结构，但使用 `ewm(span=w, adjust=False).mean()` 替代 `rolling().mean()`。

**参数：** fast=5, slow=20（与 SMA 相同）

**输出指标：** `ema_prox`, `ema_cross_strength`, `ema_cross_strength_signed`, `ema_cross_up`, `ema_cross_down`

#### 4.3 MACD 家族

**来源：** `1_First_or_not_run___Tech_Fac_Price_Mcap_volumeData.ipynb` 最后一个单元格, 第 427-495 行

**参数（用户可调）：**
- `fast`：快线 EMA 周期，默认 12
- `slow`：慢线 EMA 周期，默认 26
- `signal`：信号线 EMA 周期，默认 9
- 可选预设：(5,10,4), (10,20,8), (12,26,9), (20,40,16)

**计算步骤：**
```
1. ema_fast = Close.ewm(span=fast, adjust=False).mean()
2. ema_slow = Close.ewm(span=slow, adjust=False).mean()
3. macd_line = (ema_fast - ema_slow) / Close     # 归一化到价格
4. signal_line = macd_line.ewm(span=signal, adjust=False).mean()
5. histogram = macd_line - signal_line
6. hist_rma3 = histogram.ewm(alpha=1/3, adjust=False).mean()  # RMA(3) 平滑
7. hist_slope5 = 5日 histogram 斜率
8. cross_up = (histogram_yesterday ≤ 0) AND (histogram_today > 0)
9. cross_down = (histogram_yesterday ≥ 0) AND (histogram_today < 0)
10. cross_event = cross_up.astype(int) - cross_down.astype(int)  # +1/0/-1
```

**输出指标：** `macd_line`, `macd_signal`, `macd_hist`, `macd_hist_rma3`, `macd_hist_slope5`, `macd_cross_up`, `macd_cross_down`, `macd_cross_event`

#### 4.4 RSI 家族

**来源：** `1_First_or_not_run___Tech_Fac_Price_Mcap_volumeData.ipynb` 最后一个单元格, 第 331-398 行

**参数：**
- `period`：RSI 周期，默认 14
- 可选：7, 14, 21, 28

**计算步骤（Wilder 平滑）：**
```
1. delta = Close.diff()
2. gains = delta.clip(lower=0)
3. losses = (-delta).clip(lower=0)
4. avg_gain = gains.ewm(alpha=1.0/period, adjust=False).mean()   # Wilder RMA
5. avg_loss = losses.ewm(alpha=1.0/period, adjust=False).mean()
6. rs = avg_gain / (avg_loss + 1e-10)
7. rsi = 100 - (100 / (1 + rs))
8. rsi_scaled = (rsi - 50) / 50                    # 归一化到 [-1, 1]
9. rsi_dist_os = (30 - rsi) / 30                   # 距超卖线距离（正值=超卖）
10. rsi_dist_ob = (rsi - 70) / 30                  # 距超买线距离（正值=超买）
11. rsi_dist_os_clip = max(rsi_dist_os, 0)         # 仅保留超卖信号
12. rsi_dist_ob_clip = max(rsi_dist_ob, 0)         # 仅保留超买信号
13. rsi_turn_event = RSI 与其 3 日均线的交叉事件
```

**输出指标：** `rsi`, `rsi_scaled`, `rsi_dist_os`, `rsi_dist_ob`, `rsi_dist_os_clip`, `rsi_dist_ob_clip`, `rsi_turn_event`

**关键注意：** 必须使用 Wilder 平滑（`alpha=1/period`），不是简单 SMA。这会导致与一些在线工具的 RSI 值有微小差异。

#### 4.5 RSI 均值回归家族

**来源：** `1_First_or_not_run___Tech_Fac_Price_Mcap_volumeData.ipynb` 最后一个单元格, 第 400-422 行

**参数：** period=14（可选 6, 14, 18, 21, 28）

使用 RSI 距离超卖线的距离作为均值回归信号。

**输出指标：** `rsi_dist_os_{period}`, `rsi_dist_os_{period}_clip`

#### 4.6 KDJ 随机指标（新增）

**不在原 notebook 中，需要新增实现。**

**参数：**
- N=9（RSV 回看窗口）
- M1=3（K 线平滑因子）
- M2=3（D 线平滑因子）

**计算步骤：**
```
1. lowest_low = Low.rolling(N).min()
2. highest_high = High.rolling(N).max()
3. rsv = (Close - lowest_low) / (highest_high - lowest_low + 1e-10) × 100
4. K[0] = 50, D[0] = 50                           # 初始值
5. K[t] = (1 - 1/M1) × K[t-1] + (1/M1) × RSV[t]  # 即 2/3 × K_prev + 1/3 × RSV
6. D[t] = (1 - 1/M2) × D[t-1] + (1/M2) × K[t]    # 即 2/3 × D_prev + 1/3 × K
7. J = 3×K - 2×D
8. kdj_os_distance = (20 - J) / 20                 # 距超卖区距离（正值=超卖）
9. kdj_ob_distance = (J - 80) / 20                 # 距超买区距离（正值=超买）
10. kdj_golden_cross = (K_yesterday < D_yesterday) AND (K_today > D_today)  # 金叉
11. kdj_death_cross = (K_yesterday > D_yesterday) AND (K_today < D_today)   # 死叉
```

**注意：** KDJ 需要 High 和 Low 数据，因此只对有交易所 OHLC 数据的代币计算。CoinGecko 兜底代币（仅收盘价，约 5 个）的 KDJ 显示 N/A。

**输出指标：** `kdj_k`, `kdj_d`, `kdj_j`, `kdj_os_distance`, `kdj_ob_distance`, `kdj_golden_cross`, `kdj_death_cross`

#### 4.7 布林带家族

**来源：** `1_First_or_not_run___Tech_Fac_Price_Mcap_volumeData.ipynb` 最后一个单元格, 第 497-531 行

**参数：** period=20, num_std=2.0（可选 period: 5,10,20,40,80）

**计算步骤：**
```
1. mid = Close.rolling(period).mean()              # 中轨 = SMA
2. std = Close.rolling(period).std()
3. upper = mid + num_std × std                     # 上轨
4. lower = mid - num_std × std                     # 下轨
5. pctb = (Close - lower) / (upper - lower) - 0.5  # %B, 范围 [-0.5, 0.5]
6. width = (upper - lower) / mid                   # 带宽
7. bb_z = (Close - mid) / std                      # Z-score
8. squeeze = -width 的横截面标准化                    # 负值 = 收缩
```

**输出指标：** `bb_pctb`, `bb_width`, `bb_z`, `bb_squeeze`, 以及 `upper`, `mid`, `lower`（用于图表叠加）

#### 4.8 成交量异动家族

**来源：** `1_First_or_not_run___Tech_Fac_Price_Mcap_volumeData.ipynb` 最后一个单元格, 第 599-678 行

**参数：** ma_window=14（可选 7, 14, 21）

**计算步骤：**
```
1. vol_ma = Volume.rolling(ma_window).mean()
2. vol_std = Volume.rolling(ma_window).std()
3. vol_ratio = Volume / vol_ma                     # 成交量比率
4. vol_z = (Volume - vol_ma) / (vol_std + 1e-10)  # 成交量 Z-score
5. vol_spike_3x = (vol_ratio >= 3.0).astype(float)    # 3倍异动事件
6. vol_spike_2sigma = (vol_z >= 2.0).astype(float)    # 2σ 异动事件
```

**输出指标：** `vol_ratio`, `vol_z`, `vol_spike_3x`, `vol_spike_2sigma`

#### 4.9 动量家族

**来源：** `1_First_or_not_run___Tech_Fac_Price_Mcap_volumeData.ipynb` 最后一个单元格, 第 616-621 行

**参数：** windows=[5,10,20,30]

**计算：**
```
mom_ret_{h}d = Close / Close.shift(h) - 1          # h 日收益率
```

**输出指标：** `mom_ret_5d`, `mom_ret_10d`, `mom_ret_20d`, `mom_ret_30d`

#### 4.10 均值回归(skip)家族

**来源：** `1_First_or_not_run___Tech_Fac_Price_Mcap_volumeData.ipynb` 最后一个单元格, 第 533-597 行

**参数：** L=40（回看窗口），S=16（跳过天数）

**计算：**
```
1. anchor_price = Close.shift(S)                   # 跳过 S 天后的价格
2. lookback_price = Close.shift(L + S)             # 再往前看 L 天
3. ret = anchor_price / lookback_price - 1         # 这段区间的收益率
4. mr_z = (ret - ret.rolling(120).mean()) / ret.rolling(120).std()  # Z 标准化
5. mr_rank = ret.rank(pct=True)                    # 横截面百分位
```

**输出指标：** `mr_z_{L}_skip{S}`, `mr_rank_{L}_skip{S}`

#### 4.11 Z-Score vs MA50 家族

**来源：** `1_First_or_not_run___Tech_Fac_Price_Mcap_volumeData.ipynb` 最后一个单元格, 第 680-712 行

**参数：** ma_period=50, z_windows=[20,40,80,120]

**计算：**
```
1. ma50 = Close.rolling(50).mean()
2. dev = Close / ma50 - 1                          # 相对偏离度
3. dev_z_{w} = (dev - dev.rolling(w).mean()) / dev.rolling(w).std()  # 偏离度 Z-score
4. dev_z_gt2sigma_{w} = (|dev_z| >= 2).astype(float)  # 极端偏离事件
5. ma50_cross_up = (Close_yesterday < ma50_yesterday) AND (Close_today > ma50_today)
6. ma50_cross_dn = (Close_yesterday > ma50_yesterday) AND (Close_today < ma50_today)
7. ma50_slope_{h}d = (ma50 / ma50.shift(h) - 1)   # MA50 的 h 日变化率
```

**输出指标：** `ma50_dev`, `ma50_dev_z_40`, `ma50_dev_z_gt2sigma_40`, `ma50_cross_up`, `ma50_cross_dn`, `ma50_slope_5d`, `ma50_slope_10d`, `ma50_slope_20d`

#### 4.12 价格升幅家族

**来源：** `1_First_or_not_run___Tech_Fac_Price_Mcap_volumeData.ipynb` 最后一个单元格, 第 607-678 行

**参数：** threshold=5%

**计算：**
```
1. price_ret_{h}d = Close / Close.shift(h) - 1     # h 日收益率
2. price_app_5pct_{h}d = (price_ret >= 0.05).astype(float)  # 5% 升幅事件
3. vol3x_and_price5 = vol_spike_3x AND price_app_5pct       # 量价联合事件
4. vol2sigma_and_price5 = vol_spike_2sigma AND price_app_5pct
```

**输出指标：** `price_ret_20d`, `price_app_5pct_10d`, `vol3x_and_price5_10_10d`, `vol2sigma_and_price5_10_10d`

---

## 五、评分系统（扩充版）

### 重要说明

1. **关于被注释指标**：notebook 最后一个单元格中部分指标被注释掉（如 `rsi_turn_event`、`macd_hist_slope5`、`bb_pctb` 等，标注为"训练窗容易成为噪声冠军"）。这些指标在 ML 自动选择框架中表现不稳定，但在 Dashboard 的固定评分体系中仍然有效——Dashboard 不做 ML 特征选择，而是固定使用一组预定义信号做评分，因此这些指标仍然纳入使用。

2. **参数选择**：评分使用每个家族的**一组默认参数**（如 MACD 只用 12,26,9，SMA 交叉只用 5,20）。不做多参数族的自动选择。前端图表展示也默认使用同一组参数，但用户可以手动调整（调整后仅影响图表展示，不影响评分）。

### 5.1 趋势强度评分（0-100）

衡量看涨趋势的强度。综合多个指标家族的信号，横截面百分位排名后等权平均。

#### 趋势评分组成部分（扩充为 9 个信号）

| 分组 | 信号名称 | 指标 | 含义 | 权重 |
|------|---------|------|------|------|
| **动量** | 短期动量 | `mom_ret_10d` | 10 日收益率 | 1 |
| **动量** | 中期动量 | `mom_ret_20d` | 20 日收益率 | 1 |
| **MACD** | MACD 柱状图 | `macd_hist_12_26_9` | 正值 = 看涨 | 1 |
| **MACD** | MACD 柱状图斜率 | `macd_hist_slope5_12_26_9` | 正斜率 = 动能增强 | 1 |
| **SMA 交叉** | SMA 金叉强度 | `sma_cross_strength_signed_5_20` | 正值 = 快线在上 | 1 |
| **EMA 交叉** | EMA 金叉强度 | `ema_cross_strength_signed_5_20` | 正值 = 快线在上（更灵敏） | 1 |
| **Z-Score MA50** | MA50 趋势斜率 | `ma50_slope_20d` | 正斜率 = MA50 上行 | 1 |
| **Z-Score MA50** | MA50 偏离度 | `ma50_dev` | 正偏离 = 价格在 MA50 之上 | 1 |
| **布林带** | 布林带位置 | `bb_pctb_20` | 接近上轨 = 强势 | 1 |

**计算方法：**
```python
def trend_strength(all_tokens_indicators: dict) -> dict:
    signals = [
        'mom_ret_10d', 'mom_ret_20d',
        'macd_hist_12_26_9', 'macd_hist_slope5_12_26_9',
        'sma_cross_strength_signed_5_20', 'ema_cross_strength_signed_5_20',
        'ma50_slope_20d', 'ma50_dev', 'bb_pctb_20'
    ]
    # 对每个信号，计算全市场 200 个代币的横截面百分位排名（0~100）
    percentiles = {}
    for sig in signals:
        values = {token: indicators[sig] for token, indicators in all_tokens_indicators.items()}
        series = pd.Series(values)
        percentiles[sig] = series.rank(pct=True) * 100

    # 等权平均所有信号的百分位
    trend_scores = sum(percentiles[sig] for sig in signals) / len(signals)
    return trend_scores  # Series: token -> score (0-100)
```

### 5.2 反转强度评分（0-100）

衡量超卖/反转潜力。综合超卖类指标的信号。

#### 反转评分组成部分（扩充为 7 个信号）

| 分组 | 信号名称 | 指标 | 含义 | 权重 |
|------|---------|------|------|------|
| **RSI** | RSI 超卖距离 | `rsi_dist_os_14` | 正值 = 越超卖 | 1 |
| **RSI** | RSI 反转事件 | `rsi_turn_event_14` | RSI 从超卖区拐头向上 | 1 |
| **KDJ** | KDJ 超卖距离 | `kdj_os_distance` | J 线低于 20 = 超卖 | 1 |
| **布林带** | 布林带 Z-Score（取反）| `-bb_z_20` | 低于下轨 = 超卖 | 1 |
| **均值回归** | MR Z-Score | `mr_z_40_skip16` | 高值 = 强均值回归信号 | 1 |
| **Z-Score MA50** | MA50 偏离（取反）| `-ma50_dev_z_40` | 远低于 MA50 = 反转潜力 | 1 |
| **动量** | 短期负动量 | `-mom_ret_5d` | 近期跌幅大 = 超卖 | 1 |

**计算方法：** 与趋势强度相同——横截面百分位排名后等权平均。

### 5.3 百分位排名机制（2 年 / 3 年窗口）

#### 核心需求

不仅在当前 Top 200 代币间做横截面排名，还要提供**时间序列维度**的百分位——即该代币当前的趋势/反转得分在其自身近 2 年或近 3 年历史中处于什么位置。

#### 两种排名维度

| 排名维度 | 含义 | 计算方法 |
|---------|------|---------|
| **横截面排名** | 当前时刻在 200 个代币中的位置 | `score.rank(pct=True) * 100`，一个数字 |
| **时间序列排名（2 年）** | 该代币当前得分在其近 2 年历史得分中的位置 | 取近 730 天（2 年交易日）的每日得分，计算当前值的百分位 |
| **时间序列排名（3 年）** | 该代币当前得分在其近 3 年历史得分中的位置 | 取近 1095 天的每日得分，计算当前值的百分位 |

#### 实现方式

```python
def time_series_percentile(current_score: float, historical_scores: pd.Series, years: int) -> float:
    """
    计算 current_score 在近 N 年 historical_scores 中的百分位。
    """
    cutoff = len(historical_scores) - years * 365
    recent = historical_scores.iloc[max(0, cutoff):]
    return (recent < current_score).mean() * 100
```

#### 展示方式

```
趋势强度: 72 / 100
├── 横截面排名: Top 15%  (在当前 200 个代币中)
├── 2 年历史排名: Top 22% (在 BTC 自身近 2 年历史中)
└── 3 年历史排名: Top 18% (在 BTC 自身近 3 年历史中)
```

这样用户可以同时看到：(a) 这个代币在当前市场中有多强，(b) 这个代币在其自身历史中有多强。

---

## 六、回测模块（附加功能）

- **策略：** SMA(fast) 上穿 SMA(slow) = 金叉买入（次日收盘价）；下穿 = 死叉卖出
- **输出指标：** 累计收益率曲线、总收益率、年化收益率、Sharpe 比率、最大回撤、胜率、交易次数
- **用户可调参数：** fast/slow 周期（默认 5/20）、回测起始日期
- **展示位置：** 主页面底部可折叠面板

---

## 七、前端页面设计

### 7.1 整体布局

桌面端优先设计，移动端基本适配（单列布局，图表自适应宽度）。

```
+------------------------------------------------------------------+--------+
| 顶栏: "Crypto Tech Dashboard"        最后更新时间 | [刷新] 按钮  | 排名   |
+------------------------------------------------------------------+ 侧边栏 |
| [BTC v] 代币选择器(可搜索)   $104,230   市值: $2.03T             | (可折叠)|
| 趋势: 72 (横截面Top15% | 2年Top22%)                             |        |
| 反转: 34 (横截面Top78% | 2年Top65%)                             | Top 20 |
+------------------------------------------------------------------+ 代币   |
| 主 K 线图（蜡烛图 + 成交量柱，约 35% 高度）                       | 按趋势 |
| Binance OHLC 真实蜡烛数据                                        | 或反转 |
| TradingView Lightweight Charts，支持缩放/拖拽                     | 排序   |
+------------------------------------------------------------------+        |
| 6 个核心指标面板（2 列网格）                                       | 点击   |
| +---------------------------+  +---------------------------+      | 切换   |
| | SMA 交叉 (5/20)           |  | MACD (12,26,9)            |      | 主视图 |
| | [fast: 5] [slow: 20]      |  | [fast: 12] [slow: 26]     |      |        |
| | <价格+双均线+金叉死叉标记>  |  | <柱状图+MACD线+信号线>     |      |        |
| +---------------------------+  +---------------------------+      |        |
| | RSI (14)                  |  | 布林带 (20)                |      |        |
| | [period: 14]              |  | [period: 20] [std: 2]     |      |        |
| | <RSI线+30/70+着色区>       |  | <蜡烛+三条带+填充>         |      |        |
| +---------------------------+  +---------------------------+      |        |
| | 成交量异动 (14)            |  | 动量                       |      |        |
| | [window: 14]              |  | [5d/10d/20d/30d]          |      |        |
| | <量柱+异动黄色高亮>        |  | <多线折线+零轴>            |      |        |
| +---------------------------+  +---------------------------+      |        |
|                                                                   |        |
| [▼ 展开更多指标]                                                   |        |
| +---------------------------+  +---------------------------+      |        |
| | EMA 交叉 (5/20)           |  | RSI 均值回归 (14)         |      |        |
| +---------------------------+  +---------------------------+      |        |
| | KDJ (9,3,3)              |  | 均值回归 skip (40,16)     |      |        |
| +---------------------------+  +---------------------------+      |        |
| | Z-Score vs MA50           |  | 价格升幅                   |      |        |
| +---------------------------+  +---------------------------+      |        |
+------------------------------------------------------------------+        |
| 评分详情面板                                                      |        |
| +-------------------------------+  +---------------------------+  |        |
| | 趋势强度                       |  | 反转强度                  |  |        |
| |   [SVG 仪表盘: 72]            |  |   [SVG 仪表盘: 34]       |  |        |
| |   横截面: Top 15%             |  |   横截面: Top 78%        |  |        |
| |   2年历史: Top 22%            |  |   2年历史: Top 65%       |  |        |
| |   3年历史: Top 18%            |  |   3年历史: Top 58%       |  |        |
| |   --- 9 个分项 ---            |  |   --- 7 个分项 ---       |  |        |
| |   动量10d:    78              |  |   RSI超卖:     12        |  |        |
| |   动量20d:    71              |  |   RSI反转事件:  45        |  |        |
| |   MACD柱:    65              |  |   KDJ超卖:     28        |  |        |
| |   MACD斜率:  58              |  |   布林Z(取反):  45        |  |        |
| |   SMA金叉:   81              |  |   均值回归:     38        |  |        |
| |   EMA金叉:   76              |  |   MA50偏离:    42        |  |        |
| |   MA50斜率:  70              |  |   负动量5d:    55        |  |        |
| |   MA50偏离:  68              |  |                          |  |        |
| |   布林位置:  62              |  |                          |  |        |
| +-------------------------------+  +---------------------------+  |        |
+------------------------------------------------------------------+        |
| 回测面板（默认折叠）                                               |        |
+------------------------------------------------------------------+--------+
```

### 7.2 深色主题配色（TradingView 高端风格）

```css
:root {
    /* 背景层次 */
    --bg-primary: #131722;         /* 主背景 */
    --bg-secondary: #1e222d;       /* 卡片/面板背景 */
    --bg-tertiary: #2a2e39;        /* 输入框/hover 背景 */
    --bg-elevated: #363a45;        /* 弹出层背景 */

    /* 文字层次 */
    --text-primary: #d1d4dc;       /* 主文字 */
    --text-secondary: #787b86;     /* 次要文字/标签 */
    --text-muted: #4c525e;         /* 禁用/占位文字 */

    /* 强调色 */
    --accent-green: #26a69a;       /* 看涨/正面/金叉 */
    --accent-red: #ef5350;         /* 看跌/负面/死叉 */
    --accent-blue: #2962ff;        /* 高亮/链接/选中 */
    --accent-yellow: #f7c948;      /* 警告/异动标记 */
    --accent-purple: #ab47bc;      /* 特殊标记 */

    /* 边框 */
    --border-primary: #363a45;     /* 主边框 */
    --border-subtle: #2a2e39;      /* 细微分割线 */

    /* 图表专用色 */
    --chart-candle-up: #26a69a;    /* 阳线 */
    --chart-candle-down: #ef5350;  /* 阴线 */
    --chart-volume: #5d6673;       /* 普通成交量柱 */
    --chart-volume-spike: #f7c948; /* 异动成交量柱 */
    --chart-ma-fast: #2196f3;      /* 快均线 */
    --chart-ma-slow: #ff9800;      /* 慢均线 */
    --chart-bb-fill: rgba(33,150,243,0.05); /* 布林带填充 */
}
```

### 7.3 交互设计

- **代币选择器：** 可搜索的下拉菜单，支持按 symbol 和 name 模糊搜索。选择后所有图表和评分联动更新。显示当前价格和 24h 涨跌幅。
- **参数调节：** 每个指标面板右上角有参数输入框（number input），修改后 300ms 防抖，实时向后端请求新数据并刷新图表。参数旁有"重置"按钮恢复默认值。
- **刷新按钮：** 调用 `POST /api/refresh`，按钮变为旋转动画，轮询 `/api/status` 直到完成。更新期间其他交互不受影响。
- **图表时间轴同步（必须实现，不可分阶段）：** 所有图表共享时间范围。用户在主 K 线图上缩放/拖拽时，下方所有指标图表联动同步。实现方式：主 K 线图为 master，监听 `subscribeVisibleTimeRangeChange` 事件，单向广播给所有 slave 子图表（调用 `timeScale().setVisibleRange()`）。用全局 `isSyncing` 锁防止事件循环。
- **排名侧边栏：** 右侧 250px 宽的可折叠面板。显示 Top 20 代币，可按趋势/反转排名切换。点击代币名称直接切换主视图。每个代币显示分数和小型趋势 sparkline。
- **展开/折叠：** 附加 6 个指标家族默认折叠，点击"展开更多指标"按钮展开，带平滑动画。
- **移动端适配：** `@media (max-width: 768px)` 时所有面板变为单列，侧边栏变为底部可拉起抽屉。

---

## 八、API 接口设计

| 端点 | 方法 | 说明 | 返回格式 |
|------|-----|------|---------|
| `/api/tokens` | GET | 所有被追踪的代币列表 | `[{id, symbol, name, price, mcap, rank, has_binance}]` |
| `/api/token/{coin_id}` | GET | 代币详情 + 所有指标最新值 + 评分 | `{info, indicators, scores}` |
| `/api/ohlc/{coin_id}` | GET | K 线 OHLC 时间序列 | `[{time, open, high, low, close, volume}]` |
| `/api/indicators/{coin_id}/{family}` | GET | 某家族的图表时间序列。支持 `?fast=5&slow=20` 等参数覆盖 | `{params, current, chart_data}` |
| `/api/indicators/{coin_id}` | GET | 所有家族的当前值汇总 | `{family_name: {indicator: value}}` |
| `/api/scores/{coin_id}` | GET | 趋势 + 反转评分 + 三种百分位 | `{trend, reversal, percentiles}` |
| `/api/rankings` | GET | 全市场排名。`?sort_by=trend|reversal&limit=20` | `[{id, symbol, score, percentile}]` |
| `/api/backtest/{coin_id}` | GET | 金叉回测。`?fast=5&slow=20&start=2023-01-01` | `{stats, equity_curve}` |
| `/api/refresh` | POST | 触发手动数据刷新 | `{status: "started"}` |
| `/api/status` | GET | 系统状态 | `{last_update, token_count, status, errors}` |
| `/api/data-check` | GET | 数据一致性校验结果 | `{alignment, missing, anomalies}` |

---

## 九、实施步骤

### 阶段 1：数据层基础建设

| 步骤 | 任务 | 关键文件 | 验收标准 |
|------|------|---------|---------|
| 1.1 | 创建项目结构 + `config.py`（所有常量） | `config.py` | 所有参数常量可从此文件一处修改 |
| 1.2 | 实现 `exclusion.py`（代币排除） | `exclusion.py` | 输出与 notebook cell 2 完全一致 |
| 1.3 | 实现 `exchange_client.py`（CCXT 多交易所 OHLCV） | `exchange_client.py` | Binance→OKX→Bybit→Gate.io 瀑布回退，BTC/ETH/PI 均可获取 |
| 1.4 | 实现 `coingecko_client.py`（代币列表 + 市值 + 兜底） | `coingecko_client.py` | Top 200 列表 + 极少数兜底代币收盘价 |
| 1.5 | 实现 `symbol_mapping.py`（ID↔多交易所符号映射） | `symbol_mapping.py` | CCXT 自动探测 + 手动补充，OHLC 覆盖率 > 97% |
| 1.6 | 实现 `local_store.py`（CSV 读写，原子写入） | `local_store.py` | 全量写入、增量 append（原子 rename）、完整性检查 |
| 1.7 | 实现 `fetcher.py`（数据拉取调度） | `fetcher.py` | 全量拉取 200 代币（含 3 年历史）+ 增量更新 1 天 + 断点续传 |
| 1.8 | 实现 `data_validator.py`（一致性校验） | `data_validator.py` | 日期对齐检测、缺失天检测、异常价格检测、跨源比对 |
| 1.9 | 端到端数据层测试 | 测试脚本 | BTC/ETH 价格与交易所官网完全一致，PI 从 OKX 获取 |

### 阶段 2：指标引擎

| 步骤 | 任务 | 关键文件 | 验收标准 |
|------|------|---------|---------|
| 2.1 | 实现 `base.py` 抽象基类 | `base.py` | 定义 compute() 和 compute_chart_series() 接口 |
| 2.2 | 实现 SMA 交叉家族 | `ma_cross_sma.py` | 金叉/死叉事件与 TradingView 一致 |
| 2.3 | 实现 EMA 交叉家族 | `ma_cross_ema.py` | 同上 |
| 2.4 | 实现 MACD 家族 | `macd.py` | MACD 值与 TradingView 差异 < 0.1% |
| 2.5 | 实现 RSI 家族 | `rsi.py` | RSI 值与 TradingView 差异 < 1（注意 Wilder 平滑） |
| 2.6 | 实现 RSI 均值回归家族 | `rsi_mr.py` | 超卖距离信号正确 |
| 2.7 | 实现 KDJ 家族（新增） | `kdj.py` | KDJ 值与通达信/TradingView 一致 |
| 2.8 | 实现布林带家族 | `bollinger.py` | %B、Z-score 正确 |
| 2.9 | 实现成交量异动家族 | `volume_spike.py` | 3x 异动检测与手动核算一致 |
| 2.10 | 实现动量家族 | `momentum.py` | 收益率计算正确 |
| 2.11 | 实现均值回归(skip)家族 | `mean_reversion.py` | Z-score 与 notebook 输出对比 |
| 2.12 | 实现 Z-Score vs MA50 家族 | `zscore_ma.py` | MA50 偏离度与手动计算一致 |
| 2.13 | 实现价格升幅家族 | `price_appreciation.py` | 量价联合事件检测正确 |
| 2.14 | 实现 `registry.py` | `registry.py` | 所有 12 个家族注册并可按名查找 |

### 阶段 3：评分 + 排名 + 回测 + API

| 步骤 | 任务 | 关键文件 |
|------|------|---------|
| 3.1 | 实现 `trend_score.py`（趋势评分 9 信号） | `trend_score.py` |
| 3.2 | 实现 `reversal_score.py`（反转评分 7 信号） | `reversal_score.py` |
| 3.3 | 实现 `ranking.py`（横截面 + 2年/3年时间序列百分位 + `scores_history.csv` 持久化） | `ranking.py` |
| 3.4 | 实现 `golden_cross.py`（金叉回测） | `golden_cross.py` |
| 3.5 | 实现所有 API 路由 | `routes_*.py` |
| 3.6 | 实现 `main.py`（FastAPI + APScheduler UTC+8 08:30） | `main.py` |

### 阶段 4：前端

| 步骤 | 任务 |
|------|------|
| 4.1 | HTML 结构 + 深色主题 CSS（TradingView 高端风格） |
| 4.2 | 代币选择器（可搜索下拉 + 价格/涨跌幅显示） |
| 4.3 | 主 K 线蜡烛图（Binance OHLC + Lightweight Charts） |
| 4.4 | 6 个核心指标图表面板（含参数调节） |
| 4.5 | 6 个附加指标图表面板（默认折叠） |
| 4.6 | 评分仪表盘（SVG 仪表 + 三种百分位 + 分项明细） |
| 4.7 | 排名侧边栏（Top 20 + sparkline + 切换主视图） |
| 4.8 | 回测面板（可折叠 + 权益曲线图） |
| 4.9 | 移动端适配（媒体查询 + 单列布局） |

### 阶段 5：部署与测试

| 步骤 | 任务 |
|------|------|
| 5.1 | `requirements.txt` + `run.sh` + `.env` |
| 5.2 | macOS launchd 开机自启配置 |
| 5.3 | 完整验证流程（见第十一章） |

---

## 十、部署方案

### 10.1 依赖

```
fastapi>=0.115
uvicorn[standard]>=0.30
pandas>=2.2
numpy>=1.26
scipy>=1.12
requests>=2.31
ccxt>=4.0                   # 统一多交易所 API 访问（Binance/OKX/Bybit/Gate.io）
apscheduler>=3.10
python-dotenv>=1.0
```

### 10.2 环境变量（`.env` 文件）

```
COINGECKO_API_KEY=你的Pro API Key
UPDATE_HOUR=8
UPDATE_MINUTE=30
UPDATE_TIMEZONE=Asia/Shanghai
DATA_DIR=./local_data
BACKUP_KEEP=3
```

### 10.3 启动

```bash
cd crypto-tech-dashboard
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python -m backend.main   # 或 uvicorn backend.main:app --host 0.0.0.0 --port 8080
```

### 10.4 macOS 开机自启

通过 `launchd` plist 配置，放置在 `~/Library/LaunchAgents/com.iosg.crypto-dashboard.plist`。

---

## 十一、详细验证方案

### 11.1 数据源可靠性验证

| 验证项 | 验证方法 | 预期结果 | 频率 |
|-------|---------|---------|------|
| **多交易所连通性** | 对 Binance/OKX/Bybit/Gate.io 分别调用 CCXT 的 `load_markets()` | 至少 3/4 个交易所可用 | 每次更新前 |
| **Binance 限速检测** | 监控 CCXT 的 rateLimit 机制，确保不触发 429 | 单次更新 200 代币无限速错误 | 每次更新时 |
| **OKX/Bybit/Gate.io 限速** | 同上，CCXT 自动处理各交易所限速 | 回退代币获取无报错 | 每次更新时 |
| **CoinGecko API 可用性** | 调用 `/api/v3/ping`，检查返回正常 | 状态码 200 | 每次更新前 |
| **CoinGecko 限速** | Pro 版 500 请求/分钟 | 单次更新约 10 个请求（代币列表 + ~5 个兜底代币） | 每次更新时 |
| **API Key 有效性** | 首次启动时测试 CoinGecko 认证端点 | 返回非 401/403 | 启动时 |
| **交易对存在性** | 用 CCXT 的 `load_markets()` 刷新各交易所可用交易对，与映射表比对 | 退市的交易对自动降级到下一个交易所 | 每周一次 |
| **CCXT 库版本兼容** | 检查 CCXT 版本是否支持所有 4 个交易所的最新 API | `pip show ccxt` 版本 >= 4.0 | 每月一次 |

### 11.2 数据日期对齐验证

| 验证项 | 验证方法 | 处理方案 |
|-------|---------|---------|
| **Binance 日期标准** | 取 BTC 最新 3 天 klines，验证 `openTime` 为 UTC 00:00:00 的毫秒时间戳 | 若非 UTC 00:00，记录偏移量 |
| **CoinGecko 日期偏移** | 取 BTC 近 30 天 CoinGecko 收盘价，与 Binance Close 做交叉对比 | 计算最佳偏移量（0 天 or ±1 天），记录到 `data_integrity_log.json` |
| **日期偏移自动修正** | 如果检测到 CoinGecko 需要偏移 1 天，在读取市值数据时自动 shift | 代码中写死为可配置参数 `CG_DATE_OFFSET` |
| **周末/假期处理** | Binance 7×24 交易，无休市。CoinGecko 同理。但检查是否有某些代币在特定日期缺失数据 | 缺失天用前一天 forward-fill |

### 11.3 收盘价跨源一致性验证

| 验证项 | 验证方法 | 容差 |
|-------|---------|------|
| **交易所 Close vs CoinGecko Close** | 取 10 个主流代币（BTC, ETH, SOL, BNB, XRP, ADA, DOGE, AVAX, DOT, LINK），对比交易所 OHLCV Close 与 CoinGecko 收盘价近 30 天 | 差异 < 0.5% 为正常，> 1% 报警 |
| **跨交易所一致性** | 对同一代币（如 ETH），分别从 Binance 和 OKX 获取近 30 天 Close，对比 | 差异 < 0.1%（同为交易所数据，应高度一致） |
| **时区对齐确认** | 验证所有交易所的日线切割时间均为 UTC 00:00 | CCXT 统一处理，但需抽样验证 |
| **指标计算跨源影响** | 分别用 Binance 和 CoinGecko 收盘价计算 BTC 的 RSI(14)，对比差异 | RSI 差异 < 1 |

### 11.4 成交量数据验证

| 验证项 | 验证方法 | 预期 |
|-------|---------|------|
| **交易所成交量非零** | 检查每个代币近 30 天是否有 volume=0 的异常天 | 主流代币不应有 0 成交量 |
| **跨交易所成交量比较** | 对 BTC 分别取 Binance/OKX 成交量，验证量级一致 | 同一交易对在不同交易所的成交量可能不同，但日变化趋势应一致 |
| **VolumeSpike 合理性** | 计算 BTC 近 1 年的 vol_spike_3x 事件，手动核对是否对应已知事件（如 ETF 通过日） | 异动天应与已知市场事件对应 |
| **CoinGecko 兜底代币成交量** | 兜底代币使用 CoinGecko 聚合成交量，标注数据源不同 | 前端标注"聚合成交量"，评分中成交量指标正常参与 |

### 11.5 本地文件缓存验证

| 验证项 | 验证方法 | 预期 |
|-------|---------|------|
| **CSV 文件完整性** | 启动时检查每个 CSV：行数 > 0、无重复日期、日期单调递增、无 NaN 在关键列 | 全部通过 |
| **增量更新正确性** | 增量更新后，检查最后一行日期 = 昨日（UTC），且与 API 返回值一致 | 完全一致 |
| **文件锁/并发安全** | 在更新期间同时读取 CSV（模拟 API 请求），确保不会读到半写入状态 | 使用内存 DataFrame 提供服务，不直接读 CSV |
| **备份完整性** | 全量拉取后验证 backup 目录存在且文件数与原目录一致 | 一致 |
| **磁盘空间** | 检查 `local_data/` 目录总大小 | < 50MB |
| **损坏恢复** | 手动删除某个 CSV，重启后能自动重新拉取该代币数据 | 自动检测缺失并重拉 |

### 11.6 指标计算正确性验证

| 验证项 | 验证方法 | 容差 |
|-------|---------|------|
| **RSI(14) 与 TradingView 对比** | 取 BTC 最新 RSI 值，与 TradingView 网站手动对比 | 差异 < 1（因 Wilder 平滑的初始值处理可能略有不同） |
| **MACD(12,26,9) 对比** | 取 BTC 最新 MACD histogram，与 TradingView 对比 | 差异 < 0.1%（归一化值） |
| **BB(20,2) 对比** | 取 BTC 最新 BB 上轨/下轨/中轨，与 TradingView 对比 | 差异 < 0.01% |
| **KDJ(9,3,3) 对比** | 取 BTC 最新 K/D/J 值，与通达信或 TradingView 对比 | 差异 < 2（KDJ 初始值差异可能更大） |
| **金叉/死叉事件** | 在 BTC 近 1 年数据中找到所有 SMA(5,20) 金叉事件，手动在 TradingView 上核对 | 所有事件日期完全一致 |
| **与 notebook 输出对比** | 对 BTC 运行 `1_First_or_not_run___Tech_Fac_Price_Mcap_volumeData.ipynb` 最后一个单元格的 compute_features()，与 Dashboard 计算结果逐指标对比 | 差异 < 1e-6（浮点精度） |

### 11.7 评分与排名验证

| 验证项 | 验证方法 | 预期 |
|-------|---------|------|
| **趋势评分合理性** | 找到近期强势代币（如涨幅 Top 5），验证其趋势得分应在 80+ | 趋势得分 > 80 |
| **反转评分合理性** | 找到近期暴跌代币，验证其反转得分应较高 | 反转得分 > 70 |
| **横截面排名一致性** | 所有 200 个代币的趋势排名百分位应均匀分布在 0-100 | 分布接近均匀 |
| **时间序列排名** | 取 BTC 当前趋势得分，手动计算其在近 2 年历史中的百分位 | 与 API 返回值一致 |
| **极端情况** | 新上市代币（历史 < 2 年）的 2 年/3 年排名应标注为"数据不足" | 正确标注 |

### 11.8 前端交互验证

| 验证项 | 验证方法 |
|-------|---------|
| **代币切换** | 从 BTC 切换到 ETH，所有 12 个图表 + 评分 + 排名都应更新 |
| **参数修改** | 修改 MACD 从 (12,26,9) 到 (5,10,4)，图表应在 1 秒内刷新 |
| **图表时间轴同步** | 在主 K 线图缩放到近 30 天，所有子图同步 |
| **排名侧边栏** | 点击侧边栏中的 SOL，主视图切换到 SOL |
| **手动刷新** | 点击刷新，按钮显示旋转动画，完成后自动更新数据 |
| **首次启动体验** | 首次启动时显示"正在初始化数据..."进度，完成后正常显示 |
| **移动端** | Chrome DevTools 模拟 iPhone 12，验证单列布局和基本可用性 |

### 11.9 自动更新验证

| 验证项 | 验证方法 |
|-------|---------|
| **定时触发** | 将时间改为 1 分钟后，验证 APScheduler 能否准时触发 |
| **增量更新正确性** | 更新后检查 CSV 文件最后一行日期正确，且新数据与 API 一致 |
| **更新期间前端可用** | 在后台更新执行过程中访问前端，确认返回旧数据而非错误 |
| **更新完成后数据切换** | 更新完成后前端显示新日期的数据 |
| **连续多日更新** | 模拟连续 3 天的更新（手动触发 3 次），确认数据正确累积 |
| **异常恢复** | 在更新过程中模拟网络中断（断开 WiFi），重启后能否正常恢复 |

### 11.10 边界条件与异常处理验证

| 验证项 | 处理方案 |
|-------|---------|
| **交易所不可用代币** | 瀑布回退 Binance→OKX→Bybit→Gate.io→CoinGecko 兜底（约 5 个代币），KDJ 对兜底代币显示 N/A |
| **新代币入围 Top 200** | 自动创建 CSV 文件，全量拉取历史 |
| **代币退出 Top 200** | 保留数据但标记为 inactive，不再更新 |
| **代币改名/换 symbol** | 通过 CoinGecko ID（不变）识别，symbol 变化不影响 |
| **交易所交易对退市** | 检测到 CCXT 返回空数据，自动降级到下一个交易所（瀑布回退） |
| **闪崩/异常价格** | 检测日内振幅 > 50%，标记但不删除 |
| **API 限速错误(429)** | 指数退避重试，最多 3 次，间隔 2s/4s/8s |
| **API 超时** | 10 秒超时，重试 2 次 |
| **磁盘满** | 启动时检查可用空间 > 100MB，否则告警 |
| **进程意外退出** | launchd 的 KeepAlive 自动重启，启动时从本地文件恢复 |
