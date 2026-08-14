# lumen-query-agent

自然语言数据分析 Agent（问数台）：slash 固定分析 + ReAct 工具循环 + 只读查数。

**LumenLearn（流明学堂）为示例业务域**：虚构学习社区与可复现合成数据，用来跑通端到端流程；不是真实产品或生产环境。  
**分析能力与库可解耦**：更换 ClickHouse 连接、表结构 / 事件字典、`FIXED_QUERIES` 后，同一套路由、Agent、只读防护与 UI 可接到你自己的数据上。

本仓附带本地 ClickHouse（`events` + `users`）与造数脚本，开箱可跑：

- **固定分析 slash**：不经过 LLM，稳定出表
- **自然语言 Agent**：ReAct 调工具，交付「结论 + 数据 + 运营建议」
- **Vue 问数台**：会话、进度、表格与 SQL/JSON 全文美化

> 样本数据：Synthetic · No PII · 可复现 seed。

---

## 能力一览

### 示例业务域 vs 可迁移能力

| | 说明 |
|--|------|
| **示例业务域（可整换）** | LumenLearn 叙事、合成 `events`/`users`、`/dau` 等固定 SQL、造数脚本 |
| **可迁移能力（项目重点）** | slash / Agent 双通道、只读三道防线、ReAct 工具循环、问数台 UI、报告导出 |

换库时通常改：`.env` 的 `CH_*`、`infra/` DDL（或指向已有库）、`app/bi/` 字典与固定查询、以及 Prompt 中的表字段说明。

### 双通道交付

| 输入 | 路径 | LLM | 交付形态 |
|------|------|-----|----------|
| `/dau` `/funnel` `/retention` `/overview` `/channel` `/help` | 固定 SQL | 否 | 标题 + 元信息 + **数据表**（无运营建议） |
| 自然语言 | ReAct Agent | 是 | **结论** + 支撑数据 + **运营建议** |

只有显式 `/` 指令会在进 Agent 前硬拦截。句子里出现「日活 / 留存」**不会**抢跑固定分析，避免误路由。

快捷按钮发送的是 `/dau` 等指令，不是中文短句。

### Agent 工具

| 工具 | 作用 |
|------|------|
| `get_fixed_analysis` | 跑注册好的标准指标 SQL（可带日期窗） |
| `db_query` | 只读 SQL 下钻（SELECT/WITH；工具层 + CK 只读账号双重拦截） |
| `export_report` | 导出结构化分析报告（Markdown / 表格） |

进度流会拆成 **思考 / 调工具 / 观察**，便于对照 ReAct 过程。

### 问数台（WebUI）

- 左会话列表 · 中对话区 · 右 Run Log，三栏可拖拽调宽
- 结果优先渲染为**中文列表格**（比率列自动百分比）
- Run Log：多行步骤自动折叠、贴底滚动、点击查看**全文抽屉**
- 全文美化：Markdown / JSON 高亮、SQL 括号感知缩进与关键字高亮
- 抽屉左边框可拖拽；宽度写入 `localStorage`

### 固定分析清单

| 指令 | 指标 |
|------|------|
| `/overview` | 区间新增、DAU、完课率、练习用户 |
| `/dau` | 按日 DAU（登录账号级） |
| `/retention` | 注册 cohort 的 D1 / D7 留存 |
| `/funnel` | 学习漏斗 |
| `/channel` | 渠道完课对比 |
| `/help` | 指令说明 |

别名示例：`/日活` → `/dau`，`/today_dashboard` → `/overview`。

### 只读安全（生产级三道防线）

问数路径**禁止写库 / 污染样本数据**，相对常见「仅应用层黑名单」做法，本仓叠了三层：

| 层 | 做法 |
|----|------|
| **模型层** | System Prompt + `db_query` 工具 schema 明确：仅 `SELECT` / `WITH … SELECT`，禁止写操作与多语句 |
| **工具层** | `sql_guard`：语句白名单、禁多语句、禁 DDL/DML/权限/SYSTEM 等关键字；缺省自动补 `LIMIT` |
| **数据仓库** | Agent 默认账号 `lumen_ro`（`SETTINGS readonly=1` + `GRANT SELECT`）；会话再带 `settings.readonly=1` |

管理账号 `lumen` / `lumen_demo` **仅**用于 `scripts/generate_demo_data.py` 建表灌数，不要写进 Agent 的 `.env`。

造数时会执行 `infra/init_readonly.sql` 尝试创建只读账号。若你沿用旧容器，跑一次带 `--to-clickhouse` 的造数即可补齐账号。

---

## 技术栈

| 层 | 选型 |
|----|------|
| API | FastAPI · 任务进度落盘 |
| Agent | 单 Agent ReAct · OpenAI 兼容 Chat Completions |
| 数据 | ClickHouse only（本仓 `infra/` + 合成数据） |
| 前端 | Vue 3 + Vite（Fraunces / Sora · 橡木色） |

---

## 快速开始

### 1. 依赖与配置

```powershell
cd lumen-query-agent
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

### 2. 启动 ClickHouse 并灌入样本数据

需本机已安装 Docker。

```powershell
docker compose -f infra/docker-compose.yml up -d
python .\scripts\generate_demo_data.py --seed 42 --to-clickhouse --truncate
```

默认账号：造数用管理账号 `lumen` / `lumen_demo`；Agent `.env` 用只读账号 `lumen_ro` / `lumen_ro_demo`（见 `.env.example`）。  
更多造数参数见 [`scripts/README.md`](scripts/README.md)。

样本业务日大致在 **2026-05-04 ~ 2026-08-01**；Agent 默认日期窗会落在该区间。

### 3. 启动后端

```powershell
uvicorn app.server.app:app --host 0.0.0.0 --port 6010 --reload
```

打开：<http://127.0.0.1:6010/>（托管 `webui/dist`；无构建产物时回退 `web/`）。

### 4. 前端

```powershell
cd webui
npm install
npm run build          # 生产：由 6010 托管
# 或开发热更新：
npm run dev            # http://127.0.0.1:5173 ，代理到 6010
```

### 5. 冒烟

```powershell
python scripts\smoke_offline.py   # 路由 / 固定查询等离线检查
python scripts\smoke_basic.py     # 需服务已启动：slash 全链路
```

---

## 配置

本地 `.env`（见 `.env.example`）。

| 项 | 说明 |
|----|------|
| `CH_USER` / `CH_PASSWORD` | **必须**为只读账号 `lumen_ro` / `lumen_ro_demo` |
| `CH_HOST` / `CH_PORT` / `CH_DATABASE` | 默认 `127.0.0.1:8123` / `lumenlearn` |
| `LLM_PROVIDER` | `dashscope` / `deepseek` / `ark` / `ollama` / `openai` |
| `LLM_API_*` | 可选总覆盖；非空则优先于各 Provider 专用项 |

未配置可用 API Key 时：slash 固定分析仍可用；自然语言会提示改用 slash 或补 Key。

---

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/health` | 健康检查 |
| `POST` | `/api/v1/chat` | 对话（`sync` 可同步/异步） |
| `GET` | `/api/v1/task/{task_id}` | 任务进度（含 think / tool / observe） |

---

## 目录速览

```
infra/
  docker-compose.yml
  clickhouse_ddl.sql
  init_readonly.sql          # 创建 lumen_ro + GRANT SELECT
  clickhouse/users.d/        # readonly profile
app/
  bi/
  core/agent/
  core/routing/
  core/tools/                # sql_guard + clickhouse（readonly=1）
  core/session/
  server/
webui/
scripts/
  generate_demo_data.py      # 管理账号灌数 + 确保只读用户
  smoke_*.py
data/
```

---

## 事件契约

- `app/bi/events_dictionary.json`

采集链路（Flume / Kafka / Flink）**不是**本仓运行依赖；默认以「合成数据直写 CK」跑通问数主路径。

## 免责声明

Agent（尤其自然语言路径）生成的结论、解读与运营建议**可能存在幻觉、口径偏差或过度外推**。请以工具返回的查询结果与固定分析报表为准，重要决策前务必多渠道核实，勿仅依赖模型叙述自动执行。

## 协议

MIT。
