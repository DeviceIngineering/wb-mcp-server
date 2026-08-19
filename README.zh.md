[Русский](README.md) · [English](README.en.md)

# WB MCP Server

[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)
[![MCP tools](https://img.shields.io/badge/MCP%20tools-202-orange.svg)](docs/tools.md)
[![Transport](https://img.shields.io/badge/transport-SSE-lightgrey.svg)](#工作原理)

**在与 AI 助手的对话中管理你的 Wildberries 店铺。**
202 个覆盖 Wildberries Seller API 的工具——商品卡片、价格、广告、发货、评价、财务、
数据分析——可供 Claude、Cursor、Copilot、Gemini CLI 以及任何其他 MCP 客户端调用。
面向在 Wildberries（俄罗斯最大的电商平台）经营一个或多个卖家账号、
不愿在卖家后台里反复点击的商家。

> 这是作者本人每天在用的工作工具，按照作者自身的需要来更新，
> 详见[更新与支持](#更新与支持)。

```
你：我有哪些商品卡片被封了，原因是什么？
你：列出本周所有广告计划的广告费占比，把高于 15% 的暂停掉。
你：现在哪些仓库的入库系数是 0 或 1？
你：给所有新的 5 星评价回复一句感谢。
```

![WB MCP Server 控制台](docs/img/dashboard.png)

---

## 功能概览

202 个工具，按 Wildberries Seller API 的业务板块分组。
完整编号列表和每个工具的说明见 **[docs/tools.md](docs/tools.md)**。

| 板块 | 工具数 | 覆盖内容 |
|---|---:|---|
| 商品卡片 | 26 | 卡片列表与详情、创建与更新、SEO 文案、属性、条码、图片视频、标签、回收站、**存在错误或被封禁的卡片** |
| 价格与折扣 | 7 | 当前价格、设置价格与折扣、价格隔离区（quarantine）、WB Club（平台付费会员折扣）、B2B 价格、上传状态 |
| 促销活动 | 7 | 促销日历、自动促销、"WB 已自动把哪些商品加入活动"的审计、参加与退出活动 |
| 广告 | 22 | 计划列表与创建、投放数据与广告费占比、出价与出价建议、关键词聚类与否定词、账户余额与充值 |
| 数据分析 | 25 | 销售漏斗 v3（单品的曝光→加购→下单转化）、按天历史、库存、反欺诈、付费入库、量方处罚、品牌份额、分地区销售、搜索词 |
| 统计 | 3 | 销售、订单、库存（statistics-api） |
| FBS 订单 | 29 | 新的与全部备货任务、状态、取消、面单、发货批次、纸箱、仓库通行证、KIZ 商品追溯码（俄罗斯强制商品标识）。FBS = 卖家备货、平台揽收 |
| DBS 订单 | 10 | 卖家自行配送：订单、状态、操作、配送日期、元数据 |
| 自提（click & collect） | 9 | 自提订单、买家身份确认、操作与元数据 |
| FBW 入仓 | 6 | 发往 WB 仓库的入库计划、计划内商品、仓库列表、**未来 14 天的入库系数** |
| 卖家仓库与库存 | 8 | 卖家自有仓库、库存的写入与读取 |
| 财务 | 7 | 结算报表、明细、收单（acquiring）、余额、卖家资料 |
| 资费与仓储 | 6 | 纸箱与托盘资费、退货资费、佣金、FBW 干线运输、付费仓储 |
| 评价与提问 | 18 | 评价与提问、回复、按周期计数、归档、置顶评价、卖家评分 |
| 退货 | 3 | 退货申请、处理申请、退货报表 |
| 买家聊天 | 4 | 会话、消息事件、发送消息、下载附件 |
| 文档 | 4 | 文档类别、列表、单个与批量下载 |
| 用户 | 2 | 员工与邀请 |
| WB Jam | 1 | WB Jam 订阅状态（平台的付费数据分析服务） |
| 店铺 | 1 | 已接入的卖家账号列表 |
| 自诊断 | 4 | 整体自检、令牌解析、工具失效检测、WB API 公告 |

同类服务器通常没有的三点：

- **多店铺。** 每次调用都接受 `shop_id`，因此两个 WB 卖家账号可以在同一个对话里共存。
  只有一个店铺时，`shop_id` 可以完全省略。
- **WB API 自诊断。** 服务器会自己 ping WB 的各个主机，按 API 分类各发一个轻量探测请求，
  解析令牌的有效期与权限，并标记"失效"：某个工具原本正常、现在持续报错——
  这通常说明 WB 改了 API。
- **令牌加密。** WB 令牌以加密形式（Fernet）保存，而不是明文写在客户端配置里。

## 快速上手

需要 Docker（Docker Desktop 或 OrbStack）和一个 Wildberries Seller API 令牌。

> **首次运行前请注意。** 目前从零构建会拉取 `mcp` 2.x 库，服务器无法用它启动。
> 绕过方法与详情见[工作原理](#工作原理)中关于 `mcp` 版本的说明。

```bash
git clone https://github.com/DeviceIngineering/wb-mcp-server.git
cd wb-mcp-server
cp .env.example .env          # 本地运行保持默认即可
docker compose up -d --build
```

检查：

```bash
curl -s http://localhost:8001/api/health
# {"status":"ok","auth_enabled":false,"health_check_interval_min":30,...}
```

启动后你会得到：

| 地址 | 说明 |
|---|---|
| <http://localhost:8001> | 控制台：工具调用记录、错误、响应耗时 |
| <http://localhost:8001/shops> | 店铺管理：添加 WB 卖家账号、测试令牌 |
| <http://localhost:8001/diagnostics> | 自诊断：令牌、WB 主机 ping、探测请求、历史记录 |
| <http://localhost:8001/api/health> | 供外部监控使用的 JSON 摘要 |
| `http://localhost:8001/sse` | **MCP 端点**，填进客户端配置的就是它 |

接下来：

1. 打开 <http://localhost:8001/shops> → **Добавить магазин**（添加店铺）→ 粘贴 WB 令牌
   → **Проверить**（测试）。令牌在 WB 卖家后台（seller.wildberries.ru）里获取：
   **Настройки → Доступ к API → Создать токен**（设置 → API 访问 → 创建令牌）。
   有效期 180 天，剩余天数会显示在自诊断页面上。
2. 接入 MCP 客户端——见下一节。
3. 对助手说："列出我的 Wildberries 店铺"，应当触发 `wb_list_shops` 工具。

启动命令逐项说明：

| 参数 | 作用 |
|---|---|
| `up` | 启动 `docker-compose.yml` 中定义的服务 |
| `-d` | 后台运行，不占用终端 |
| `--build` | 从 `Dockerfile` 构建镜像——首次运行和代码更新后需要 |

停止：`docker compose down`（数据保留在 `wb_data` 卷中）。
日志：`docker compose logs -f`。

<details>
<summary>不使用 Docker 运行</summary>

```bash
git clone https://github.com/DeviceIngineering/wb-mcp-server.git
cd wb-mcp-server
python3 -m venv .venv && source .venv/bin/activate
pip install .
DATA_DIR=./data PORT=8001 python -m wb_mcp.app
```

这里必须指定 `DATA_DIR`：默认写入 `/data`，那是容器内部的路径。
</details>

## 接入各个客户端

服务器通过 **SSE** 提供 MCP：`GET /sse` 是事件流，`POST /messages` 用于客户端发消息。
各客户端对 SSE 的支持程度不同，因此每个客户端都有单独的说明文档，
其中包含 macOS、Linux、Windows 三种系统下的配置文件路径、可直接粘贴的 JSON，
以及带鉴权令牌和不带令牌两种写法。

> `docs/` 目录下的客户端说明目前**只有俄文版**。不过其中的配置都是现成的 JSON、
> 文件路径和命令行参数，不依赖语言也能看懂。

| 客户端 | 是否直接支持 SSE | 说明文档 |
|---|---|---|
| Claude Code | 是 | [docs/claude-code.md](docs/claude-code.md) |
| Claude Desktop | 否 → 需 `mcp-remote` 桥接或本地 stdio | [docs/claude-desktop.md](docs/claude-desktop.md) |
| Cursor | 是 | [docs/cursor.md](docs/cursor.md) |
| Windsurf | 是 | [docs/windsurf.md](docs/windsurf.md) |
| VS Code（GitHub Copilot） | 是 | [docs/vscode-copilot.md](docs/vscode-copilot.md) |
| Cline | 是 | [docs/cline.md](docs/cline.md) |
| Continue.dev | 是 | [docs/continue.md](docs/continue.md) |
| Zed | 支持按 URL 接入；官方未声明支持 SSE | [docs/zed.md](docs/zed.md) |
| JetBrains AI Assistant | 是（SSE 作为遗留传输方式） | [docs/jetbrains.md](docs/jetbrains.md) |
| Gemini CLI | 是 | [docs/gemini-cli.md](docs/gemini-cli.md) |
| Codex CLI | 否 → 需 `mcp-remote` 桥接 | [docs/codex.md](docs/codex.md) |

总览与兼容性表格见 [docs/README.md](docs/README.md)。

最简单的一种，Claude Code：

```bash
claude mcp add --transport sse wildberries http://localhost:8001/sse
```

## 多店铺与安全

**多个卖家账号。** 店铺在 `/shops` 页面添加，每个店铺有自己的 `shop_id`。
`wb_list_shops` 返回店铺列表；202 个工具中有 200 个把 `shop_id` 作为第一个参数
（例外是 `wb_list_shops` 和 `wb_degradations`）。
只有一个店铺时可以省略该参数，服务器会自动填入唯一可用的那个。

**令牌存放位置。** 在 `wb_data` 卷中（容器内路径为 `/data`）：

- `shops.json` —— 店铺信息，令牌用 Fernet 加密；
- `.encryption_key` —— 加密密钥，首次启动时生成；
- `stats.db` —— SQLite，保存调用统计与自诊断历史。

密钥与加密数据放在一起，因此加密能防止 `shops.json` 单个文件意外泄露
（备份、复制粘贴），但防不住拿到整个卷的人。迁移数据要整卷迁移——见 [DEPLOY.md](DEPLOY.md)。

**MCP 鉴权。** `.env` 中的 `MCP_AUTH_TOKEN` 变量：

```bash
openssl rand -hex 32   # 把生成的值填进 .env → MCP_AUTH_TOKEN=
docker compose up -d
```

- 留空（默认）—— 只要能访问该端口，任何人都能连 `/sse`；
- 已设置 —— 客户端必须发送 `Authorization: Bearer <令牌>`，**或者**在 URL 里带
  `?token=<令牌>`。后一种写法可以救那些无法自定义请求头的客户端。

**服务器不负责的事：**

- Web 界面（`/`、`/shops`、`/diagnostics`）和 `POST /messages` **没有**令牌保护：
  只有 `GET /sse` 会校验。请把 8001 端口留在可信网络内。
- 8001 端口不适合直接暴露到公网。需要远程访问请用 Tailscale 或 VPN。
- 服务器不终止 HTTPS。需要对外提供 TLS，请在前面加反向代理。

## 工作原理

一个 Docker 容器，里面是一个同时扮演两种角色的 FastAPI 应用：
基于 SSE 的 MCP 服务器，以及一个简单的 Web 界面。逐个文件说明：

- **`wb_mcp/server.py`** —— MCP 服务器本体。`TOOLS` 列表包含 202 个 `Tool` 对象
  （名称、描述、参数的 JSON Schema），客户端调用 `tools/list` 拿到的就是它。
  调用通过三个字典分发：`NO_CLIENT_DISPATCH`（不需要访问 WB）、
  `CLIENT_DISPATCH`（需要店铺的 HTTP 客户端）、`SHOP_DISPATCH`（还需要 `shop_id`）。
  stdio 入口函数 `main()` 也在这里，供只支持 stdio 的客户端使用。
- **`wb_mcp/client.py`** —— 面向 14 个 Wildberries 主机的 HTTP 客户端。
  每个店铺一个 `WBClient`，内部是带令牌的 `httpx.AsyncClient`；
  客户端按 `shop_id` 缓存在连接池里。
- **`wb_mcp/app.py`** —— FastAPI：MCP 用的 `GET /sse` 与 `POST /messages`、
  控制台/店铺/自诊断三个页面、`/api/*` JSON 接口、`MCP_AUTH_TOKEN` 校验，
  以及后台健康检查循环。
- **`wb_mcp/settings.py`** —— 店铺与密钥：读写 `shops.json`、Fernet 加密、
  从旧的单店铺 `settings.json` 迁移、在界面上对令牌打码。
  另有兜底逻辑：设置了 `WB_API_TOKEN` 环境变量时，会出现一个名为 `default` 的店铺。
- **`wb_mcp/diagnostics.py`** —— ping WB 主机、解码 JWT 令牌（有效期、权限、沙箱标记）、
  "探测请求"（每个 API 分类发一个轻量真实请求）、WB 公告。
- **`wb_mcp/stats.py`** —— 通过 aiosqlite 使用 SQLite：每次工具调用都会记录耗时、
  成功与否和 `shop_id`；失效检测器和健康检查历史都来自这里。
- **`wb_mcp/templates/`** —— 三个基于 PicoCSS 的页面，无需前端构建。

一些不那么显而易见的地方：

- **只有一个店铺时 `shop_id` 会自动填入。** 日常很方便，但一旦添加第二个账号，
  不带 `shop_id` 的调用就会开始返回"Укажите shop_id"（请指定 shop_id）。
- **每次调用都会写入统计**，包括失败的调用。失效检测器正是靠它工作：
  "以前能用、现在持续失败"说明 WB 改了 API，而不是你写错了。
  查看方式：`wb_degradations` 工具或控制台页面。
- **每 30 分钟一次的后台自诊断**会向 WB 发真实请求，消耗你的调用配额。
  如果这带来困扰，在 `.env` 里设置 `HEALTH_CHECK_INTERVAL_MIN=0`。
- **返回原样的数据**：WB 的原始 JSON，不做二次封装。这让工具行为可预测，
  但大体量报表最好带上过滤条件，否则返回内容会占满模型的上下文。
- **容器日志在每条 MCP 消息时都会打印** `RuntimeError: Unexpected ASGI message
  'http.response.start' sent, after response already completed`。
  原因是 `POST /messages` 被包在 FastAPI 路由里，而不是作为 ASGI 应用挂载。
  出现该日志时消息其实已被接收（`202 Accepted`）并处理完毕——
  用官方 Python MCP 客户端（`mcp` 1.29.0）实测，`initialize`、`tools/list`
  和工具调用都正常。但每次 POST 后连接会断开，因此复用 keep-alive 连接的客户端
  可能会出问题。这条日志属于预期现象，不代表服务坏了。
- **`mcp` 库版本——已知问题。** 服务器基于 `mcp` 1.x 的装饰器 API（`@app.list_tools()`）
  编写，该 API 在 `mcp` 2.0 中被移除。`pyproject.toml` 里写的是 `mcp[cli]>=1.0.0`，
  没有上界，所以全新安装会拉到 `mcp` 2.x，启动时报
  `AttributeError: 'Server' object has no attribute 'list_tools'`。
  在 `pyproject.toml` 加上限制之前，请显式安装 1.x：

  ```bash
  pip install "mcp[cli]<2.0.0"          # 本地运行
  ```

  使用 Docker 时，在 `Dockerfile` 的 `pip install .` 之后加上同一行，
  或者等待仓库修复。

环境变量：

| 变量 | 默认值 | 含义 |
|---|---|---|
| `WB_API_TOKEN` | 空 | `default` 店铺使用的令牌；通过 `/shops` 添加店铺更方便 |
| `MCP_AUTH_TOKEN` | 空 | `/sse` 的 Bearer 令牌；留空表示关闭鉴权 |
| `HEALTH_CHECK_INTERVAL_MIN` | `30` | 后台自诊断间隔（分钟），`0` 表示关闭 |
| `DATA_DIR` | `/data` | 存放 `shops.json`、`.encryption_key`、`stats.db` 的目录 |
| `PORT` | `8001` | HTTP 服务端口 |

## Wildberries API 的限制

这些是 WB 平台自身的限制，不是本服务器的限制——但助手会经常撞上它们，
提前知道为好。

- `GET /adv/v3/fullstats`（广告投放数据）—— **每分钟 3 次请求**，查询区间不超过 31 天。
- 销售漏斗 v3 —— **每分钟 3 次请求**；按天的历史数据最多只能取最近一周。
- `/ping` —— 每台主机 30 秒内 3 次请求（后台自诊断已考虑这一点）。
- **任何 4XX 响应都会按 10 次请求计入配额**（该规则自 2026-06-04 起生效）。
  循环里带一个错参数，配额就用光了。
- `reportDetailByPeriod` 将于 2026-07-15 下线；服务器已改用 finance-api，
  并保留了回退到旧端点的逻辑。
- FBW 入库计划无法通过 API 创建，只能在卖家后台操作。`wb_fbw_*` 系列工具仅供查询。
- WB 令牌有效期 180 天。剩余天数可通过 `wb_token_info` 和 `/diagnostics` 页面查看。
- WB 返回 `429` 表示触发限流，不是故障。过一分钟重试即可。

以上内容依据 dev.wildberries.ru 官方文档核对，截至 2026 年 6 月。

## 技术参考

### Wildberries Seller API 主机

| API | 基础 URL |
|-----|-------------|
| Content | content-api.wildberries.ru |
| Marketplace (FBS/DBS/DBW) | marketplace-api.wildberries.ru |
| Supplies (FBW) | supplies-api.wildberries.ru |
| Statistics | statistics-api.wildberries.ru |
| Analytics | seller-analytics-api.wildberries.ru |
| Prices | discounts-prices-api.wildberries.ru |
| Promotions calendar | dp-calendar-api.wildberries.ru |
| Advert | advert-api.wildberries.ru |
| Finance | finance-api.wildberries.ru |
| Feedbacks + Questions | feedbacks-api.wildberries.ru |
| Returns | returns-api.wildberries.ru |
| Tariffs / News / Seller | common-api.wildberries.ru |
| Buyer Chat | buyer-chat-api.wildberries.ru |
| Documents | documents-api.wildberries.ru |

### 自诊断

- **`/diagnostics` 页面** —— 按店铺展示：令牌有效期与权限、所有 WB API 主机的 ping、
  分类探测请求、检查历史，以及"立即检查"按钮。
- **后台自动检查**，每 `HEALTH_CHECK_INTERVAL_MIN` 分钟一次。
- **失效检测器** —— 在控制台上高亮那些不再正常工作的工具。
- **MCP 工具**：`wb_diagnostics`、`wb_token_info`、`wb_degradations`、`wb_api_news`。
- **`GET /api/health`** —— 供外部监控的 JSON 摘要。
- **`POST /api/diagnostics/run`** —— 立即对所有店铺跑一次检查。
- **`GET /api/diagnostics/<shop_id>`** —— 单个店铺的完整诊断。

### 项目结构

```
wb-mcp-server/
├── docker-compose.yml          # 端口 8001，wb_data 卷
├── Dockerfile                  # python:3.12-slim
├── pyproject.toml
├── DEPLOY.md                   # 部署到独立机器、迁移数据
├── docs/                       # 客户端接入说明 + 工具清单
└── wb_mcp/
    ├── server.py       # MCP 服务器：202 个工具、分发表、stdio 模式
    ├── client.py       # 14 个 Wildberries API 的 HTTP 客户端
    ├── app.py          # FastAPI：SSE + Web 界面 + 鉴权 + 健康检查循环
    ├── diagnostics.py  # ping、JWT 解码、探测请求、API 公告
    ├── settings.py     # 店铺与密钥（Fernet）
    ├── stats.py        # 调用统计与检查历史（SQLite）
    └── templates/      # PicoCSS：dashboard、diagnostics、shops
```

### 部署

把服务器迁到独立机器、迁移店铺数据、配置开机自启——
见 **[DEPLOY.md](DEPLOY.md)**（俄文）。

## 更新与支持

Wildberries 一直在改 API：端点会新增、改名、下线——
上面的限制章节列出的就是已经在实践中踩过的坑。
本服务器是作者自己的工作工具，**按作者自身需要更新**：
当某次改动弄坏了他自己店铺里的功能时。没有更新计划，也不承诺时间。

如果你急需某项修复，请发邮件到 **d0371153@gmail.com**。
也欢迎提 Issue 和 Pull Request，都会处理。

## 许可证

MIT —— 见 [LICENSE](LICENSE)。
