# Cloudflare Named Tunnel 部署指引（Mac mini 长期运行）

## 为什么要做这一步

`start.command` 默认用的是 **Cloudflare Quick Tunnel**（`cloudflared tunnel --url`）：
- ✅ 优点：零配置，开箱即用
- ❌ 缺点：URL 是临时随机的（`https://abc-def-1234.trycloudflare.com`），**cloudflared 进程一重启 URL 就变**
  - Mac mini 断网重连 → URL 变
  - cloudflared 自身崩溃自启 → URL 变
  - Mac mini 重启 → URL 变
  - 后果：**老的浏览器 tab 静默失效**，对方看到的 dashboard 直接卡死，但他自己不知道

适合：30 分钟内的临时演示。
**不适合**：长期挂在 Mac mini 上、给团队/LP 长期访问。

---

## 切到 Named Tunnel 后的好处

- URL **永久不变**（例如 `https://tech.iosg.vc` 或 `https://iosg-tech.cfargotunnel.com`）
- cloudflared 跟 launchd 一起开机自启，挂了自动重启
- 多人长期收藏的链接永远有效

---

## 一次性配置步骤（在 Mac mini 上做）

需要的前提：
- 已装 `cloudflared`（`brew install cloudflared`）
- 拥有 Cloudflare 账户（免费即可）
- 可选：你自己有的域名托管在 Cloudflare（如 `iosg.vc`）

### Step 1: 登录 Cloudflare

```bash
cloudflared tunnel login
```

会弹浏览器让你登录 Cloudflare 账户 + 选一个域名。
登录成功后凭证存在 `~/.cloudflared/cert.pem`。

### Step 2: 创建 Named Tunnel

```bash
cloudflared tunnel create iosg-tech-dashboard
```

输出会显示 tunnel UUID + 凭证文件路径（`~/.cloudflared/<uuid>.json`），记下来。

### Step 3: 绑定 DNS

**选项 A（用你自己的域名 — 推荐）**：

```bash
cloudflared tunnel route dns iosg-tech-dashboard tech.iosg.vc
```

之后访问 `https://tech.iosg.vc` 就是 dashboard。

**选项 B（不用自己域名，直接用 cloudflared 提供的子域名）**：

不跑 `route dns`，直接用 tunnel 自带的 `<uuid>.cfargotunnel.com` URL —
仍然永久稳定，但不漂亮。

### Step 4: 写配置文件

新建 `~/.cloudflared/config.yml`：

```yaml
tunnel: iosg-tech-dashboard
credentials-file: /Users/<your-user>/.cloudflared/<uuid>.json

ingress:
  - hostname: tech.iosg.vc          # ← 跟 Step 3 里 route dns 的域名一致
    service: http://localhost:8000
  - service: http_status:404
```

### Step 5: 手动测试一次

```bash
cloudflared tunnel run iosg-tech-dashboard
```

浏览器开 `https://tech.iosg.vc` 应该看到 dashboard。Ctrl+C 关掉。

### Step 6: 注册为开机自启服务

```bash
sudo cloudflared service install
```

之后即使 Mac mini 重启，cloudflared 也会跟随启动，挂掉自动重启。

---

## 改 `start.command`

Named Tunnel 装好之后，`start.command` 里的 `cloudflared tunnel --url ...` 那部分就**不需要了**（已经由 launchd 跑）。改成只起 Docker：

```bash
# 第 3 段（cloudflared）整段删除或注释掉，因为 cloudflared 已经在系统服务里跑了
```

或者保留 `start.command` 不动，把它作为开发/演示用的"一键短期 demo"，长期运行依赖 launchd 服务。

---

## 验证 launchd 已生效

```bash
# 看 cloudflared 进程
ps aux | grep cloudflared

# 看 launchd 状态
sudo launchctl list | grep cloudflared

# 看日志
tail -f /Library/Logs/com.cloudflare.cloudflared.out.log
```

---

## 部署架构对比

| 模式 | URL 稳定性 | 配置复杂度 | 适用场景 |
|---|---|---|---|
| **Quick Tunnel**（当前 `start.command`） | ❌ 每次变 | 0 步 | 临时演示 |
| **Named Tunnel + launchd** | ✅ 永远不变 | 6 步一次性 | Mac mini 长期运行、团队访问 |

---

## 常见坑

| 现象 | 原因 | 修复 |
|---|---|---|
| `cloudflared tunnel login` 弹浏览器但无法登录 | 内网不能访问 cloudflare.com | 切到能通的网络 |
| 登录后 `tunnel create` 报 "no zones" | 你 Cloudflare 账户下还没添加任何域名 | 用选项 B（不绑域名，用 cfargotunnel 子域名） |
| `route dns` 报 "zone not found" | 域名不在 Cloudflare 托管 | 把域名 NS 切到 Cloudflare，或用选项 B |
| `service install` 报权限不足 | 没用 sudo | `sudo cloudflared service install` |
| 跑起来后 `tech.iosg.vc` 502 Bad Gateway | Docker 容器没起 / 端口不是 8000 | `docker ps` 确认 + 调 `config.yml` 里 `service:` |

---

## 不做这一步的话

完全可以继续用 `start.command` 的 Quick Tunnel — 每次启动给你一个新 URL，复制发给对方就行。
适合：临时演示、临时分享、不想给长期固定 URL 的场景。

但如果你想做到"Mac mini 上跑一年，团队 / LP 永远用同一个 URL 访问"，就必须切到 Named Tunnel。
