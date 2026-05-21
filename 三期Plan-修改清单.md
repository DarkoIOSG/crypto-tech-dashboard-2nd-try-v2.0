# 三期 Plan — 修改清单（基于四方独立审查）

> **写于**: 2026-05-18
> **基线**: commit `b96f7e3` (二期完工 + Docker + 米兰 UI 微调)
> **审查来源**: 量化工程师 / 资深分析师 / 米兰设计师 / Google PM 四份独立 audit
> **原则**: Plan 用中文写；**所有用户可见 UI 全部英文**；不动数学内核（用户明确决定）
> **预计工作量**: 4-5 工作日
> **目标交付路径**: 路径 B —— 内部 + IOSG portfolio 受控演示 + LP 路演

---

## Part 0 — 决策前提（用户已拍板）

| 议题 | 用户决定 |
|---|---|
| Trend sleeve 5d 反方向 (ρ=-0.014) | **不修权重，不提"显著反向"** — Tier-A 0.40 权重作为"建议数据"保留 |
| 是否说"机器学习模型" | **不说** — 当前只是线性拟合，文案里不暗示 ML |
| Token loading 1-2s 卡顿 | **暂时保持** — 当前计算量小，不加 loading skeleton |
| 进入门槛 | **加密码页**，密码硬编码 `IOSG`（大写），任何人输入即可，无用户名 |

---

## Part 1 — 八大改动模块（按优先级）

### 模块 1：进入密码页（authentication gate）

**需求**: 任何人打开 dashboard，先看到一个密码输入页。密码硬编码 `IOSG`（4 个大写字母）。输入正确后 localStorage 记 token，永久免输（除非用户清浏览器缓存）。

**改动文件**：
- 新增 `frontend/login.html` — 全屏密码页，IOSG logo + 输入框 + Enter 提交
- 新增 `frontend/css/login.css` — 极简风（黑底大字，TradingView 登录页风格）
- 新增 `frontend/js/auth.js` — `localStorage.getItem('iosg-auth')` 校验 + `sessionStorage` fallback
- 修改 `frontend/index.html` — 顶部 inline script 加 auth guard：未登录 → `location.href = '/login.html'`
- 修改 `backend/main.py` — 加 `/login.html` 路由（静态文件 serve）；考虑 backend `/api/*` 是否也加 token 检查（**第一版只做前端拦截，后端不加 — 简单，演示场景够用**）

**UI 文案（英文）**：
```
┌──────────────────────────────┐
│                              │
│          IOSG                │
│   Crypto Tech Dashboard       │
│                              │
│  ┌────────────────────┐      │
│  │ Enter access code  │      │
│  └────────────────────┘      │
│                              │
│       [  Enter  ]            │
│                              │
│   Internal preview ·         │
│   Not investment advice      │
└──────────────────────────────┘
```

**验收**:
- 清浏览器 localStorage 后访问 `/` → 跳到 `/login.html`
- 输入 `IOSG` → 跳回 `/`，dashboard 正常加载
- 输入错（小写 `iosg` / 其他字符）→ 输入框抖动 + 提示 "Incorrect code"
- 输入正确后关闭浏览器再开 → 不用再输

**工作量**: 0.5 天

---

### 模块 2：法务底部 footer（不可少）

**需求**: 全站底部固定 footer，含免责声明 + 版本号 + 数据延迟说明。

**改动文件**：
- 修改 `frontend/index.html` — `</main>` 后加 `<footer class="site-footer">` 区块
- 修改 `frontend/css/styles.css` — `.site-footer` 样式（sticky bottom，与主题协调）

**UI 文案（英文，固定不变）**：
```
┌─ Footer ──────────────────────────────────────────────────────────┐
│ © 2026 IOSG · v2.5.0 · Last data refresh: 2 hours ago            │
│                                                                    │
│ This dashboard is a research preview for internal IOSG and        │
│ portfolio-company use only. The displayed scores, rankings and    │
│ backtests are illustrative and DO NOT constitute investment       │
│ advice, solicitation, or a recommendation to buy or sell any      │
│ asset. Past performance does not guarantee future results.        │
│ Crypto and US-equity prices may be delayed.                       │
└────────────────────────────────────────────────────────────────────┘
```

**验收**:
- 浅色 / 深色主题下都协调
- 移动 viewport (375px) 文字不溢出
- 版本号取自 `package.json` 或后端 `/api/system/health` 返回字段

**工作量**: 1-2 小时

---

### 模块 3：数据自动刷新（系统启动 + 每日 9 点）

**需求**: 两个机制叠加：
1. **系统启动时检测**: 如果 `last_ohlcv_update` 不是今天，主动触发一次 daily update（Yahoo + CCXT）
2. **每天早 9 点 Asia/Shanghai 自动 refresh**: 现有 APScheduler cron 已经是 08:30 + 08:35，改成 **09:00 + 09:05** 更符合"早 9 点左右"用户预期
3. **boot-time backfill**: 如果数据缺口 ≥ 2 天，自动 fill-the-gap 而不只拉今天

**改动文件**：
- 修改 `backend/main.py` lifespan：boot 时读 `last_update.json`，对比 `today - last_ohlcv_update`，如果 ≥ 1 天，立即在 background task 跑 `run_daily_update` + `run_stocks_daily_update`
- 修改 `backend/data/fetcher.py` `run_daily_update`：lookback_days 从 5 改为 `max(5, days_since_last_update + 2)` 处理多天缺口
- 修改 `.env`：`UPDATE_HOUR=9`, `UPDATE_MINUTE=0`
- 修改 `docker-compose.yml` / 文档：相应注释更新

**UI 文案（英文，topbar）**：
```
当前: "last update: 2026-05-15T16:25:27"   ← 原始 ISO，丑
改后: "Updated 2 hours ago"                ← human-friendly
```
鼠标 hover 显示完整 ISO 时间戳 (`title=`).

**当前时间获取**：
- 前端 JS 直接用 `new Date()` (浏览器本地时间，足够准确)
- 后端用 `datetime.now(tz=ZoneInfo("Asia/Shanghai"))`
- **不调用外部公开 NTP API** —— 服务器系统时间已经自动同步 NTP，再调外部 API 是过度工程

**验收**:
- 故意把 `last_update.json` 改成 3 天前 → 启动服务 → 5 秒内开始自动 backfill
- topbar 时间从 ISO 变成 "Updated X hours/minutes ago"
- 早 9:00 cron 真的触发（看 log）

**工作量**: 1 天

---

### 模块 4：美股 OHLC endpoint 修复

**需求**: 现在 `curl /api/ohlc/MSTR` 返回 0 行 K 线，但磁盘上 `local_data/ohlcv/MSTR.csv` 是有数据的。endpoint bug。

**调查 + 修复步骤**：
1. `curl http://127.0.0.1:8000/api/ohlc/MSTR` 看真实返回
2. 看 `backend/api/routes_ohlc.py`，找 `/api/ohlc/{cg_id}` handler
3. 大概率是 `validate_cg_id` 拒绝了大写 ticker，或者 `data_service.get_ohlcv` 找不到 MSTR.csv
4. 同样修 `/api/indicators/MSTR` 如果也 broken

**改动文件**：
- 修改 `backend/api/routes_ohlc.py`（或 routes_indicators.py） — 让大写 ticker 也能通过
- 修改 `backend/services/data_service.py:get_ohlcv` — 确认 `local_data/ohlcv/{cg_id}.csv` lookup 兼容大写

**验收**:
- `curl /api/ohlc/MSTR?days=365` → ≥ 200 candles，从 2019-12-30 到今天
- `curl /api/ohlc/COIN` / `CRCL` / `MARA` 都正常
- 前端选 MSTR / COIN / CRCL → K 线图正常显示

**工作量**: 2-4 小时

---

### 模块 5：asset_class 命名统一

**需求**: 当前代码混用 `us-stock` / `stock` / `us_stock`，filter 不通。

**调查**:
```bash
grep -rn "asset_class" backend/ frontend/ | grep -E "stock|stocks"
```
找出所有出现位置，统一成 **`us-stock`**（中划线，与 stocks_universe.csv 一致）。

**改动文件**（grep 出来后逐个改）：
- `backend/services/data_service.py`
- `backend/api/routes_*.py` 
- `frontend/js/app.js`
- `frontend/js/api.js`
- `frontend/index.html`（tab-btn data-tab）
- 任何包含 "stock" filter 的 URL handler

**验收**:
- `grep -rn "'stock'\|\"stock\"\|=stock\b" backend/ frontend/` → 0 hits（只允许 us-stock）
- `curl /api/scores?asset_class=us-stock` 返 38 个 stock
- `curl /api/scores?asset_class=stock` 返空（明确告知是错的 asset_class，不是 silent fallback）

**工作量**: 1-2 小时

---

### 模块 6：量化内核 disclaimer 文案重写

**需求**:
- Tier-A 0.40 trend 权重保留不动
- 不提"显著反向"任何字眼
- 移除任何"机器学习"、"AI" 暗示词 → 改成"线性加权" / "rule-based"
- 但**保留** Tier-B / Calibrated 的诚实标注 — 它们是研究实验，accept=false 是诚实结果

**改动文件**：
- `frontend/js/app.js renderTierBBanner()` — 重写 banner 文案
- `frontend/index.html` — 所有 info-mark tooltip 含 "ML" / "machine learning" 的地方改写
- `backend/scoring/explainers.py` — TREND/REVERSAL/OVERALL explainer 的 strengths/weaknesses 不提"反方向"
- `README.md` — 移除"ML scoring" / "AI" 字眼

**UI 文案改写示例**：
```
当前 banner: "Theory weights · research-only (Sharpe 5d: theory -0.16 vs cal 0.07)"
改后:        "Linear-weighted composite · research preview"

当前 explainer Trend Weaknesses: "5d horizon Spearman is statistically reversed..."
改后: "Optimized for multi-week to multi-month positioning; short-term swing 
       signals are noisier. Cross-sectional ranking is universe-relative."
```

**关键原则**:
- 不撒谎（不说 "AI-powered"），但也不主动暴露反方向数学（用户决定）
- 把焦点定位在 **multi-week / multi-month** horizon
- "linear-weighted" 是真实描述，比"AI"更诚实

**验收**:
- grep "AI\|machine learning\|ML" frontend/ README.md → 0 hits（或只在内部 docs/scoring_audit/ 里）
- banner 不显示负 Sharpe 数字
- 但 `/api/scoring/tier_b` + `/api/scoring/calibrated` endpoint 数据保持完整（内部研究人员仍能 GET）

**工作量**: 2-3 小时

---

### 模块 7：视觉打磨（米兰设计师 5 件）

**需求**: 米兰设计师评分 59/80，给了 5 个具体改动让评分 →64+ 进 LP 区。

#### 7.1 — 5 accent 同源去饱和
- 当前 5 accent 饱和度从 47% 跳到 100%，不统一
- 改 `frontend/css/styles.css :root` + light theme 块，让 5 accent 在 HSL 上 S=60-75% 区间

**示例**（仅示意，需要设计师 fine-tune）：
```css
/* before */
--accent-green: #26a69a;   /* S=62%, OK */
--accent-red:   #ef5350;   /* S=83%, 偏高 */
--accent-yellow:#f7c948;   /* S=92%, 太跳 */
--accent-purple:#ab47bc;   /* S=53%, 偏低 */

/* after — 同源饱和度 60-75% */
--accent-green: #26a69a;
--accent-red:   #d85a58;
--accent-yellow:#d4ae3a;
--accent-purple:#9a4eb0;
```

#### 7.2 — 12 indicator panel 默认折叠
- 当前 12 panel 全开，首屏窒息
- 首屏只展开 4 个：**SMA Cross / RSI / MACD / Bollinger**
- 其余 8 个折进 `.more-indicators <details>`（已有结构，只需迁移）

**改动**: `frontend/index.html` 重排 panel 位置（DOM 顺序）

#### 7.3 — Brand 升级
- 当前 brand = `IOSG Crypto Tech Dashboard` 15px system font
- 改成两层：
  ```
  IOSG          ← 18px bold tabular-nums
  Tech Dashboard ← 11px upper-case letter-spaced
  ```
- 不加 SVG logo（保持简洁）

**改动**: `frontend/index.html` topbar-left 区 + `frontend/css/styles.css .brand`

#### 7.4 — Reversal badge 不用紫色
- 当前 Reversal 用 `--accent-purple`（紫）
- 改成中性灰 `--text-primary` 数字 + 标签灰
- 紫色保留给 KDJ J line 等"真的"紫色含义元素

**改动**: `frontend/css/styles.css .score-badge.reversal span`

#### 7.5 — 字号砍到 5 档
- 当前 9/10/11/12/13/14/15/38/56 px 散乱
- 统一成 **5 档**: 10 / 12 / 14 / 38 / 56 (micro / caption / body / sub-hero / hero)
- 砍掉中间过渡值（9 → 10，11 → 12，15 → 14）

**改动**: 全局 `frontend/css/styles.css` grep `font-size: \d+px` 后归一

**验收**:
- 主页打开第一屏 indicator panel 数量 ≤ 4
- 5 accent 在 dark / light 双主题都协调（设计师肉眼判断 OR Python HSL diff）
- brand 看着像金融工具不像 demo
- Reversal 数字不再紫色

**工作量**: 1 天（米兰审美 fine-tune）

---

### 模块 8：补漏（PM 提的边角）

#### 8.1 — URL 大写 token 友好降级
- 当前 `/#token=ETH`（大写）静默 fallback 到 BTC
- 改成：toast 提示 "Token 'ETH' not found; matched 'ethereum'" + 自动跳

**改动**: `frontend/js/app.js init()` token 匹配逻辑加大小写不敏感 + 提示

#### 8.2 — favicon + social meta tags
- 当前没 favicon（浏览器 tab 显示通用图标）
- 加一个 IOSG 字 favicon（16×16 + 32×32 PNG 或 SVG）
- `<meta property="og:title" content="IOSG Crypto Tech Dashboard">` 等 social meta

**改动**: 新增 `frontend/favicon.ico` + `frontend/index.html <head>`

#### 8.3 — `?token=ETH` 大写匹配
（同 8.1）

#### 8.4 — 错误页（404 / 数据缺失）
- 选一个不存在的 token id → 当前可能白屏或卡住
- 加 graceful empty state："Token not found. Try BTC / ETH / SOL."

**改动**: `frontend/js/app.js selectToken` 或 `onTokenChange` 错误分支

**工作量**: 半天

---

## Part 2 — 工作量汇总 + 优先级

| 模块 | 工作量 | 优先级 | 是否阻断 LP 演示 |
|---|---|---|---|
| 1. 密码页 | 0.5 天 | P0 | ✓ 阻断 |
| 2. 法务 footer | 2 小时 | P0 | ✓ 阻断 |
| 3. 数据自动刷新 | 1 天 | P0 | ✓ 阻断（数据陈旧问题）|
| 4. 美股 OHLC 修复 | 2-4 小时 | P0 | ✓ 阻断（美股不能用）|
| 5. asset_class 命名统一 | 1-2 小时 | P1 | 边角 |
| 6. 量化 disclaimer 文案 | 2-3 小时 | P0 | ✓ 阻断（公开看到负 Sharpe）|
| 7. 视觉打磨 5 件 | 1 天 | P1 | 不阻断但 LP 感受会差 |
| 8. PM 补漏 4 件 | 0.5 天 | P2 | nice-to-have |
| **合计** | **4-5 天** | | |

---

## Part 3 — 执行顺序建议（线性）

```
Day 1
├─ 上午: 模块 1 密码页（0.5d）
└─ 下午: 模块 2 footer（2h）+ 模块 6 量化 disclaimer 文案（3h）

Day 2
├─ 上午: 模块 3 数据自动刷新（boot + cron + 时间显示）
└─ 下午: 模块 3 继续 + 测试

Day 3
├─ 上午: 模块 4 美股 OHLC 修复（2-4h）+ 模块 5 asset_class 统一（1-2h）
└─ 下午: 模块 7.1 + 7.2 accent + panel 折叠

Day 4
├─ 上午: 模块 7.3 brand + 7.4 Reversal + 7.5 字号
└─ 下午: 模块 8 PM 补漏

Day 5
├─ 上午: 综合 smoke test + 端到端验收（重新跑 4 方 audit checklist）
└─ 下午: commit 推送 + 写 changelog
```

---

## Part 4 — 验收 / Audit checklist

每个模块改完都要跑这些：

### 通用 sanity
- [ ] 服务启动无 error
- [ ] 17 个 endpoint 全 200
- [ ] JS 9 文件 syntax 通过
- [ ] 0 中文字符在 backend / frontend 源码
- [ ] light + dark 主题都正常切

### 模块 1 验收
- [ ] 清 localStorage → 自动跳 `/login.html`
- [ ] 输入 `IOSG` → 跳回 `/`
- [ ] 输入 `iosg` / 其他 → 拒绝 + 提示

### 模块 2 验收
- [ ] footer 在浅 + 深色都协调
- [ ] 移动 375px viewport 不溢出
- [ ] 版本号正确

### 模块 3 验收
- [ ] 把 last_update 改 3 天前，启动 → 5 秒内 backfill
- [ ] 早 9:00 cron 触发
- [ ] topbar 时间显示"Updated 2 hours ago"

### 模块 4 验收
- [ ] `/api/ohlc/MSTR` 返回 ≥ 200 candles
- [ ] 前端选 MSTR / COIN / CRCL → K 线显示

### 模块 5 验收
- [ ] `grep us_stock\|=stock\b` → 0 hits
- [ ] `?asset_class=us-stock` 返 38
- [ ] `?asset_class=stock` 返空 / 报错（不静默）

### 模块 6 验收
- [ ] grep "AI\|machine learning" frontend/ README → 0
- [ ] banner 文案 "Linear-weighted composite · research preview"
- [ ] 没暴露任何负 Sharpe 数字

### 模块 7 验收
- [ ] 5 accent HSL S 都在 60-75%
- [ ] 首屏 ≤ 4 个 indicator panel
- [ ] brand 视觉升级
- [ ] Reversal 数字不紫
- [ ] 字号全局只有 5 个值

### 模块 8 验收
- [ ] favicon 在浏览器 tab 显示
- [ ] og:title meta 存在
- [ ] `#token=ETH` 大写 → 提示 + 跳 ethereum
- [ ] 选不存在 token → 不白屏

---

## Part 5 — 不做的事（明确范围）

为避免范围蔓延，本期 **不做**：

- ❌ 改 Tier-A 0.40 trend 权重（用户决定保留）
- ❌ UI 暴露 trend 5d 反方向警示（用户决定不提）
- ❌ UI 暴露 survivorship bias（用户没明确要，等后续）
- ❌ Tier-D point-in-time universe rebuild（Phase 3 backlog）
- ❌ Rate-limit / auth 系统化（密码页够用了，没有真正用户管理）
- ❌ 后端 token 验证（前端拦截够用，演示场景不需要）
- ❌ pytest CI suite（团队接手再做）
- ❌ Loading skeleton（用户决定暂时保持）
- ❌ Sharpe / Calibrated 数学修正（用户决定先 disclaimer，不动权重）
- ❌ 港股 universe（Phase 3 backlog）

---

## Part 6 — 风险登记

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| 模块 3 早 9:00 cron 跟 host 时区不一致 | 中 | 数据延迟 | docker-compose 加 `TZ=Asia/Shanghai` env |
| 模块 4 美股 OHLC bug 比预想复杂 | 低 | 多花半天 | 调试时间预留 |
| 模块 7 设计师 fine-tune 主观 | 中 | 反复改 | 第一版按本 plan 数字硬来 |
| 密码 IOSG 太弱被爆破 | 高（如果公开） | 0 安全 | 仅限受控分享，不发推特 |
| Tier-B banner 文案改得太软导致内部研究人员看不到诚实信息 | 低 | 透明度损失 | API endpoint 保留完整数据，只前端 banner 软化 |

---

## Part 7 — 完工标志

执行完本 plan，系统具备：

✅ **进入门**: 密码 IOSG  
✅ **法务**: footer disclaimer + 版本号  
✅ **数据**: 自启自动 backfill + 早 9:00 cron + human-friendly 时间显示  
✅ **美股**: MSTR / COIN / CRCL K 线可看  
✅ **命名**: asset_class 统一 us-stock  
✅ **文案**: 不提 ML / 反方向，定位"线性加权研究预览"  
✅ **视觉**: 米兰设计师 5 件改完，评分 64+/80  
✅ **边角**: favicon / social meta / 大写 token 友好降级 / 404 不白屏  

可以发给 LP / IOSG portfolio CTO / 受控演示，不可以发推特 / PH。

---

**下一步**: 用户审阅本 plan → 拍板"开始执行" → 我按 Day 1-5 顺序逐模块做。
