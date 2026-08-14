# nl2sql-query-agent

通用 **NL2SQL / 问数 Agent**：自然语言与 slash 指令 → 只读查数 → 表格与结构化结论。

定位是可复用的分析中间层，而不是某个业务产品：

- **slash 固定分析**：注册好的标准 SQL，不经 LLM，稳定出表
- **自然语言 Agent**：ReAct 调工具（固定分析 / 动态 SQL / 导出报告），交付结论与建议
- **只读安全**：模型约束 + SQL 防护 + 数据库只读账号 / `readonly=1`
- **问数台 UI**：多会话、进度、表格与 SQL/JSON 全文美化

接入自有数据时，替换连接配置、表/指标元数据与固定查询即可；引擎与前端可保留。

---

## 示例场景（可整拆）

仓库里附带的 **LumenLearn（流明学堂）** 只是一个**临时虚构场景**：合成学习社区行为数据 + 几条示例指标，方便 clone 后立刻跑通。

| | 说明 |
|--|------|
| **通用能力（主）** | 路由、ReAct、只读防护、工具协议、任务进度、问数台 |
| **Lumen 夹具（次）** | `infra/` 里的示例 ClickHouse、`lumenlearn` 库、造数脚本、`/dau` 等示例 slash、事件字典 |

**不是**真实业务库，也**不绑定**学习社区领域。上线或对接生产时，应换成你的库表与口径，并视情况删除或停用这套示例数据。

样本数据：Synthetic · No PII · 可复现 seed；业务日约 **2026-05-04 ~ 2026-08-01**。

---

## 能力一览

### 双通道交付

| 输入 | 路径 | LLM | 交付形态 |
|------|------|-----|----------|
| `/dau` `/funnel` `/retention` `/overview` `/channel` `/help`（示例指令） | 固定 SQL | 否 | 标题 + 元信息 + **数据表**（无运营建议） |
| 自然语言 | ReAct Agent | 是 | **结论** + 支撑数据 + **运营建议** |

只有显式 `/` 会在进 Agent 前硬拦截；句子里的业务词**不会**抢跑固定分析。快捷按钮发送的是 slash，不是中文短句。

### Agent 工具

| 工具 | 作用 |
|------|------|
| `get_fixed_analysis` | 执行已注册的标准分析（可带日期窗） |
| `db_query` | 只读 SQL 下钻（SELECT/WITH；工具层 + 库侧只读双重拦截） |
| `export_report` | 导出结构化分析报告 |

进度流拆成 **思考 / 调工具 / 观察**。

### 问数台（WebUI）

- 左会话 · 中对话 · 右 Run Log，三栏可拖拽
- 结果优先渲染为表格；Run Log 可折叠、贴底滚动、全文抽屉
- SQL / JSON 高亮与排版；抽屉宽度可持久化

### 示例固定分析（Lumen 夹具）

| 指令 | 指标（示例） |
|------|----------------|
| `/overview` | 区间新增、DAU、完课率、练习用户 |
| `/dau` | 按日 DAU |
| `/retention` | 注册 cohort D1 / D7 留存 |
| `/funnel` | 学习漏斗 |
| `/channel` | 渠道完课对比 |
| `/help` | 指令说明 |

换业务域时，应改写 `FIXED_QUERIES` 与 slash 映射，而不是沿用上述学习社区口径。

### 只读安全（三道防线）

| 层 | 做法 |
|----|------|
| **模型层** | Prompt + 工具 schema：仅 `SELECT` / `WITH … SELECT` |
| **工具层** | `sql_guard`：白名单、禁多语句、禁写/DDL 等；缺省补 `LIMIT` |
| **数据仓库** | 只读账号 + `GRANT SELECT`；会话 `settings.readonly=1` |

示例夹具下：Agent 用 `lumen_ro`；管理账号 `lumen` **仅**给造数脚本。对接自有库时，请配置你自己的只读账号。

---

## 技术栈

| 层 | 选型 |
|----|------|
| API | FastAPI · 任务进度落盘 |
| Agent | 单 Agent ReAct · OpenAI 兼容 Chat Completions |
| 数据访问 | ClickHouse 客户端（示例夹具用本仓 `infra/`；可改连其它实例） |
| 前端 | Vue 3 + Vite |

---

## 快速开始（用示例夹具跑通）

目录名若仍为历史 `lumen-query-agent`，以实际 clone 路径为准。

### 1. 依赖与配置

```powershell
cd nl2sql-query-agent   # 或你的本地目录名
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

### 2. 启动示例 ClickHouse 并灌数

需 Docker。

```powershell
docker compose -f infra/docker-compose.yml up -d
python .\scripts\generate_demo_data.py --seed 42 --to-clickhouse --truncate
```

详见 [`scripts/README.md`](scripts/README.md)。

### 3. 启动后端

```powershell
uvicorn app.server.app:app --host 0.0.0.0 --port 6010 --reload
```

打开：<http://127.0.0.1:6010/>

### 4. 前端

```powershell
cd webui
npm install
npm run build
# 或 npm run dev → http://127.0.0.1:5173
```

### 5. 冒烟

```powershell
python scripts\smoke_offline.py
python scripts\smoke_basic.py
```

### 接到你自己的库

1. 改 `.env` 的 `CH_*`（建议只读账号）  
2. 更新 `app/bi/` 事件/指标与 `FIXED_QUERIES`、slash 路由  
3. 调整 Agent Prompt 中的表字段说明  
4. （可选）去掉或停用 `infra/` 示例 Compose 与造数脚本  

---

## 配置

见 `.env.example`。

| 项 | 说明 |
|----|------|
| `CH_*` | ClickHouse；示例默认为 `lumenlearn` + `lumen_ro` |
| `LLM_PROVIDER` | `dashscope` / `deepseek` / `ark` / `ollama` / `openai` |
| `LLM_API_*` | 可选总覆盖 |

无 API Key 时 slash 仍可用；自然语言需配置 LLM。

---

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/health` | 健康检查 |
| `POST` | `/api/v1/chat` | 对话（`sync` 可同步/异步） |
| `GET` | `/api/v1/task/{task_id}` | 任务进度 |

---

## 目录速览

```
infra/                 # 示例 ClickHouse 夹具（可替换/删除）
app/bi/                # 指标与固定 SQL（按业务替换）
app/core/agent/        # ReAct
app/core/routing/      # slash
app/core/tools/        # sql_guard / db_query / …
webui/                 # 问数台
scripts/               # 示例造数与冒烟
```

示例事件契约：`app/bi/events_dictionary.json`（仅 Lumen 夹具）。

---

## 免责声明

Agent（尤其自然语言路径）生成的结论、解读与运营建议**可能存在幻觉、口径偏差或过度外推**。请以工具返回的查询结果与固定分析报表为准，重要决策前务必多渠道核实，勿仅依赖模型叙述自动执行。

## 协议

MIT。
