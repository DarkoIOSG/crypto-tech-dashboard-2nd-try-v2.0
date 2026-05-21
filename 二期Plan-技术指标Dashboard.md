# 二期 Plan — 技术指标 Dashboard（Phase 2 Plan）

> **状态**：定稿（待 ExitPlanMode 审批）
> **写于**：2026-05-14
> **当前 Git HEAD**：`814b530`（R7-8 fix retry path for failed_ids）
> **实施开始后此文件将另存为**：`crypto-tech-dashboard-2nd-try/二期Plan-技术指标Dashboard.md`
> **总条目数**：11 个改进项 + 3 个 R6/R7 carryover bug = 14 个 atomic 工作单元
> **预计周期**：4 周 × 4 phase（每 phase 末跑独立 audit）

---

# Part 0 — Context（为什么做二期）

一期（R1-R7）跑了 7 轮迭代，把 `PLAN_技术指标Dashboard.md` 的 §1-§11 核心需求落到代码层面：12 指标族 + 9+7 评分信号 + 2y/3y 时间序列百分位 + 数据层 + APScheduler 调度 + 浅色调色板 21 var + 移动端布局 + UX polish。Quant + System Engineer R7 verdict 是 `SHIP`，Artist + Aesthetician R7 verdict 是 `NEEDS-POLISH (49/65)`。

系统能 ship，但用户提出 **11 个改进方向 + 4 个角色视角**：

1. **评分体系不够"用户友好"**（item 1, 2, 9）— Trend/Reversal 双数字让用户困惑，缺综合判断
2. **数据广度不足**（item 7, 11）— 仅 crypto Top-200，缺美股；OHLCV 只到 2023-05-15，需到 2020-01-01
3. **数据本地化 + 可靠性**（item 10）— `main.py` 有 portability bug；增量写、损坏恢复
4. **市场基本面信息缺失**（item 5）— 没有市值排名、流动性、30 日均量
5. **视觉沉浸感**（item 3, 4, 8）— 没浅色模式、中文残留、tooltip 不够丰富
6. **指标可靠性透明度**（item 6）— 不知道某个指标历史回测是赚是赔

二期围绕这些需求展开，**全部按用户原话执行**。

---

# Part 1 — 用户原始 11 项需求（verbatim）

> 以下为用户在二期 prompt 中**原话引用**。我的解读和方案写在 Part 4，先把原文锁定为唯一来源。

### 用户原话 item 1 — 优化 Score 展示

> 目前的 Momentum（动量）Score 和 Reversal（反转）Score 让用户比较困惑。
> (a) 明确这两个 Score 的具体含义和优势。
> (b) 增加对比维度，展示当前代币在 Top 200 中的排名。
> (c) 在图表中增加计算逻辑的说明。

### 用户原话 item 2 — 建立综合评分体系

> 由于目前有 Momentum 和 Reversal 两个指标，用户难以得出综合判断。
> (a) 请站在专业量化研究员和金融分析师的角度，构思一个综合评分方案。
> (b) 考虑引入类似 Transformer 或相关算法，针对"可交易行为"进行评分。
> (c) 该评分应基于动量与反转的变化趋势优化而来。

### 用户原话 item 3 — 增加浅色模式

> 在系统右上角增加一个模式切换图标（如太阳/月亮标志），支持从暗黑模式切换到白色（浅色）页面。

### 用户原话 item 4 — 系统语言全英文版

> 目前系统仍留有一些中文内容，请将所有的汉语内容（包括指标名称、公共变量名等）全部改为英文，确保没有任何中文字符出现。

### 用户原话 item 5 — 增加代币市值与流动性数据

> 在系统中增加一个板块，方便查看代币的实时行情：
> (a) 市值排名与具体市值（Market Cap）。
> (b) 流动性（Liquidity）数据。
> (c) 30日平均成交量。

### 用户原话 item 6 — 指标可靠性（Robustness）分析

> 从分析师视角出发，分析当前指标在历史数据中的表现。
> (a) 针对关键的买入/卖出点（如金叉、死叉等策略）进行回测。
> (b) 评估如果完全按照该指标交易，在历史中是盈利还是亏损，从而判断其可靠性。

### 用户原话 item 7 — 增加美股票

> 现在系统只能支持两个股票，现在需要增加数量，特别是港美股。请你通过 Yahoo Finance 去调研一下这些股票的相关信息。
>
> Stock data was obtained from Yahoo Finance, providing coverage for 40 publicly traded cryptocurrency-related companies:
>
> `['ANY', 'APLD', 'ARBK', 'BIGG', 'BITF', 'BKKT', 'BLSH', 'BTBT', 'BTCS', 'BTDR', 'BTGO', 'BTM', 'CAN', 'CIFR', 'CLSK', 'COIN', 'CORZ', 'CRCL', 'DEFT', 'DMGGF', 'EBON', 'ETOR', 'EXOD', 'FIGR', 'FLD', 'GEMI', 'GLXY', 'GREE', 'HIVE', 'HOOD', 'HUT', 'IREN', 'MARA', 'MOGO', 'MSTR', 'NPPTF', 'RIOT', 'SMLR', 'VOYG', 'WULF']`

**澄清后约束**（Q5 + Q9）：港股暂缓；仅美股 40 只；默认登陆 token = `CRCL`。

### 用户原话 item 8 — PowerTile / Hover 状态完善

> 目前我发现有一些 PowerTile（或是 Hover 状态），鼠标放上去后显示的是问号，证明里面的详细信息没有补充。请你优化和完善一下这个地方。

### 用户原话 item 9 — Overall Score 综合面板

> 关于我刚才提到的综合评估体系。得出的 Overall Score 应该放在最上面，类似于 Momentum 和 Reversal 指标。它应该是一个综合面板的类型。

### 用户原话 item 10 — 数据本地化

> 绝大多数数据应该保存在本地文件夹。以港美股为例，如果已经获取到了最近的相关数据，首先要把数据备份到本地，之后采用增量写入的方式更新数据库，而不是每次都读取全部数据。否则一旦数据库损坏，稳健性会非常差。

### 用户原话 item 11 — 加密货币历史延伸

> 关于加密货币（如 Bitcoin）的数据。目前只能显示 2024 年（原文误读为 2025 年）以来的数据，没达到我的要求。
> 1. 目标：数据需要追溯到 2020 年 1 月 1 日。
> 2. 逻辑：
>    (a) 如果是 2020 年之后才出的代币，就从上市第一天开始获取。
>    (b) 如果是 2020 年之前就有的股票或代币，必须取到 2020 年 1 月 1 日。
> 3. 存储：检查所有数据源，确保数据存在当前文件夹下。我要做成"绿色化"或可移动的文件夹，方便复制到其他电脑上直接运行。
>
> 请你以架构师的身份，思考如何扩展日期并提高系统可靠性。默认显示的图表可以维持显示最近一年的 K 线。
>
> **修订（2026-05-15 用户直接指示）**：取消"默认 1 年"约束。默认 viewport 直接显示**全部历史**（2020-01-01 → today，对应老币；listing-day → today，对应新币）。`fitContent()` 一把展开，用户可自行缩放/平移到子区间。

### 用户提出的 4-tier 数据获取逻辑（在 Q10 答复中给的硬约束）

> 针对数据获取，请遵循以下逻辑：
> 1. 先按照 CCXT 进行极致的获取，拿到所有能获得的 OHLC 数据。
> 2. 如果获取不到，检查链上（On-chain）是否有可用的 OHLC 数据。
> 3. 如果链上也获取不到，你先去尝试抓取（扒取）数据。
> 4. 如果依然无法获取，就按照你第一个方案提到的逻辑，把之前的数据补齐。
>
> 另外，你需要进行标注：明确标注多长时间之后的数据才是正确的，这一点必须体现出来。

**澄清后**（Q13）：Tier 2（链上）和 Tier 3（抓取）跳过；只保留 Tier 1（CCXT 极致）+ Tier 4（CG close-only）。但 **per-token 数据质量边界元数据必须保留并在 UI 中暴露**（Q14 决策）。

---

# Part 2 — 16 个澄清问题 Q&A（verbatim）

> 这部分把用户每一个答复**原话录下**作为决策依据。

### Q1 — 综合评分 tier
**问**：Tier A 手工加权 / Tier B Ridge 回归 / Tier C ML / A 现做 B 留到下一冲刺，选哪个？
**用户答**：「A 和 B 都做吧，因为我不确定 B 能不能一口气做的效果很好」
**决策**：Tier A 在 Phase 2B 落地，Tier B 在 Phase 2D 落地，同 API 字段，前端 Toggle 切换。

### Q2 — Tooltip 风格
**问**：原生 title / 原生+局部 popover / 全自定义 popover，选哪个？
**用户答**：「原生 + 局部 popover（推荐折中）」
**决策**：12 panel header + 7 param label 用原生 title；16 Score Breakdown component row + Overall card 用 80 行轻量 popover（200ms 悬停延迟、悬停内部不消失、可选 "Methodology →" 链接）。

### Q3 — 浅色调色板气质
**问**：两层 off-white / 纯白 / 暖灰，选哪个？
**用户答**：「按照 tradingview 的白色做的方法，各种颜色搭配要非常高级」
**决策**：两层 off-white：canvas `#F0F3FA`（淡蓝灰）+ card `#FFFFFF`（纯白）。Accent 色调暗化以满足 WCAG AA：`--accent-green` 从 `#26a69a` 调到 `#089981`、`--accent-yellow` 从 `#f7c948` 调到 `#B8860B`（原值在白底不可读）。

### Q4 — Overall 卡布局
**问**：Strategy A 全宽 hero + 下方 2 列 / Strategy B 3 列等宽 / Strategy C 垂直 3 段，选哪个？
**用户答**：「Strategy A: 上方全宽 hero + 下方 2 列（推荐）」
**决策**：全宽 hero card 在上，下方保留现有 2 列 Trend + Reversal grid。Overall gauge 240px（比下方 170px 大 ~40%），大数字 56px（比下方 38px 大），左侧 2px `--accent-blue` accent border，标题加 9px uppercase `COMPOSITE` 微 badge。

### Q5 — 港股纳入二期？
**问**：5 只窄带 / 12 只中等 / 自定义？
**用户答**：「美股的范围，我发送给你了呀（40 只列表）。默认是 CRCL 吧」
**决策**：港股**暂缓 Phase 3**。Phase 2 仅美股 40 只。默认登陆 token = CRCL。

### Q6 — crypto + 股票混合排名还是分开？
**问**：彻底分开 / 混合 / 分开但保留 "All" tab？
**用户答**：「彻底分开（推荐）」
**决策**：crypto 200 和 stocks 40 各自独立 cross-section ranking。sidebar 两个 tab：`[Crypto (200)]` `[US Stocks (40)]`。tab 状态保存到 URL hash。

### Q7 — Overall 卡 breakdown 内容
**问**：6 个 sleeve / Top 6 contributor / 两个都做？
**用户答**：「6 个 sleeve（A 推荐，抽象）」
**决策**：Overall card 下方显示 6 个 sleeve + 各自加权贡献：Trend / Reversal / Signal Breadth / Risk / Trend TS 2y / Reversal TS 2y。

### Q8 — 11 项实施顺序
**问**：架构先行 / 用户价值先行 / 三路并行？
**用户答**：「架构先行（Plan B 推荐）」
**决策**：Phase 2A (10/11/5/7) → Phase 2B (2A/6/1) → Phase 2C (9/3/4/8 + R6/R7 carryover) → Phase 2D (2B + 最终验收)。

### Q9 — 港股 final 决策
**用户答**：「只要我和你说的那 40，我可能说错了，不要港股」
**决策**：与 Q5 一致。HK 完全跳过 Phase 2。

### Q10 — pre-2023 crypto 数据
**问**：close-only fallback / 严格主义 / 仅 Top-50 backfill？
**用户答**：「先用 ccxt 进行极致的获取，按照你第一个倾向的方案来处理多个交易所。你可以接受 close only，但在处理某个代币时，需要说明从什么时候开始。」+ 4-tier 数据获取逻辑。
**决策**：Tier 1 CCXT 极致 + Tier 4 CG close-only。每 token 写 `data_coverage.json` 元数据，UI 在评分区显示 "Data Coverage" 折叠。

### Q11 — 英化范围
**问**：仅用户可见 / 加后端 comments+log / 加 docs？
**用户答**：「包含后端代码注释 + log」
**决策**：所有 `.py` `.js` `.html` `.css` 中的中文翻为英文。docs（README/PLAN/任务交接指南）保持中文不动。commit history 也不重写。

### Q12 — 验收方式
**问**：每模块一轮 / 末尾一次 / 仅 smoke test？
**用户答**：「每个大模块完工后跳一轮验收（推荐）」
**决策**：4 轮 audit round（R8-α 数据架构师+系统工程师；R8-β quant+designer；R8-γ artist+analyst；R8-δ quant final）。

### Q13 — Tier 2/3 source
**问**：仅 Tier 1+4 / TheGraph / CMC / 全要？
**用户答**：「只要 Tier 1 (CCXT) + Tier 4 (CG close-only)，跳过链上和抓取」
**决策**：Phase 2 数据源只用 Tier 1 + Tier 4。但 CCXT 扩展到 8 个交易所（Binance / OKX / Bybit / Gate.io + Coinbase / Kraken / KuCoin / Bitstamp）实现"极致"。

### Q14 — 数据质量边界 UI
**问**：评分区折叠 / candle 虚线 / 两个都做 / 仅 API？
**用户答**：「额外一条 'Data Coverage' 小折序在评分区（推荐）」
**决策**：评分区 token-meta 下面加一行 "Data Coverage: Exchange OHLC from 2023-05-15 · Close-only history back to 2020-01-01 · KDJ/Volume valid from 2023-05-15"，点击展开显示 tier 分布表。

### Q15 — R6/R7 carryover bugs
**问**：全部修 / 只修移动端 drawer / 全部跳过？
**用户答**：「全部修复（推荐）」
**决策**：R6-7 移动端 drawer + R7-3 gauge 0/100 label 裁切 + R7-4 indicator panel 右价轴 chip 重叠，全部在 Phase 2C 修复。

### Q16 — Tier B 时机
**问**：Phase 2D / Phase 3 / 不做？
**用户答**：「Phase 2D 同期上（与 Plan agent A 建议一致）」
**决策**：与 Q1 一致。

---

# Part 3 — 三角色视角深入分析（用户要求 4）

## 3.1 金融分析师 + 量化研究员视角

### 当前评分系统的问题（用户原话 item 1 + 2）

Trend score 是 9 信号的 cross-sectional 百分位加权混合，Reversal score 是 7 信号的 cross-sectional 百分位加权混合。两者输出都是 0-100，让用户面对两个数字时无所适从：
- BTC 此刻 Trend=41.2，Reversal=55.0。**这是好还是坏？** 用户看不出来
- 没有"在 200 个 token 中排第几"的具体名次
- 没有公式说明，用户不知道 Trend 是 SMA/EMA/MACD/动量混合的、Reversal 是 RSI/KDJ/Bollinger/均值回归混合的

### 量化方案：Tier A 手工加权

**公式（finance-theory 先验权重，Liu/Tsyvinski 2021 + Russell/Engle 2010）**：

```
Overall = 0.40 · Trend (CS percentile)
        + 0.25 · Reversal (CS percentile)
        + 0.15 · Breadth (% of 9 trend signals > 0, CS percentile)
        + 0.10 · Risk (1 / vol_20d, CS percentile, low-vol = high score)
        + 0.10 · TS_Trend_2y · 0.5
        + 0.10 · TS_Reversal_2y · 0.5
```

**权重正当性**：
- Trend = 0.40：crypto 中 momentum 是最稳健 factor（Liu/Tsyvinski 2021 "Risks and Returns of Cryptocurrency"）
- Reversal = 0.25：真实但噪声大，crypto 反弹 25% 后继续跌的概率不低
- Breadth = 0.15：多信号一致性（Russell/Engle 协同性 discount）
- Risk = 0.10：惩罚高波动 moonshot（vol-adjusted return = Sharpe-like）
- TS 历史 = 0.10：捕捉"罕见 strength outlier"，长期看 BTC 2y 一直高位的 token 比刚冲起来的更可靠

**Walk-forward 验证**（accept gate）：

```
For each historical date in scores_history.csv:
  - Compute Tier A composite
  - Compute forward 5d / 10d / 20d return per token
  - Spearman rank correlation per horizon

Accept if: ρ(Overall, forward_5d_return) ≥ ρ((Trend+Reversal)/2, forward_5d_return) + 0.05
```

### 量化方案：Tier B Ridge 经验权重

**目标**：拿真历史数据驱动权重，回答"为什么 Trend 应该 40% 而不是 50%"。

**实现**：
- pooled panel Ridge with date-fixed effects
- 24 个月 train / 1 月 test / monthly rolling
- 16 个原子信号 CS percentile + 4 个 sleeve 都进特征
- 目标变量：每 token 每日前 5 日 log return
- `sklearn.linear_model.RidgeCV(alphas=[0.1, 1, 10, 100])`
- 12 折稳定性：若系数符号翻转就 drop

**接受准则**：Tier B holdout Spearman ρ ≥ Tier A baseline + 0.02。若不达，**接受失败、保留 Tier A 作 production**，UI 隐藏 Tier B Toggle。

### 量化方案：指标稳健性回测（item 6）

针对 9 个指标族每个设计一个 canonical 策略，跑 universe-wide backtest：

| 策略名 | 入场 | 退场 |
|---|---|---|
| `rsi_oversold_30_50` | RSI < 30 | RSI > 50 |
| `macd_signal_cross` | MACD line crosses signal up | crosses down |
| `kdj_oversold_cross` | K crosses D up while both < 20 | K crosses D down while both > 80 |
| `bollinger_lower_band` | close 触下轨 (pctb<0) | close 触中轨 (pctb=0.5) |
| `sma_golden_cross` | SMA(5) > SMA(20) | SMA(5) < SMA(20) |
| `ema_golden_cross` | EMA(5) > EMA(20) | EMA(5) < EMA(20) |
| `momentum_breakout` | 20d return > 0 | 20d return ≤ 0 |
| `zscore_reversion` | z-score < -2 | z-score > 0 |
| `price_appreciation` | 20d return > 10% AND vol_z > 2 | 5d return < 0 |

universe-wide 汇总 per strategy：
- median Sharpe
- mean Sharpe
- pct positive Sharpe
- worst case (Sharpe, cg_id)
- best case (Sharpe, cg_id)

**可靠性 badge 阈值（calibrated for crypto, BTC buy-hold Sharpe ≈ 1.1）**：
- **Reliable**：median Sharpe ≥ 0.5 AND ≥ 60% positive AND worst ≥ -1.0
- **Useable with caveats**：median Sharpe ∈ [0.2, 0.5) OR pct positive ∈ [50%, 60%)
- **Unreliable**：median Sharpe < 0.2 OR pct positive < 50%

### 量化方案：rank in universe 显示（item 1b）

`/api/scores/{id}` 添加：
- `rank_in_universe_trend: int (1..N)`
- `rank_in_universe_reversal: int (1..N)`
- `rank_in_universe_overall: int (1..N)`
- `universe_size: int`

UI 在每个 score-card 标题旁显示：`Rank 47 / 200`，hover 显示"Top 23.5% in 200-token universe today"。

### 量化方案：计算逻辑 explainer（item 1c）

新模块 `backend/scoring/explainers.py`：

```python
TREND_EXPLAINER = {
    "title": "Trend Score",
    "one_line": "Blended SMA / EMA / MACD / momentum signals, ranked cross-sectionally.",
    "formula_md": "Trend = equal-weighted mean of 9 signal percentiles, then rank-percentile across the 200-token universe.",
    "signal_table": [
        {"key": "mom_ret_10d", "label": "Momentum (10d)", "current": <value>, "weight": 1.0},
        {"key": "mom_ret_20d", "label": "Momentum (20d)", "current": <value>, "weight": 1.0},
        ...9 rows...
    ],
    "strengths": [
        "Captures persistent trends across multiple timeframes",
        "Robust against single-indicator failure",
        ...
    ],
    "weaknesses": [
        "Lags reversal points by ~5-10 days",
        "False signals in choppy markets",
        ...
    ],
    "interpretation": {
        "above_70": "Strong uptrend across most signals — momentum continuation likely.",
        "30_70": "Mixed signals — wait for confirmation.",
        "below_30": "Weak / downtrending — avoid long entries."
    }
}
```

新路由 `GET /api/scoring/explainer` 返回 Trend / Reversal / Overall 三个 explainer。前端点 `.info-mark` `?` 弹出 modal popover 展示 explainer + 当前 token 的 signal_table 实时数值。

---

## 3.2 系统架构师 + 数据科学家视角

### 数据层架构（item 10 + 11）

**当前问题**（Plan agent B 调研发现）：
- `backend/main.py:57` 硬编码 `LocalStore(Path(PROJECT_ROOT) / "local_data")`，**忽略** `.env` 的 `DATA_DIR` 变量。这是"绿色化"的前置 bug（P0 portability）
- 所有 200 个 OHLCV CSV earliest date 都是 2023-05-15（一期 `HISTORY_DAYS=1095`）
- `top200_current.csv` 只有 5 列，没 market_cap_rank / total_volume / liquidity proxy
- 没 yfinance 集成，stocks 完全空白
- 没 boot-time 完整性校验，损坏 CSV 不会被检测

**4-tier waterfall 实现**（用户 Q10 + Q13 决策后）：

```
Tier 1: CCXT 8-exchange waterfall
  Binance → OKX → Bybit → Gate.io → Coinbase → Kraken → KuCoin → Bitstamp
  per-call pagination via since= cursor (cap 4000 days)
  最大化 OHLC 覆盖

Tier 2: skip
Tier 3: skip

Tier 4: CoinGecko close-only fallback
  /coins/{id}/market_chart/range — single-shot full range
  fill O=H=L=Close, volume=0, source="coingecko"
  KDJ / Volume Spike 自动 NaN-guard
```

**Per-token data coverage 元数据**（用户要求 item 11.3 + Q14）：

新文件 `local_data/metadata/data_coverage.json`：

```json
{
  "bitcoin": {
    "earliest_date": "2017-01-01",
    "latest_date": "2026-05-13",
    "listing_date": "2009-01-09",
    "real_ohlc_from": "2017-08-15",
    "close_only_windows": [],
    "tier_breakdown": [
      {"from": "2017-08-15", "to": "2021-12-31", "tier": 1, "source": "binance", "rows": 1599},
      {"from": "2022-01-01", "to": "2023-05-14", "tier": 1, "source": "okx", "rows": 499},
      {"from": "2023-05-15", "to": "2026-05-13", "tier": 1, "source": "okx", "rows": 1095}
    ]
  },
  "spiko-amundi-overnight-swap-fund-eur": {
    "earliest_date": "2024-03-21",
    "latest_date": "2026-05-13",
    "listing_date": "2024-03-21",
    "real_ohlc_from": null,
    "close_only_windows": [["2024-03-21", "2026-05-13"]],
    "tier_breakdown": [
      {"from": "2024-03-21", "to": "2026-05-13", "tier": 4, "source": "coingecko", "rows": 783}
    ]
  }
}
```

新 API：`GET /api/data-coverage/{cg_id}` 返回单 token 的 coverage 信息。

### Stocks 集成架构（item 7）

**Option 3（最轻量，Plan agent B 推荐 + Q6 决策）**：

- `local_data/metadata/stocks_universe.csv`：40 行 US tickers + `asset_class` 字段
- `backend/data/yfinance_client.py`：mirror coingecko_client 接口
  ```python
  class YFinanceClient:
      def fetch_universe_metadata(tickers) -> pd.DataFrame
      def fetch_ohlcv(ticker, start, end) -> Optional[pd.DataFrame]
      def fetch_market_overview(ticker) -> dict
  ```
- 用 `yf.Ticker(ticker).history(auto_adjust=True, actions=False)`，`auto_adjust=True` 折叠 splits + dividends
- 列 rename `Open/High/Low/Close/Volume` → `open/high/low/close/volume`，timezone `America/New_York`
- `source = "yfinance"`
- 跨 asset_class **彻底分开** ranking（Q6 决策）：`cross_sectional_percentile` 按 `asset_class` 分区
- `_validators.validate_cg_id` 正则扩展允许 A-Z + `.`（保留 `..` / `/` 拒绝）

**Stocks daily refresh 时序**：crypto 08:30 Asia/Shanghai 后 5 分钟（08:35）启动 stocks job。yfinance 周末 + 美股节假日跳过，但当日数据要等美股收盘后 ~3 小时（即 04:00 next day Asia/Shanghai），所以 08:35 拉的数据已经是 T-1 的完整数据，这个时序刚好。

### "绿色化"打包架构（item 10）

**修复 + 增强**：
1. **修 `backend/main.py:57`**：`LocalStore(DATA_DIR)` 替代硬编码
2. **新增 `backend/data/integrity.py`**：boot 时校验每个 OHLCV CSV（详见 Part 4）
3. **新增 `backend/data/quarantine/`**：损坏 CSV 自动移这里，不删
4. **新增 `Fetcher.repair_token(cg_id)`** + `POST /api/admin/repair/{id}`（仅 127.0.0.1）
5. **新增 `scripts/pack_green_folder.sh`**：
   ```bash
   zip -r dashboard_green_$(date +%Y%m%d).zip . \
     -x "venv/*" "*/__pycache__/*" "local_data/ohlcv_backup_*/*" \
        ".git/*" "*.pyc" "scripts/*.log"
   ```
6. **`.env` 政策**：ship `.env` 但 `COINGECKO_API_KEY` 改占位符；README 提示新机器要轮换 key
7. **依赖**：`requirements.txt` 加 `yfinance==0.2.40`（用户决策包 fish 这一项）

### 历史延伸架构（item 11）

- `.env` 设 `HISTORY_DAYS=2326`（today 2026-05-14 到 2020-01-01）
- 不全量重拉，**APPEND-EXTEND** 策略：
  ```python
  def run_history_extension(target_start_date="2020-01-01"):
      for cg_id in store.list_ohlcv_ids():
          existing = store.read_ohlcv(cg_id)
          existing_start = existing['date'].min()
          if existing_start <= target_start_date:
              continue
          # 拉 target_start_date → existing_start - 1day via CCXT waterfall
          new_rows, tier_used = exchange_client.fetch_ohlcv_waterfall(...)
          if new_rows is None:
              new_rows = coingecko_client.fetch_close_price_history(...)  # Tier 4
          snapshot_ohlcv_backup(cg_id)  # safe rollback
          store.append_ohlcv(cg_id, new_rows)  # dedup-by-date
          write_data_coverage_entry(cg_id, tier_used)
  ```
- 总运行时间预估：200 token × 平均 800 个新 bar/token = ~6-10 min
- 磁盘：9.5 MB → ~20 MB OHLCV（acceptable）
- **scores_history 不 backfill**：保持当前 2023-06 起点；3y 窗口 2026-06 自然满足

### 增量写入机制（user item 10 要求）

存量已实现：`backend/data/local_store.py:150-187` 的 `append_ohlcv` 用 `pd.concat` + `drop_duplicates(subset=['date'], keep='last')` + atomic rename。Phase 2 仅需扩展到 stocks。`yfinance_client.fetch_ohlcv` 返回 DataFrame 后走同一 `store.append_ohlcv` 路径，零额外架构。

---

## 3.3 艺术美学设计师视角

### 浅色模式调色板（item 3 + Q3 "TradingView 白色高级风"）

**21 个 light CSS var**（已审 WCAG AA 对比度）：

```css
html[data-theme="light"] {
    /* 两层 off-white（用户 Q3 决策） */
    --bg-primary:    #F0F3FA;  /* canvas 淡蓝灰 */
    --bg-secondary:  #FFFFFF;  /* card 纯白 */
    --bg-tertiary:   #F7F8FA;  /* input/button rest */
    --bg-elevated:   #E0E3EB;  /* hover */

    /* 文字（near-black 而非 #000 — 更软） */
    --text-primary:   #131722;  /* AA 16:1 on white */
    --text-secondary: #50565E;
    --text-muted:     #9098A4;

    /* Accent — 暗化以保证白底 AA 对比度 */
    --accent-green:  #089981;  /* TV light buy — was #26a69a, too light on white */
    --accent-red:    #F23645;
    --accent-blue:   #2962FF;
    --accent-yellow: #B8860B;  /* 暗金 — #f7c948 在白底不可读 */
    --accent-purple: #9C27B0;

    /* 边框 */
    --border-primary: #D6DCE5;
    --border-subtle:  #E8ECF2;

    /* Chart-specific */
    --chart-candle-up:    #089981;
    --chart-candle-down:  #F23645;
    --chart-volume:       #B0B6C0;
    --chart-volume-spike: #B8860B;
    --chart-ma-fast:      #1565C0;
    --chart-ma-slow:      #EF6C00;
    --chart-bb-fill:      rgba(33, 150, 243, 0.07);
}
```

**主题切换机制**：
- `<html data-theme="dark" | "light">` 属性，CSS 用 `html[data-theme="light"] { ... }`
- 内联 `<script>` 在 `<head>` 顶部（stylesheet 加载前）解析 localStorage → prefers-color-scheme → fallback "dark"，**避免 flash-of-wrong-theme**
- 监听 `matchMedia('change')`，仅在 localStorage 无值时响应
- Toggle 按钮：32×32 icon-only ghost button，放 Refresh 左侧
- 双 SVG（sun + moon），CSS 控制显示哪个："display destination state"（dark 模式显示 sun = "切到 light"）
- 200ms cross-fade 过渡：`transition: background-color 200ms ease, color 200ms ease`

**Charts 重新 tint 不重建**（保留 zoom 状态）：
- 每个 chart 模块加 `readPalette()` helper 读 CSS var
- 加 `retint()` 公有方法，调 `chart.applyOptions(...)` + 每个 `series.applyOptions(...)`
- theme toggle 时 app.js 调 `Candle.retint()` + `IndicatorPanels.retint(family)` x12
- SVG 模块（score_gauge / sparkline）缓存 `__lastValue` 然后 re-render

### Overall hero panel 设计（item 9 + Q4 + Q7）

**Strategy A（用户 Q4 选）**：

```
┌──────────────────────────────────────────────────────┐
│  OVERALL · COMPOSITE   [?]    Rank 12 / 200          │
│                                                       │
│  ╭───────────╮   76.2       ▲ MACD Histogram +0.74  │
│  │ 240px     │   Composite  ▲ MA50 Slope    +0.61   │
│  │ gauge     │   Score      ▼ RSI Turn      -0.21   │
│  │ (40% bigger)│             "Strong trend setup"   │
│  ╰───────────╯                                       │
│                                                       │
│  Trend          72 × 0.40 = 28.8                     │
│  Reversal       41 × 0.25 = 10.3                     │
│  Signal Breadth 67 × 0.15 = 10.1                     │
│  Risk (low vol) 55 × 0.10 =  5.5                     │
│  Trend TS 2y    83 × 0.05 =  4.2                     │
│  Reversal TS 2y 58 × 0.05 =  2.9                     │
│  ───────────────────────────────                     │
│  Overall                     61.8                    │
└──────────────────────────────────────────────────────┘
┌──────────────────────┐  ┌──────────────────────┐
│ TREND   72.0  Rank 18│  │ REVERSAL  41.0  Rank85│
│ ╭──gauge──╮          │  │ ╭──gauge──╮           │
│ ╰─────────╯          │  │ ╰─────────╯           │
│ 9 components rows    │  │ 7 components rows     │
└──────────────────────┘  └──────────────────────┘
```

**视觉区分层级（subtle to bold）**：
1. **文档顺序 + 全宽**：最弱也最有效
2. **2px `--accent-blue` 左侧 accent border**：不抢戏
3. **`COMPOSITE` 9px uppercase pill**：明示"这是合成出来的"
4. **240px gauge + 56px score**：尺寸即层级
5. **Rank chip in title bar**：每张卡都有，统一视觉语言

**Blurb 4-quadrant 文本**：
- Trend ≥ 66 AND Reversal < 33: "Strong bull setup"
- Trend < 33 AND Reversal ≥ 66: "Oversold rebound candidate"
- Trend ≥ 66 AND Reversal ≥ 66: "Conflicted — bullish trend with oversold reversal"
- Trend < 33 AND Reversal < 33: "Weak across the board"
- else: "Mixed signals"

### 16 个英文 label 翻译表（item 4 + Q11）

**注意：这个翻译表修了一个一期遗留 collision bug**——原版 `ma50_dev`（Trend）和 `ma50_dev_z_40`（Reversal）都翻为"MA50 偏离"，用户分不清。英文版区分为 "MA50 Deviation" 和 "MA50 Deviation Z (40)"。

| Key（不变） | 当前 zh | EN 译文 |
|---|---|---|
| `mom_ret_10d` | 动量 10d | **Momentum (10d)** |
| `mom_ret_20d` | 动量 20d | **Momentum (20d)** |
| `macd_hist_12_26_9` | MACD 柱 | **MACD Histogram** |
| `macd_hist_slope5_12_26_9` | MACD 斜率 | **MACD Histogram Slope (5d)** |
| `sma_cross_strength_signed_5_20` | SMA 金叉 | **SMA Cross Strength (5/20)** |
| `ema_cross_strength_signed_5_20` | EMA 金叉 | **EMA Cross Strength (5/20)** |
| `ma50_slope_20d` | MA50 斜率 | **MA50 Slope (20d)** |
| `ma50_dev` | MA50 偏离 | **MA50 Deviation** |
| `bb_pctb_20` | 布林位置 | **Bollinger %B (20)** |
| `rsi_dist_os_14` | RSI 超卖 | **RSI Oversold Distance (14)** |
| `rsi_turn_event_14` | RSI 反转事件 | **RSI Turn Event (14)** |
| `kdj_os_distance` | KDJ 超卖 | **KDJ Oversold Distance** |
| `bb_z_20` | 布林 Z(取反) | **Bollinger Z-Score (inverted, 20)** |
| `mr_z_40_skip16` | 均值回归 | **Mean Reversion Z (40, skip 16)** |
| `ma50_dev_z_40` | MA50 偏离 | **MA50 Deviation Z (40)** |
| `mom_ret_5d` | 负动量 5d | **Negative Momentum (5d)** |

### Tooltip 富化全表（item 8 + Q2）

**12 个 panel header tooltip（原生 title）**：

| Panel | Tooltip |
|---|---|
| SMA Cross (5/20) | Simple Moving Average crossover. When the fast SMA crosses above the slow SMA, momentum is shifting upward (golden cross); a downside cross marks a death cross. |
| MACD (12,26,9) | Moving Average Convergence/Divergence. Histogram = (fast EMA − slow EMA) − signal EMA. Positive and rising = bullish acceleration; falling toward zero = momentum cooling. |
| RSI (14) | Relative Strength Index. 0–100 scale using Wilder smoothing of average gains vs losses. Readings <30 historically mark oversold conditions, >70 overbought. |
| Bollinger (20, 2σ) | Price envelope of mean ± 2 standard deviations over 20 bars. %B near 1 = near upper band (stretched); near 0 = near lower band (mean-reversion candidate). |
| Volume Spike (14) | Ratio of today's volume to its 14-day moving average. Values ≥2× often accompany breakouts or capitulation; volume-confirmed moves tend to follow through. |
| Momentum (5/10/20/30d) | Log returns over four lookbacks. Cross-sectionally ranked. Aligned positive readings across timeframes = persistent uptrend; mixed signs = chop. |
| EMA Cross (5/20) | Exponential Moving Average crossover. EMAs weight recent prices more heavily than SMAs, so the cross fires earlier — sometimes too early in choppy regimes. |
| RSI Mean Reversion (14) | Distance from RSI 30 (oversold). Positive when RSI <30; zero otherwise. Standalone reversal signal — best confirmed by a turn event or %B re-entry. |
| KDJ (9,3,3) | Stochastic K/D/J lines. K below 20 and turning up = oversold reversal candidate; J line amplifies K to surface extremes earlier. |
| Mean Reversion (40, skip 16) | Z-score of price vs its trailing 40-day mean, skipping the most recent 16 days to avoid contaminating with the same window we're trading. Negative = below mean. |
| Z-Score vs MA50 | Standardized distance of price from its 50-day moving average. ±2σ historically marks stretched conditions worth watching for snapbacks. |
| Price Appreciation (10d/20d) | Raw price change percentages over two lookbacks. Provides absolute-return context alongside the cross-sectionally ranked momentum signal. |

**16 个 Score Breakdown component tooltip（用 popover）**：

| Row label | Tooltip |
|---|---|
| Momentum (10d) | 10-day log return, ranked cross-sectionally to 0–100 within today's universe. Higher = stronger recent uptrend vs peers. |
| Momentum (20d) | 20-day log return, cross-sectionally ranked. Confirms whether the 10d move is a continuation or a one-off pop. |
| MACD Histogram | MACD(12,26,9) histogram value, cross-sectionally ranked. Positive and growing = bullish acceleration. |
| MACD Histogram Slope (5d) | Slope of the MACD histogram over the last 5 bars. Captures acceleration of acceleration — turns sign before the histogram itself does. |
| SMA Cross Strength (5/20) | Signed normalized gap between fast and slow SMA. Positive = fast above slow (golden-cross regime); magnitude scales the rank. |
| EMA Cross Strength (5/20) | Same as SMA cross but with EMAs — reacts faster to recent prices. |
| MA50 Slope (20d) | Slope of the 50-day moving average over the last 20 days. Positive = the medium-term trend is curving upward. |
| MA50 Deviation | Percentage distance of price above its 50-day MA. Positive in uptrends; very high can presage exhaustion. |
| Bollinger %B (20) | Where price sits within its 20-day Bollinger band. 1.0 = upper band, 0.5 = mean, 0.0 = lower band. |
| RSI Oversold Distance (14) | How far RSI is below the 30 oversold threshold. Larger = more deeply oversold = stronger reversal-candidate. |
| RSI Turn Event (14) | Captures the moment RSI re-crosses 30 from below. Discrete bullish reversal trigger. |
| KDJ Oversold Distance | Stochastic K distance below 20. Larger = more oversold on a higher-volatility-aware scale than RSI. |
| Bollinger Z-Score (inverted, 20) | Standardized %B with sign flipped so that "near lower band" produces a high reversal score. |
| Mean Reversion Z (40, skip 16) | Z-score of price vs its trailing 40-day mean, skipping the most recent 16 days to avoid lookback contamination. Very negative = stretched below mean. |
| MA50 Deviation Z (40) | Z-score of the MA50 deviation series over a 40-day window. Detects when "% above MA50" is itself stretched. |
| Negative Momentum (5d) | Inverted 5-day return. High values indicate recent weakness, which the reversal model treats as a setup for a snapback. |

**Overall info-mark tooltip**:
> Composite of Trend and Reversal weighted by finance-theory priors: 40% Trend + 25% Reversal + 15% signal breadth + 10% risk-adjustment + 10% 2y historical strength. Cross-sectionally ranked to 0-100.

**7 个参数 label tooltip（原生 title）**：

| Label | Tooltip |
|---|---|
| period | Lookback window in bars (days). |
| fast / slow | Number of bars used in the faster/slower moving average. Smaller fast = more sensitive but more whipsaws. |
| signal | Smoothing window applied to MACD line to compute the signal line. |
| N | KDJ: stochastic window. |
| M1 | KDJ: K-line smoothing factor. |
| M2 | KDJ: D-line smoothing factor. |
| std | Number of standard deviations for the Bollinger band width. |
| window / ma_window | Number of bars in the volume moving average baseline. |

---

# Part 4 — 11 项详细方案（含 file:line touchpoint + acceptance）

> 这部分把每一项的 why / what / where / how / acceptance 全部展开。每项都按这个模板：
>
> ```
> ### R8-N · 用户 item X
> **用户原话**: ...
> **why**: ...
> **what**: 改动列表
> **where**: 文件 + 行号
> **how**: 实现要点
> **acceptance**: 可逐项核对的验收标准
> ```

## Phase 2A — 基础设施 + 数据扩展（Week 1）

### R8-1A · 用户 item 10（绿色化 + 增量 + 损坏恢复）

**用户原话**："绝大多数数据应该保存在本地文件夹...首先要把数据备份到本地，之后采用增量写入的方式...否则一旦数据库损坏，稳健性会非常差。"

**why**: Plan agent B 发现 `backend/main.py:57` 硬编码忽略 `DATA_DIR`，是"绿色化"前置 P0 bug；缺 boot-time 完整性校验；缺 per-token 修复路径。

**what**:
1. 修 portability bug
2. 加 boot-time 完整性校验
3. 加单 token 修复机制
4. 加打包脚本

**where + how**:

- `backend/main.py:57`：把 `LocalStore(Path(PROJECT_ROOT) / "local_data")` 改为 `LocalStore(DATA_DIR)`（`DATA_DIR` 已经在 `config.py:74-79` 解析过相对/绝对路径）

- 新文件 `backend/data/integrity.py`：
  ```python
  def verify_local_data_integrity(store, validator) -> dict:
      """boot-time check, returns per-token issue list"""
      issues = []
      for cg_id in store.list_ohlcv_ids():
          path = OHLCV_DIR / f"{cg_id}.csv"
          # 1. file size > 0
          if path.stat().st_size == 0:
              issues.append((cg_id, "empty_file"))
              continue
          # 2. header equals OHLCV_COLUMNS
          # 3. pd.read_csv succeeds
          # 4. row count >= MIN_OHLCV_ROWS
          # 5. last_date within 14 days for active tokens
          # 6. validate_ohlcv issues empty
          ...
      return issues
  ```

- 新目录 `local_data/quarantine/`：损坏 CSV 移这里（`shutil.move`），不删

- `backend/data/fetcher.py` 新方法 `repair_token(cg_id)`：调 `fetch_ohlcv_waterfall` + `fetch_close_price_history` 重拉单 token，atomic 写回

- 新路由 `backend/api/routes_admin.py` `POST /api/admin/repair/{id}`：localhost-only check（`request.client.host == "127.0.0.1"`）

- `backend/main.py` lifespan：boot 调 `verify_local_data_integrity`，log 输出 issues，但**不自动 repair**（防 .env 出错触发 200 API calls）

- 新脚本 `scripts/pack_green_folder.sh`：
  ```bash
  #!/bin/bash
  set -e
  cd "$(dirname "$0")/.."
  out="dashboard_green_$(date +%Y%m%d).zip"
  cp .env .env.bak
  sed -i.tmp 's/^COINGECKO_API_KEY=.*/COINGECKO_API_KEY=your-coingecko-pro-key-here/' .env
  zip -r "$out" . \
    -x "venv/*" "*/__pycache__/*" "local_data/ohlcv_backup_*/*" \
       ".git/*" "*.pyc" "scripts/*.log" "*.tmp"
  mv .env.bak .env
  rm -f .env.tmp
  echo "Wrote $out ($(du -h $out | cut -f1))"
  ```

- `README.md` 加"移植到另一台电脑"小节

**acceptance**:
- [ ] `.env` 设 `DATA_DIR=/tmp/test_dash`，fetcher 写、API 读都在 `/tmp/test_dash`
- [ ] `echo "garbage" > local_data/ohlcv/bitcoin.csv` 后 boot，log 标注该文件 quarantine
- [ ] `curl -X POST http://127.0.0.1:8080/api/admin/repair/bitcoin` 单 token 修复成功
- [ ] `curl -X POST http://example.com/api/admin/repair/bitcoin` 拒绝（不是 127.0.0.1）
- [ ] `bash scripts/pack_green_folder.sh` 生成 `dashboard_green_YYYYMMDD.zip`，解压到新机器 `setup.sh && run.sh` 即可
- [ ] `local_data/metadata/data_integrity_log.json` 每次 boot 更新

---

### R8-1B · 用户 item 11（OHLCV 史延伸到 2020-01-01）

**用户原话**："数据需要追溯到 2020 年 1 月 1 日。如果是 2020 年之后才出的代币，就从上市第一天开始获取。如果是 2020 年之前就有的股票或代币，必须取到 2020 年 1 月 1 日。"

**why**: 一期所有 200 个 CSV earliest 2023-05-15（HISTORY_DAYS=1095）。用户要求 BTC 这种老 token 必须能拿到 2020-01-01。

**what**:
1. 扩展 CCXT 到 8 个交易所（"极致"获取）
2. 添加 `run_history_extension` 方法 append-prepend
3. 写 per-token data_coverage.json 元数据
4. 新 endpoint 暴露 coverage

**where + how**:

- `.env`：`HISTORY_DAYS=2326`
- `backend/data/exchange_client.py`：
  - `EXCHANGE_PRIORITY` 扩展到 8 个：`["binance", "okx", "bybit", "gateio", "coinbase", "kraken", "kucoin", "bitstamp"]`
  - `PER_CALL_LIMIT` 字典加 Coinbase=300、Kraken=720、KuCoin=1500、Bitstamp=1000
  - 分页 since= cursor 已支持 4000 天上限，无结构变化
- `backend/data/fetcher.py` 新方法：
  ```python
  def run_history_extension(self, target_start_date="2020-01-01") -> dict:
      """For each existing token, prepend OHLCV back to target_start_date.
      Returns summary with extended_tokens / tier_used / failed."""
      from datetime import datetime, timedelta
      summary = {"extended": 0, "skipped": 0, "failed": [], "tier_breakdown": {}}
      target_dt = datetime.strptime(target_start_date, "%Y-%m-%d")
      for cg_id in self.store.list_ohlcv_ids():
          existing = self.store.read_ohlcv(cg_id)
          if existing is None or len(existing) == 0:
              continue
          existing_start = existing['date'].min()
          if existing_start <= target_dt:
              summary["skipped"] += 1
              continue
          # snapshot before mutation
          self.store.snapshot_ohlcv_backup(cg_id)
          # Tier 1: CCXT waterfall (8 exchanges)
          new_df, source = self.exchange_client.fetch_ohlcv_waterfall(
              cg_id=cg_id,
              days=(existing_start - target_dt).days,
              mapper=self.mapper,
              end_date=existing_start - timedelta(days=1),
          )
          tier = 1
          if new_df is None or new_df.empty:
              # Tier 4: CG close-only
              new_df = self.coingecko_client.fetch_close_price_history(
                  cg_id=cg_id,
                  from_date=target_dt,
                  to_date=existing_start - timedelta(days=1),
              )
              if new_df is not None and not new_df.empty:
                  new_df = _coingecko_close_to_ohlcv(new_df)
                  new_df["source"] = COINGECKO_SOURCE_TAG
                  source = "coingecko"
                  tier = 4
          if new_df is not None and not new_df.empty:
              self.store.append_ohlcv(cg_id, new_df)
              summary["extended"] += 1
              summary["tier_breakdown"].setdefault(tier, []).append(cg_id)
              self._update_data_coverage(cg_id, source=source, tier=tier)
          else:
              summary["failed"].append(cg_id)
      return summary
  ```
- 新文件 `local_data/metadata/data_coverage.json`（schema 见 Part 3.2）
- 新路由 `backend/api/routes_market.py`（与 R8-2A 共用文件）`GET /api/data-coverage/{cg_id}`
- `scores_history.csv` **不 backfill**：保持 2023-06 起点（Plan B 建议；2y 窗口当前已满足，3y 窗口 2026-06 自然满足）
- 新脚本 `scripts/run_history_extension.py` one-shot 执行
- **默认 candle chart 显示全部历史** (2026-05-15 修订)：`frontend/js/app.js renderCandle` 改为 `getOhlc(id, 2326)` 拉全部 2020→today；`timeScale().fitContent()` 一把展开。renderAllIndicators 同步改为 days=2326，保持时间轴对齐。原"默认 1 年"约束已取消（用户直接指示）。

**acceptance**:
- [ ] BTC `local_data/ohlcv/bitcoin.csv` 第一行 `date <= 2020-01-01`（实际应该是 2017 年代 OKX 数据）
- [ ] SOL `local_data/ohlcv/solana.csv` 第一行 `date >= 2020-04-XX`（其 OKX listing 日期）
- [ ] SUI `local_data/ohlcv/sui.csv` 第一行 `date >= 2023-05-XX`（其 listing 日期；2023 后 listing 的 token 维持 listing day 起）
- [ ] `data_coverage.json` 每个 token 有 `tier_breakdown` 数组
- [ ] `GET /api/data-coverage/bitcoin` 200，返回 tier_breakdown
- [ ] `scores_history.csv` 行数不变（不 backfill）
- [ ] 默认 candle chart 1440 viewport 显示全部历史（fitContent 展开 2020→today）
- [ ] 总运行时间 ≤ 15 分钟（一次性 history extension job）

---

### R8-1C · 用户 item 5（市值 + 流动性 + 30d 均量面板）

**用户原话**："增加一个板块，方便查看代币的实时行情：(a) 市值排名与具体市值。(b) 流动性数据。(c) 30日平均成交量。"

**why**: 一期 `top200_current.csv` 只有 5 列，缺 mcap_rank / total_volume / liquidity proxy。CG `/coins/markets` 端点本来就返回这些，一期没解析。

**what**:
1. 扩展 CG 字段提取
2. top200_current schema 升级
3. 新 endpoint `/api/market_overview/{id}`
4. 前端新增 market panel

**where + how**:

- `backend/data/coingecko_client.py:276-290`：`expected` 字段列表扩展：
  ```python
  expected = [
      "id", "symbol", "name", "current_price", "market_cap",
      # New columns
      "market_cap_rank", "fully_diluted_valuation", "total_volume",
      "circulating_supply", "total_supply", "max_supply",
      "price_change_percentage_24h",
  ]
  ```
- `backend/data/data_validator.py:27-33`：`TOP200_REQUIRED_COLUMNS` 扩展加 `market_cap_rank` + `total_volume`
- 新方法 `DataService.avg_volume_30d(cg_id) -> Optional[float]`：
  ```python
  def avg_volume_30d(self, cg_id: str) -> Optional[float]:
      df = self.get_ohlcv(cg_id)
      if df is None or len(df) == 0:
          return None
      tail = df.tail(30)
      # if majority source=coingecko, vol is fake (zero-filled), return None
      if "source" in tail.columns:
          fallback_pct = (tail["source"] == "coingecko").mean()
          if fallback_pct >= 0.5:
              return None
      return float(tail["volume"].mean())
  ```
- 新 router `backend/api/routes_market.py`:
  ```python
  @router.get("/api/market_overview/{cg_id}")
  def market_overview(cg_id: str):
      cg_id = validate_cg_id(cg_id)
      svc = get_service()
      token = svc.get_token(cg_id)
      if token is None:
          raise HTTPException(404, f"unknown token {cg_id}")
      df = svc.get_ohlcv(cg_id)
      source = str(df['source'].iloc[-1]) if df is not None else None
      pair = svc.get_symbol_mapping(cg_id, source) if source else None
      return {
          "cg_id": cg_id,
          "market_cap": token.get("mcap"),
          "market_cap_rank": token.get("market_cap_rank"),
          "fully_diluted_valuation": token.get("fdv"),
          "current_price": token.get("price"),
          "price_change_24h_pct": token.get("price_change_percentage_24h"),
          "total_volume_24h": token.get("total_volume"),
          "avg_volume_30d": svc.avg_volume_30d(cg_id),
          "circulating_supply": token.get("circulating_supply"),
          "total_supply": token.get("total_supply"),
          "liquidity": {
              "exchange": source,
              "spot_pair": pair,
              "source_tag": source,
          }
      }
  ```
- 前端 `frontend/index.html` 在 token-selector 和 score-detail 之间插入：
  ```html
  <section id="market-cap-panel" class="market-panel">
    <div class="market-tile" data-field="market_cap_rank">
      <div class="market-tile-label">Mcap Rank</div>
      <div class="market-tile-value" id="mcap-rank">#--</div>
    </div>
    <div class="market-tile" data-field="market_cap">
      <div class="market-tile-label">Market Cap</div>
      <div class="market-tile-value" id="mcap-value">$--</div>
    </div>
    <div class="market-tile" data-field="total_volume_24h">
      <div class="market-tile-label">24h Volume</div>
      <div class="market-tile-value" id="vol-24h">$--</div>
    </div>
    <div class="market-tile" data-field="avg_volume_30d">
      <div class="market-tile-label">30d Avg Volume</div>
      <div class="market-tile-value" id="vol-30d">$--</div>
    </div>
    <div class="market-tile" data-field="liquidity">
      <div class="market-tile-label">Liquidity</div>
      <div class="market-tile-value" id="liquidity-source">--</div>
    </div>
  </section>
  ```
- 新组件 `frontend/js/components/market_panel.js`（~50 行）调 `/api/market_overview/{id}` 渲染 tiles，format with `Intl.NumberFormat`（$1.42T / $79K / 2.85B 等）
- 新 CSS rules in `styles.css` 给 `.market-panel` + `.market-tile`
- `frontend/js/api.js` 加 `getMarketOverview(id)` 方法
- `frontend/js/app.js` selectToken flow 加 `await MarketPanel.render(id)`

**acceptance**:
- [ ] `top200_current.csv` 至少 12 列
- [ ] `GET /api/market_overview/bitcoin` 8 个 numeric 字段非 null
- [ ] CG-fallback token（如 zano）`avg_volume_30d=null`，UI 显 "—"
- [ ] 前端 BTC 页可见 5 个 tile，数值合理
- [ ] tile hover 显示 tooltip（"Liquidity: data from binance via BTC/USDT pair"）

---

### R8-1D · 用户 item 7（美股 40 只集成）

**用户原话**："现在系统只能支持两个股票，现在需要增加数量...通过 Yahoo Finance 去调研一下这些股票的相关信息" + 40 ticker 列表 + Q5 "默认是 CRCL" + Q6 "彻底分开"

**40 ticker 列表**：
```
ANY, APLD, ARBK, BIGG, BITF, BKKT, BLSH, BTBT, BTCS, BTDR,
BTGO, BTM, CAN, CIFR, CLSK, COIN, CORZ, CRCL, DEFT, DMGGF,
EBON, ETOR, EXOD, FIGR, FLD, GEMI, GLXY, GREE, HIVE, HOOD,
HUT, IREN, MARA, MOGO, MSTR, NPPTF, RIOT, SMLR, VOYG, WULF
```

**why**: 一期完全没 stocks 集成。yfinance Python lib 是标准选择，US ticker 无需后缀。

**what**:
1. 新 yfinance_client 模块
2. universe config 文件
3. asset_class 维度贯穿后端 API + 前端
4. 前端 tab strip
5. 独立 stocks daily refresh job

**where + how**:

- `requirements.txt` 加：`yfinance==0.2.40`
- 新文件 `local_data/metadata/stocks_universe.csv`：
  ```csv
  ticker,asset_class,name,exchange,region,active
  ANY,us-stock,Sphere 3D Corp,NASDAQ,US,true
  APLD,us-stock,Applied Digital Corp,NASDAQ,US,true
  ARBK,us-stock,Argo Blockchain plc,NASDAQ,US,true
  ... (40 行)
  ```
  （`name` 字段可由 yfinance `Ticker.info["longName"]` 自动填，初次启动时 enrich）
- 新文件 `backend/data/yfinance_client.py`:
  ```python
  import yfinance as yf
  import pandas as pd
  from typing import Optional
  from datetime import date

  STOCKS_SOURCE_TAG = "yfinance"

  class YFinanceClient:
      def __init__(self):
          self._tk_cache = {}

      def _ticker(self, sym):
          if sym not in self._tk_cache:
              self._tk_cache[sym] = yf.Ticker(sym)
          return self._tk_cache[sym]

      def fetch_ohlcv(self, ticker: str, start: date, end: date) -> Optional[pd.DataFrame]:
          t = self._ticker(ticker)
          df = t.history(start=str(start), end=str(end),
                         auto_adjust=True, actions=False, prepost=False)
          if df is None or df.empty:
              return None
          df = df.rename(columns={
              "Open": "open", "High": "high", "Low": "low",
              "Close": "close", "Volume": "volume"
          })
          df.index = df.index.tz_localize(None).normalize()
          df["date"] = df.index
          df["source"] = STOCKS_SOURCE_TAG
          df = df.reset_index(drop=True)
          return df[["date", "open", "high", "low", "close", "volume", "source"]]

      def fetch_market_overview(self, ticker: str) -> dict:
          info = self._ticker(ticker).info
          return {
              "ticker": ticker,
              "name": info.get("longName"),
              "exchange": info.get("exchange"),
              "market_cap": info.get("marketCap"),
              "shares_outstanding": info.get("sharesOutstanding"),
              "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
              "total_volume_24h": info.get("regularMarketVolume"),
              "price_change_percentage_24h": info.get("regularMarketChangePercent"),
          }
  ```
- `backend/data/fetcher.py` 新方法 `run_stocks_daily_update`：mirror crypto path 但独立 try/finally + last_update.json 区段
- `backend/main.py` lifespan：APScheduler 加第二个 cron 08:35 Asia/Shanghai for stocks
- `backend/services/data_service.py:99-152` `list_tokens()` 改造：
  ```python
  def list_tokens(self) -> List[Dict]:
      out = []
      # crypto tokens
      for cg_id in self._list_crypto_ohlcv_ids():
          out.append({**meta, "asset_class": "crypto", "id": cg_id})
      # us stocks
      for ticker in self._list_stocks_universe(asset_class="us-stock"):
          out.append({**meta, "asset_class": "us-stock", "id": ticker})
      return out
  ```
- `backend/scoring/ranking.py` 加 `asset_class` 分区：
  ```python
  def cross_sectional_percentile(scores: Dict[str, float],
                                  asset_class: Optional[str] = None,
                                  tokens_by_class: Optional[Dict[str, str]] = None) -> Dict[str, float]:
      if asset_class is None or tokens_by_class is None:
          # legacy: rank all together
          ...
      else:
          # partition by class, rank within each
          ...
  ```
- `backend/api/_validators.py:26` `validate_cg_id` 正则扩展：`^[a-zA-Z0-9][a-zA-Z0-9_\-\.]{0,63}$`（允许大写 + dot for `.HK`，仍拒绝 `..` `/` 前导 dot）
- `backend/api/routes_scores.py` `all_scores()` 加 `asset_class: Optional[str] = None` query param，filter 后再 cross-section rank
- 前端 `frontend/index.html` sidebar 上方加：
  ```html
  <div class="sidebar-tabs">
    <button class="tab-btn active" data-tab="crypto">Crypto (200)</button>
    <button class="tab-btn" data-tab="us-stock">US Stocks (40)</button>
  </div>
  ```
- 前端 `frontend/js/app.js` 加 tab logic：tab 状态保存到 `location.hash`，切 tab 时 reload rankings + 默认 token：crypto→BTC，us-stock→CRCL
- 在 token 选择器 dropdown 中按 active tab 过滤 candidates

**acceptance**:
- [ ] `local_data/ohlcv/COIN.csv`、`MSTR.csv` 等 40 个文件存在，source=yfinance，行数 ≥ 250
- [ ] `local_data/metadata/stocks_universe.csv` 40 行齐
- [ ] `GET /api/tokens` 返回 240 entries（200 + 40），每个含 `asset_class`
- [ ] `GET /api/scores?asset_class=us-stock` 仅 40 美股，独立 cross-section rank
- [ ] crypto rank 1 的不在 stocks rank 1（彻底分开）
- [ ] 前端 sidebar 显示 2 个 tab；切到 US Stocks 默认选 CRCL；hash 变为 `#tab=us-stock`
- [ ] 周末 stocks fetch 不报错（yfinance 跳过非交易日）
- [ ] stocks daily cron 08:35 触发，独立于 crypto cron

---

### Phase 2A 验收：R8-α audit round

完工后派 **2 个 fresh-context agent**：
- **Agent A**：System Architect — 验证 portability、history extension、stocks 集成
- **Agent B**：Data Scientist — 验证数据完整性、cross-section 独立 rank、4-tier waterfall 真用上

每个 agent 端口分配：8091（A）、8092（B）。报告写到 `/tmp/AUDIT_R8a_*.md`。

---

## Phase 2B — 评分体系 + 指标稳健性（Week 2）

### R8-2A · 用户 item 2A（Tier A 综合评分）

**用户原话**: item 2 (a-c) + item 9 "应该放在最上面" + Q1 "A 和 B 都做" + Q4 Strategy A + Q7 6 sleeve

**why**: Trend / Reversal 双数让用户无所适从；需 1 个 headline 数字。

**what**: 详见 Part 3.1。

**where + how**:

- 新指标族 `backend/indicators/volatility.py`：
  ```python
  class VolatilityFamily(IndicatorFamily):
      name = "volatility"
      default_params = {"windows": [20, 60]}

      def compute(self, df, **params):
          p = self.merged_params(params)
          windows = p["windows"]
          close = df["close"].astype(float)
          log_ret = np.log(close / close.shift(1))
          out = {}
          for w in windows:
              # annualised (365 trading days for crypto)
              out[f"vol_{w}d"] = log_ret.rolling(w).std() * np.sqrt(365)
          return out
  ```
- `backend/indicators/registry.py:29-42` 注册 `volatility`
- 新模块 `backend/scoring/overall_score.py`:
  ```python
  TIER_A_WEIGHTS = {
      "trend": 0.40,
      "reversal": 0.25,
      "breadth": 0.15,
      "risk": 0.10,
      "ts_trend_2y": 0.05,
      "ts_reversal_2y": 0.05,
  }

  def compute_breadth(trend_components: dict) -> float:
      """% of 9 trend signals that are positive."""
      pos = sum(1 for v in trend_components.values() if v is not None and v > 0)
      return 100.0 * pos / len(trend_components) if trend_components else 0.0

  def compute_overall_score(
      trend_cs_pct: float, reversal_cs_pct: float,
      breadth: float, risk_cs_pct: float,
      ts_trend_2y_pct: Optional[float], ts_rev_2y_pct: Optional[float],
      weights: dict = TIER_A_WEIGHTS,
  ) -> float:
      ts_trend = ts_trend_2y_pct if ts_trend_2y_pct is not None else 50.0
      ts_rev = ts_rev_2y_pct if ts_rev_2y_pct is not None else 50.0
      return (
          weights["trend"]       * trend_cs_pct
        + weights["reversal"]    * reversal_cs_pct
        + weights["breadth"]     * breadth
        + weights["risk"]        * risk_cs_pct
        + weights["ts_trend_2y"] * ts_trend
        + weights["ts_reversal_2y"] * ts_rev
      )

  def cross_sectional_overall_scores(all_indicators, all_scores, vol_data, asset_class=None) -> Dict[str, float]:
      ...

  def compute_overall_components(token_id, all_indicators, all_scores, weights) -> dict:
      """Returns 6 sleeve rows with raw value + weight + contribution."""
      ...
  ```
- 修改 `backend/services/data_service.py:262-287` `current_scores()` 加：
  ```python
  out[cg_id] = {
      ...existing fields...,
      "overall_score": float(overall_scores.get(cg_id, 0.0)),
      "overall_cs_percentile": float(cs_overall.get(cg_id, 0.0)),
      "overall_components": compute_overall_components(cg_id, ...),
  }
  ```
- `backend/api/routes_scores.py` 加 overall fields；`?sort_by=overall` 选项
- 修改 `scores_history.csv` schema：加 `overall_score`, `overall_cs_percentile` 列
- 读取兼容：`data_service._load_scores_history` 旧行 overall 字段 fillna(None)
- 前端 `frontend/index.html` 重构 score-detail：
  ```html
  <section class="score-detail">
    <h2 class="section-header">Score Breakdown</h2>

    <!-- NEW Overall hero card, full width -->
    <div class="score-card score-card-overall">
      <header class="overall-head">
        <h3>Overall <span class="badge-composite">COMPOSITE</span>
          <span class="info-mark" data-explainer="overall">?</span></h3>
        <span class="rank-chip" id="overall-rank">Rank — / —</span>
        <div id="overall-percentiles" class="percentiles muted"></div>
      </header>
      <div class="overall-body">
        <div id="overall-gauge" class="score-gauge score-gauge-xl"></div>
        <div class="overall-meta">
          <div id="overall-value" class="score-large score-xl">--</div>
          <div id="overall-blurb" class="score-blurb muted">--</div>
        </div>
        <ul id="overall-components" class="components components-overall"></ul>
      </div>
    </div>

    <!-- Existing 2-col Trend + Reversal grid -->
    <div class="score-detail-grid">
      <div class="score-card score-card-trend">
        <header>
          <h3>Trend <span class="info-mark" data-explainer="trend">?</span></h3>
          <span class="rank-chip" id="trend-rank">Rank — / —</span>
        </header>
        ... existing trend content ...
      </div>
      <div class="score-card score-card-reversal">
        ... mirror for reversal ...
      </div>
    </div>
  </section>
  ```
- `frontend/js/app.js renderScoreDetail()` 扩展渲染 overall
- `frontend/css/styles.css` 加 `.score-card-overall { border-left: 2px solid var(--accent-blue) }`、`.badge-composite { ... 9px uppercase pill }`、`.score-gauge-xl { width: 240px }`、`.score-xl { font-size: 56px }`

**acceptance**:
- [ ] `GET /api/scores/bitcoin` 返回 `overall_score`, `overall_cs_percentile`, `overall_components`（6 个 key 完备）
- [ ] 200 个 token 单日 overall_score rank 唯一覆盖 1..200
- [ ] Walk-forward Spearman ρ(`overall`, forward 5d return) ≥ ρ((trend+reversal)/2, forward 5d return) + 0.02（用 scores_history 现有数据 holdout 最后 90 天）
- [ ] hero card 在 1440×900 viewport 完全在首屏内
- [ ] gauge 视觉上比 Trend/Reversal 大 ≥ 30%（DOM rect 实测）
- [ ] 6 个 sleeve 总和等于 overall_score 显示值（数学一致性）

---

### R8-2B · 用户 item 6（指标稳健性回测）

**用户原话**: "(a) 针对关键的买入/卖出点（如金叉、死叉等策略）进行回测。(b) 评估如果完全按照该指标交易，在历史中是盈利还是亏损"

**why**: 用户问"我能不能信这个 RSI"。当前 `golden_cross.py` 只能跑 SMA，不能 generalize 到其他指标。

**what**:
1. 重构 `golden_cross.py` 为 Strategy pattern
2. 9 canonical strategies
3. universe_robustness module
4. `/api/indicator-robustness` endpoint with 缓存
5. UI section

**where + how**:

- 新模块 `backend/backtest/engine.py`:
  ```python
  @dataclass
  class BacktestResult:
      cagr: float; sharpe: float; max_drawdown: float; n_trades: int
      final_equity: float; win_rate: float; avg_trade_return: float
      equity_curve: list[dict]; params: dict

  def run_backtest(
      df: pd.DataFrame,
      strategy: Callable[[pd.DataFrame, dict], pd.Series],
      strategy_params: dict | None = None,
      start_date: str | None = None,
      commission_bps: float = 5.0,
  ) -> BacktestResult:
      """Generic backtest engine. Strategy returns position [0,1] aligned to df.index."""
      ...
  ```
  把 `golden_cross.py:32-139` 的统计计算 lift 进来。
- 新模块 `backend/backtest/strategies.py`:
  ```python
  def strategy_rsi_oversold(df, period=14, entry=30, exit=50) -> pd.Series:
      rsi = INDICATORS["rsi"].compute(df, period=period)[f"rsi_{period}"]
      in_pos = pd.Series(0, index=df.index)
      pos = 0
      for i in range(len(df)):
          if pos == 0 and rsi.iloc[i] < entry:
              pos = 1
          elif pos == 1 and rsi.iloc[i] > exit:
              pos = 0
          in_pos.iloc[i] = pos
      return in_pos

  def strategy_macd_signal_cross(df, fast=12, slow=26, signal=9) -> pd.Series:
      ...
  def strategy_kdj_oversold_cross(df, N=9, M1=3, M2=3) -> pd.Series:
      ...
  ... 9 total

  CANONICAL_STRATEGIES = {
      "rsi_oversold_30_50": (strategy_rsi_oversold, {"period": 14, "entry": 30, "exit": 50}),
      "macd_signal_cross": (strategy_macd_signal_cross, {}),
      "kdj_oversold_cross": (strategy_kdj_oversold_cross, {}),
      "bollinger_lower_band": (strategy_bollinger_lower_band, {"period": 20, "num_std": 2.0}),
      "sma_golden_cross": (strategy_sma_golden_cross, {"fast": 5, "slow": 20}),
      "ema_golden_cross": (strategy_ema_golden_cross, {"fast": 5, "slow": 20}),
      "momentum_breakout": (strategy_momentum_breakout, {"lookback": 20, "threshold": 0.0}),
      "zscore_reversion": (strategy_zscore_reversion, {"window": 40, "entry_z": -2.0, "exit_z": 0.0}),
      "price_appreciation": (strategy_price_appreciation, {"lookback": 20, "threshold": 0.10}),
  }
  ```
- 新模块 `backend/backtest/universe_robustness.py`:
  ```python
  def run_universe_robustness(
      svc: DataService,
      strategies: dict = CANONICAL_STRATEGIES,
      asset_class: str = "crypto",
      min_history_days: int = 365,
  ) -> dict:
      results = {}
      for strat_name, (fn, params) in strategies.items():
          per_token = []
          for cg_id in svc.list_active_ids(asset_class=asset_class):
              df = svc.get_ohlcv(cg_id)
              if df is None or len(df) < min_history_days: continue
              result = run_backtest(df, strategy=fn, strategy_params=params)
              per_token.append({
                  "cg_id": cg_id, "symbol": svc.get_token(cg_id)["symbol"],
                  "sharpe": result.sharpe, "cagr": result.cagr,
                  "max_dd": result.max_drawdown, "n_trades": result.n_trades,
                  "win_rate": result.win_rate,
              })
          # Aggregate
          sharpes = [r["sharpe"] for r in per_token if r["sharpe"] is not None]
          median_sharpe = np.median(sharpes)
          pct_positive = sum(1 for s in sharpes if s > 0) / len(sharpes) * 100
          worst = min(per_token, key=lambda r: r["sharpe"])
          best = max(per_token, key=lambda r: r["sharpe"])
          # Reliability badge
          if median_sharpe >= 0.5 and pct_positive >= 60 and worst["sharpe"] >= -1.0:
              reliability = "reliable"
          elif median_sharpe >= 0.2 or pct_positive >= 50:
              reliability = "caveats"
          else:
              reliability = "unreliable"
          results[strat_name] = {
              "median_sharpe": median_sharpe, "mean_sharpe": np.mean(sharpes),
              "pct_positive": pct_positive,
              "worst": {"cg_id": worst["cg_id"], "sharpe": worst["sharpe"]},
              "best": {"cg_id": best["cg_id"], "sharpe": best["sharpe"]},
              "reliability": reliability,
              "n_tokens": len(per_token),
              "per_token": per_token,
          }
      return results
  ```
- 缓存 `local_data/robustness_cache/`:
  - `robustness_summary.json` — top-level aggregate
  - `robustness_<strategy_name>.json` — per-token detail
  - `robustness_meta.json` — `{computed_at, ohlcv_hash, universe_size}`
- 失效：daily-update 末尾算 ohlcv_hash 与 stored hash 比对，不同则后台 recompute
- 新 router `backend/api/routes_robustness.py`:
  - `GET /api/indicator-robustness` 顶层汇总
  - `GET /api/indicator-robustness/{strategy_name}` 详情
  - `POST /api/indicator-robustness/recompute` 手动
- `backend/backtest/golden_cross.py` 退化为 thin wrapper（保持 `/api/backtest/{cg_id}` 不变）
- 前端 `frontend/index.html` 在现有 `<details class="backtest">` 后加：
  ```html
  <section class="indicator-robustness">
    <h2 class="section-header">Indicator Robustness</h2>
    <table id="robustness-table">
      <thead><tr>
        <th>Strategy</th><th>Median Sharpe</th><th>% Positive</th>
        <th>Worst</th><th>Best</th><th>Reliability</th>
      </tr></thead>
      <tbody></tbody>
    </table>
    <div id="robustness-detail" hidden></div>
  </section>
  ```
- `frontend/js/components/robustness_panel.js`（~100 行）渲染表格 + 点击 row 展开 distribution

**acceptance**:
- [ ] `backend/backtest/engine.py` 存在；`golden_cross.py` 退化到 ≤20 行
- [ ] `CANONICAL_STRATEGIES` 注册恰好 9 个
- [ ] `GET /api/indicator-robustness` 200 in <100ms（cache hit），9 strategies 都返
- [ ] 手动 `POST /api/indicator-robustness/recompute` ≤ 5 分钟完成
- [ ] 修改任一 OHLCV CSV 后 daily-update 自动 recompute
- [ ] 前端 table 9 行，每行有 reliability badge（reliable/caveats/unreliable）
- [ ] 点击 RSI row 展开 per-token Sharpe 分布
- [ ] 点击 distribution 中的 token 跳转到该 token 详情页

---

### R8-2C · 用户 item 1（评分展示优化）

**用户原话**: "(a) 明确这两个 Score 的具体含义和优势。(b) 增加对比维度，展示当前代币在 Top 200 中的排名。(c) 在图表中增加计算逻辑的说明。"

**what**:
1. API 加 rank fields
2. 新 explainer module + endpoint
3. 前端 rank chip + popover modal

**where + how**:

- `backend/services/data_service.py` `current_scores()` 加：
  ```python
  # rank_in_universe by descending score
  trend_rank = {cid: r+1 for r, (cid, _) in enumerate(
      sorted(out.items(), key=lambda x: x[1]['trend_score'], reverse=True)
  )}
  reversal_rank = {cid: r+1 for r, (cid, _) in enumerate(
      sorted(out.items(), key=lambda x: x[1]['reversal_score'], reverse=True)
  )}
  overall_rank = {cid: r+1 for r, (cid, _) in enumerate(
      sorted(out.items(), key=lambda x: x[1]['overall_score'], reverse=True)
  )}
  for cid in out:
      out[cid]['rank_in_universe_trend'] = trend_rank[cid]
      out[cid]['rank_in_universe_reversal'] = reversal_rank[cid]
      out[cid]['rank_in_universe_overall'] = overall_rank[cid]
      out[cid]['universe_size'] = len(out)
  ```
- `backend/api/routes_scores.py:74-115` `token_score()` 把 rank fields 加入 response
- 新模块 `backend/scoring/explainers.py`（详见 Part 3.1）
- 新 router `backend/api/routes_scoring_meta.py`：`GET /api/scoring/explainer` 返回三个 explainer
- 前端 `frontend/index.html` 每个 score-card title bar 加：`<span class="rank-chip" id="trend-rank">Rank — / —</span>`
- 前端 `frontend/js/app.js` `renderScoreDetail()` 写入 rank chip
- 新 popover：点 `.info-mark[data-explainer]` 触发 modal overlay 渲染 markdown
- `frontend/css/styles.css` 加 `.rank-chip { font-variant-numeric: tabular-nums; padding: 1px 6px; border-radius: 3px; ... }`、`.explainer-modal { ... }`

**acceptance**:
- [ ] `GET /api/scores/bitcoin` 包含 `rank_in_universe_trend`, `..._reversal`, `..._overall`, `universe_size`
- [ ] 每个 score-card 标题旁可见 "Rank N / 200" 文本
- [ ] 点击任一 `.info-mark` 弹出 modal，含 "rank-percentile blending" 字样
- [ ] close-only token rank 显示 "—" 不报错（API 返回 null）

---

### Phase 2B 验收：R8-β audit round

派 **2 个 fresh-context agent**：
- **Agent C**：Quant Researcher — 验证 Tier A 公式数值正确、Spearman ρ baseline 测试、9 strategy 数据合理
- **Agent D**：Product Designer — 验证 hero panel 视觉、explainer modal 内容准确

报告到 `/tmp/AUDIT_R8b_*.md`。

---

## Phase 2C — UX 视觉（Week 3）

### R8-3A · 用户 item 9（Overall hero panel UI 已含在 R8-2A）

已在 R8-2A 实现。本 phase 主要做 polish + 移动端适配。

**移动端 (<768px)** 堆叠顺序（top to bottom）：
1. Overall card — 全宽，gauge 居中，components 折叠成 `<details>`
2. Trend card — 全宽
3. Reversal card — 全宽

### R8-3B · 用户 item 3（浅色模式）

**what + how**: 详见 Part 3.3。

**实现 checklist**:

- [ ] `frontend/css/styles.css` 加 `html[data-theme="light"] { ... }` 块覆盖 21 个 CSS var
- [ ] `frontend/index.html` `<head>` 顶部加 inline `<script>` 解析 localStorage + prefers-color-scheme + dataset.theme
- [ ] `frontend/index.html` topbar 右侧加 `<button id="theme-toggle">` + sun/moon SVG icons
- [ ] `frontend/js/app.js` 加 `setupThemeToggle()` 函数：click 切换 + localStorage 写入 + 触发 `Charts.retintAll()`
- [ ] `frontend/js/charts/candle.js`:
  - 加 `readPalette()` helper 读 CSS var
  - 改 `_baseOpts()` 用 readPalette()
  - 加 `retint(ctx)` 公有方法
- [ ] `frontend/js/charts/indicator_panels.js`:
  - 同上 `readPalette()`
  - `_smallChart` 用 readPalette()
  - `retint(family, ctx)` 方法
- [ ] `frontend/js/components/score_gauge.js`:
  - 把所有硬编码 hex 移到 readPalette()
  - render 函数缓存 last value 以便 retint 重渲
- [ ] `frontend/js/components/sparkline.js`:
  - 同上
- [ ] `frontend/index.html` legend swatch inline `style="background:#..."` 改成 class（`.swatch-blue`, `.swatch-orange`, `.swatch-green`, `.swatch-purple` 各读相应 CSS var）
- [ ] 添加 transition: `html, body, .topbar, .score-card, .indicator-panel, .chart { transition: background-color 200ms ease, color 200ms ease }`

**acceptance**:
- [ ] 切换主题 charts 不重建（DevTools zoom state 保留）
- [ ] 所有元素读 CSS var；grep `[a-fA-F0-9]{6}` 找不到 hex literal（除 :root 内）
- [ ] WCAG AA：每对 text/bg ≥ 4.5:1（用 axe-core 或 Chrome DevTools 校验）
- [ ] 首次加载 light mode 用户无 dark flash
- [ ] localStorage `iosg-theme` 存正确值
- [ ] OS prefers-color-scheme 变化时仅在 localStorage 无值时响应

### R8-3C · 用户 item 4（全英化）

**用户原话** + Q11: 包含后端代码注释 + log。

**实现 checklist**:

- [ ] `frontend/js/app.js:586-605` COMPONENT_LABELS 16 entries 改 EN（见 Part 3.3 表）
- [ ] 全 `frontend/**/*.{js,html,css}` grep `[一-鿿]` → 0 hits
- [ ] 全 `backend/**/*.py` grep `[一-鿿]` → 0 hits（包括 docstring、code comment、log message）
- [ ] docs（README、PLAN、任务交接指南）不动
- [ ] commit messages 不重写历史

**注意**：后端中文 comment 翻译时**保留原意完整**。例如：
- `# P0-F: HTML5 [hidden] 属性 MUST 胜过组件 display 规则` →
- `# P0-F: HTML5 [hidden] attribute MUST win over component display rules`

**acceptance**:
- [ ] `grep -rE '[一-鿿]' frontend/ backend/` 0 hits
- [ ] `ma50_dev` vs `ma50_dev_z_40` UI 中可区分（修了 collision bug）
- [ ] API 响应仍是 ASCII 键（一期已经是）

### R8-3D · 用户 item 8（tooltip 富化）

**what**: 详见 Part 3.3。

**实现 checklist**:

- [ ] 新组件 `frontend/js/components/popover.js`（~80 行）：
  - `Popover.attach(element, getContent)` 绑定 hover
  - 200ms open delay
  - 鼠标移到 popover 内部保持
  - click outside dismiss
  - 用 CSS var 自动适应主题
- [ ] 12 个 panel header `<header><span class="panel-title">...</span><span class="info-mark" data-tooltip="...">?</span></header>`，原生 title
- [ ] 16 个 Score Breakdown component row：用 popover.attach + COMPONENT_TOOLTIPS map
- [ ] 7 个 param label info-mark：原生 title
- [ ] Overall info-mark：popover with full explainer

**acceptance**:
- [ ] 每个 `.info-mark` + panel header 都有真 tooltip（grep 不到 `title="?"` 或 `title=""`）
- [ ] 全部 tooltip ≤ 280 char：`Array.from(document.querySelectorAll('[title]')).forEach(e => console.assert(e.title.length <= 280))`
- [ ] popover 在 Score Breakdown row hover 200ms 出现
- [ ] popover 内 hover 不消失
- [ ] popover 跟主题切换变色

### R8-3E · R6/R7 carryover bugs（Q15 全部修）

**R6-7 移动端 drawer 真生效**：
- 调试 `frontend/css/styles.css` `@media (max-width: 768px) .sidebar { position: fixed; ... transform: translateY(...) }`
- 确认 R6-1 score-detail hoist 没破坏 sidebar 的 DOM 位置
- Playwright 实测：375×812 viewport drawer 默认收起、tap 拉起 .expanded、再 tap 收起

**R7-3 gauge 0/100 label 裁切**：
- `frontend/js/components/score_gauge.js` viewBox 从 W=220 调到 W=240，加 padding right/left = 6
- Playwright 截图 `/tmp/r8c/19_gauge_closeup.png` 三个数字可读

**R7-4 indicator panel 右价轴 chip 重叠**：
- `frontend/js/charts/indicator_panels.js` `rightPriceScale.minimumWidth` 从 56 调到 72
- 或改方案：把 createPriceLine 的 OB/OS chip 移到 y-axis 内侧 label 模式

**acceptance**:
- [ ] 375×812 viewport screenshot drawer 默认收起、可拉起
- [ ] gauge 三个 tick label（0、50、100）全部可读
- [ ] RSI panel 70/30 chip 不压 y-axis tick label

### Phase 2C 验收：R8-γ audit round

派 **2 个 fresh-context agent**：
- **Agent E**：Artist / Aesthetician — 验证 21 个 light var 高级感、tooltip 富化、英化无残留
- **Agent F**：Senior Analyst — 验证 Overall hero 视觉等级、explainer 内容、移动端 drawer 真用

---

## Phase 2D — Tier B + 最终验收（Week 4）

### R8-4A · 用户 item 2B（Tier B Ridge 回归）

**what + how**: 详见 Part 3.1。

**实现 checklist**:

- [ ] 新脚本 `scripts/train_tier_b.py`：
  ```python
  from sklearn.linear_model import RidgeCV
  import pandas as pd
  # 1. 读 scores_history.csv → ~213k 观测
  # 2. 拼接对应 OHLCV → forward 5d log return
  # 3. 16 个原子 signal + 4 sleeve CS percentile features
  # 4. Date FE: per-date demean
  # 5. Walk-forward CV: 24m train / 1m test / monthly rolling
  # 6. RidgeCV(alphas=[0.1, 1, 10, 100])
  # 7. coef 跨 12 折稳定性检测，sign 翻转的 sleeve drop
  # 8. 写 local_data/scoring/tier_b_weights.json
  #    {weights: {trend: 0.42, ...}, alpha: 1.0,
  #     cv_folds: [...12 折数据...],
  #     holdout_spearman_rho_5d: 0.07,
  #     baseline_tier_a_rho_5d: 0.05,
  #     accept: true|false}
  ```
- [ ] 修改 `backend/scoring/overall_score.py` 加 `load_tier_b_weights()` + 请求 `?weights=regressed` 时用 Tier B
- [ ] `backend/api/routes_scores.py` 加 `weights` query 参数支持
- [ ] 前端 score-card 标题加 `<select id="weights-toggle">` 切换 `Theory | Data-driven`
- [ ] explainer modal Tier B 行加 actual coefficient table

**acceptance**:
- [ ] `scripts/train_tier_b.py` 跑完输出 `tier_b_weights.json`
- [ ] holdout Spearman ρ ≥ Tier A baseline + 0.02 OR `accept: false` 并 explainer 说明
- [ ] 前端 weights toggle 切换两种权重，UI 即时刷新（点 token 重新算）

### Phase 2D 验收：R8-δ audit round

派 **1 个 quant agent** 做最终 cross-check：
- Tier A vs Tier B 数值合理性（同 token 差异 < 50 分）
- 整个 Phase 2 verdict 综合（21+ commits 无回归）

---

# Part 5 — 4-Phase 详细时间表

| 周 | Phase | 工作单元 | 估算 | Audit |
|---|---|---|---|---|
| **Week 1** | **2A 基础+数据** | R8-1A portability + integrity (Day 1)<br>R8-1B history → 2020 (Day 2-3)<br>R8-1C mcap/liquidity panel (Day 4)<br>R8-1D stocks 集成 (Day 5)<br>R8-α audit (Day 5 末) | 5 工作日 | 2 agents |
| **Week 2** | **2B 评分+分析** | R8-2A Tier A overall + volatility indicator (Day 1-2)<br>R8-2B 9 canonical strategies + engine refactor (Day 3-4)<br>R8-2C score display + explainer (Day 5)<br>R8-β audit (Day 5 末) | 5 工作日 | 2 agents |
| **Week 3** | **2C UX 视觉** | R8-3A overall hero polish (Day 1)<br>R8-3B 浅色模式 (Day 2)<br>R8-3C 全英化 (Day 3)<br>R8-3D tooltip 富化 (Day 4)<br>R8-3E R6/R7 carryover bugs (Day 5 上午)<br>R8-γ audit (Day 5 下午) | 5 工作日 | 2 agents |
| **Week 4** | **2D Tier B + 最终** | R8-4A Tier B Ridge (Day 1-3)<br>UI weights toggle (Day 4)<br>R8-δ audit (Day 5) + buffer | 5 工作日 | 1 agent |

总 = 4 周 = ~20 工作日 = ~25 commits

---

# Part 6 — 文件改动总清单

## 新增文件（22 个）

| 文件 | 用途 | item |
|---|---|---|
| `backend/data/integrity.py` | boot 完整性校验 | 10 |
| `backend/data/yfinance_client.py` | stocks 数据源 | 7 |
| `backend/data/quarantine/` | 损坏 CSV 隔离 dir | 10 |
| `backend/indicators/volatility.py` | vol_20d/60d (for Risk sleeve) | 2 |
| `backend/scoring/overall_score.py` | Tier A + Tier B 综合评分 | 2 |
| `backend/scoring/explainers.py` | Trend/Reversal/Overall explainer dicts | 1 |
| `backend/backtest/engine.py` | 通用回测引擎 | 6 |
| `backend/backtest/strategies.py` | 9 canonical strategies | 6 |
| `backend/backtest/universe_robustness.py` | universe-wide backtest | 6 |
| `backend/api/routes_market.py` | market_overview + data_coverage endpoints | 5, 11 |
| `backend/api/routes_robustness.py` | indicator-robustness endpoints | 6 |
| `backend/api/routes_scoring_meta.py` | explainer endpoint | 1 |
| `backend/api/routes_admin.py` | repair_token endpoint | 10 |
| `frontend/js/components/market_panel.js` | 5-tile market info | 5 |
| `frontend/js/components/popover.js` | 局部 popover | 8 |
| `frontend/js/components/robustness_panel.js` | indicator robustness UI | 6 |
| `scripts/train_tier_b.py` | Tier B 训练脚本 | 2 |
| `scripts/run_history_extension.py` | history backfill one-shot | 11 |
| `scripts/pack_green_folder.sh` | 绿色化 zip 打包 | 10 |
| `local_data/metadata/data_coverage.json` | per-token coverage | 11 |
| `local_data/metadata/stocks_universe.csv` | 40 美股配置 | 7 |
| `local_data/robustness_cache/` | 回测缓存 dir | 6 |

## 修改文件（30 处）

| 文件 | 改动 | line range |
|---|---|---|
| `backend/main.py` | 修 portability bug + boot integrity + stocks scheduler | 57, lifespan |
| `backend/config.py` | HISTORY_DAYS=2326 + stocks constants | 83 |
| `backend/data/coingecko_client.py` | 扩展 expected 字段提取 | 276-290 |
| `backend/data/exchange_client.py` | 8 个 exchange + Coinbase/Kraken/KuCoin/Bitstamp | 38-43, EXCHANGE_PRIORITY |
| `backend/data/fetcher.py` | run_history_extension + run_stocks_daily_update + repair_token | append |
| `backend/data/local_store.py` | schema 验证更新 | 39 |
| `backend/data/data_validator.py` | TOP200_REQUIRED_COLUMNS 扩展 | 27-33 |
| `backend/services/data_service.py` | overall_score + rank_in_universe + asset_class | 99-152, 262-322 |
| `backend/scoring/trend_score.py` | unchanged (signals reuse) | — |
| `backend/scoring/reversal_score.py` | unchanged | — |
| `backend/scoring/ranking.py` | asset_class partition | 16-24 |
| `backend/backtest/golden_cross.py` | thin wrapper for engine.run_backtest | 32-139 |
| `backend/api/routes_tokens.py` | asset_class field + active flag | 14-94 |
| `backend/api/routes_scores.py` | overall + rank + asset_class filter + weights param | 16-115 |
| `backend/api/_validators.py` | regex 允许 A-Z + `.` | 26 |
| `frontend/index.html` | hero panel + market panel + tab strip + theme toggle + data coverage + robustness section | 多处 |
| `frontend/css/styles.css` | light theme block + score-card-overall + market-panel + robustness-table + 移动 drawer 修 | 多处 |
| `frontend/js/app.js` | overall card + tabs + theme + i18n + popover wiring | 多处 |
| `frontend/js/api.js` | getMarketOverview + getIndicatorRobustness + getScoringExplainer + getDataCoverage | 多处 |
| `frontend/js/charts/candle.js` | readPalette + retint | 多处 |
| `frontend/js/charts/indicator_panels.js` | readPalette + retint + minimumWidth fix | 多处 |
| `frontend/js/components/score_gauge.js` | readPalette + xl size + viewBox fix | 多处 |
| `frontend/js/components/sparkline.js` | readPalette | 多处 |
| `requirements.txt` | add yfinance | append |
| `README.md` | 绿色化 + 浅色模式 + asset class 说明 | append |
| **全 `backend/**/*.py`** | 中文 comment + log → 英文 | 多处 |

---

# Part 7 — 4 轮 audit 验收方法

每个 audit round 派指定角色的 fresh-context agent（不读旧报告、不互看、不动代码）。

## R8-α (Phase 2A 末) — 2 agents

**Agent A — System Architect**：
- 端口 8091；写报告到 `/tmp/AUDIT_R8a_arch.md`
- 验证 portability fix（DATA_DIR=/tmp/xxx 端到端）
- 验证 history extension 真的回到 2020（BTC/ETH 首行 ≤ 2020-01-01）
- 验证 8 exchange waterfall 在 daily-update 真用上
- 验证 quarantine + repair 流程

**Agent B — Data Scientist**：
- 端口 8092；写报告到 `/tmp/AUDIT_R8a_data.md`
- 验证 data_coverage.json schema + tier_breakdown 完整
- 验证 stocks_universe.csv 40 行齐 + 每只 OHLCV 真拉成功
- 验证 cross_sectional 真彻底分开（crypto rank 不影响 stocks rank）
- 验证 market_overview API 数值合理

## R8-β (Phase 2B 末) — 2 agents

**Agent C — Quant Researcher**：
- 端口 8091；`/tmp/AUDIT_R8b_quant.md`
- 验证 Tier A overall_score 公式（手算 vs API 6 位小数一致）
- 验证 walk-forward Spearman ρ 测试通过
- 验证 9 robustness strategies 数据合理（不是全部 unreliable）
- 验证 indicator_robustness 缓存失效正确

**Agent D — Product Designer**：
- 端口 8092；`/tmp/AUDIT_R8b_design.md`
- 验证 Overall hero card 视觉层级（首屏可见、240px gauge、56px 数字）
- 验证 6 个 sleeve breakdown 数学一致（加权求和 = overall_score）
- 验证 explainer modal 内容准确 + 引用代码字面
- 验证 rank chip 显示正确

## R8-γ (Phase 2C 末) — 2 agents

**Agent E — Artist / Aesthetician**：
- 端口 8091；`/tmp/AUDIT_R8c_artist.md`
- 验证 21 个 light CSS var WCAG AA 全通过
- 验证主题切换无 chart 重建 / zoom 保留
- 验证 16 + 12 + 16 + 7 + 1 = 52 个 tooltip 都有内容
- 验证 R6-7 drawer / R7-3 gauge / R7-4 chip 三个 carryover 真修

**Agent F — Senior Analyst**：
- 端口 8092；`/tmp/AUDIT_R8c_analyst.md`
- 验证 grep `[一-鿿]` 全工程 0 hits
- 验证 popover 200ms 体验、悬停不消失
- 验证 R8 累计修复回顾，确认无回归

## R8-δ (Phase 2D 末) — 1 agent

**Agent G — Quant Final**：
- 端口 8091；`/tmp/AUDIT_R8d_final.md`
- 验证 Tier A vs Tier B 数值合理（同 token 差异范围）
- 验证 24+ commits 不引入回归（mock 跑一遍 R7 时已通过的 smoke test）
- 给最终 ship/needs-work verdict

---

# Part 8 — 风险登记表

| 风险 | 触发条件 | 缓解 |
|---|---|---|
| OKX rate-limit 429 | history extension 一次性大量请求 | CCXT 自带 backoff；retry 3 次后落 CG |
| Tier B Ridge ρ 没打过 Tier A | 历史数据样本不足或非平稳 | 接受失败，UI 隐藏 Tier B toggle，保 Tier A 作 production |
| stocks 周末数据空缺 | cross-section rank 计算时刻处理 | asset_class 彻底分开（Q6 决策）；stocks 仅周一-周五参与 ranking |
| LightweightCharts 切主题边界 | 旧版本 applyOptions 不支持某些字段 | fallback destroy+recreate，提示用户 zoom 状态丢失 |
| 16 个英文 label 不一致 | 多处 hardcode | COMPONENT_LABELS 单一来源 |
| 4 phase 跨度长出错回滚 | 中间某 phase 引入回归 | 每 phase 末 audit + 单 commit 可 revert |
| yfinance 突然降级 | Yahoo 后端变化，scrape 失败 | log warning + UI 标记 stocks 部分降级；Phase 3 备选用 Polygon API |
| `.env` 真实 key 误提交 | git add 时不小心 | .gitignore 已有 .env；pack_green_folder.sh 自动替换占位符 |
| Phase 2D Tier B 训练耗时长 | 24m × 12 fold = 288 月 Ridge | 单次训练 < 5 min（pandas in-memory） |
| data_coverage.json schema 改了破坏 UI | 后续加字段 | 前端用 optional chaining，缺字段 graceful degrade |

---

# Part 9 — 实施开始的第 0 件事

ExitPlanMode 通过后，按此顺序执行：

### Step 0：Plan 文件复制到项目根
```bash
cp "<source-plan-file>" "<project-root>/二期Plan-技术指标Dashboard.md"
cd <project root>
git add 二期Plan-技术指标Dashboard.md
git commit -m "docs: Phase 2 plan finalized"
```

### Step 1：R8-1A Day 1 第 1 个 commit
修 `backend/main.py:57` portability bug：

```python
# Before
from backend.config import PROJECT_ROOT
...
store = LocalStore(Path(PROJECT_ROOT) / "local_data")

# After
from backend.config import DATA_DIR
...
store = LocalStore(DATA_DIR)
```

提交：`fix R8-1A: backend/main.py honors DATA_DIR env var`

### Step 2：依此推进 4 phase × 5 day × ~5 commit/day

---

# Part 10 — Phase 3 候选（不在二期内）

记下来防忘：
- 港股集成（5-15 只 .HK ticker）
- L2 orderbook 流动性深度（CG /coins/{id}/tickers）
- TheGraph DEX OHLC（Tier 2）
- 真 Transformer composite（XGBoost + walk-forward）
- 完整 Methodology 专题页（rich page，含每个信号公式 + 历史表现）
- 实时（intraday）数据流，支持 5min/15min K线
- 链上数据扩展（whale alert、链上指标）
- scores_history 回填到 2020（基于扩展后的 OHLCV）

---

# 附录 A：用户决策快速查表

| Q# | 问题 | 选择 |
|---|---|---|
| Q1 | 综合评分 tier | A + B 都做 |
| Q2 | tooltip 风格 | 原生 + 局部 popover |
| Q3 | 浅色调色板气质 | TradingView 白色高级 |
| Q4 | Overall 卡布局 | Strategy A 全宽 hero |
| Q5 | 港股 | 跳过 |
| Q6 | crypto+stock 排名 | 彻底分开 |
| Q7 | Overall breakdown 内容 | 6 个 sleeve |
| Q8 | 实施顺序 | 架构先行 |
| Q9 | 港股 final | 跳过，默认 CRCL |
| Q10 | pre-2023 数据 | CCXT 极致 + CG fallback + 4-tier 元数据 |
| Q11 | 英化范围 | 含后端 comments + log |
| Q12 | 验收方式 | 每模块一轮 audit |
| Q13 | Tier 2/3 source | 跳过 |
| Q14 | 数据质量边界 UI | 评分区 Data Coverage 折叠 |
| Q15 | R6/R7 carryover | 全部修 |
| Q16 | Tier B 时机 | Phase 2D 同期 |

# 附录 B：本计划文档生成过程

- **Phase 1**: 3 个 Explore agent 并行调研（scoring/frontend/data layer），耗时 ~10 min
- **Phase 2**: 3 个 Plan agent 并行设计（quant/architect/designer），耗时 ~15 min
- **Phase 3**: 16 个澄清问题分 4 轮 AskUserQuestion，用户分别答复
- **Phase 4**: 整合所有发现 + 决策 → 本文档
- **Phase 5**: ExitPlanMode 等用户审批

文档总字符数：~32K（约 1400 行）。
