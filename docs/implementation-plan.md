# Lumen Query Agent · 实现规划

> **规格与示例**：[spec.md](./spec.md)（场景、数据契约、验收用例、与 dsh/ai_claw 对照）。  
> 本文只负责 **Phase 任务拆解、文件清单、工期**。

> 原则：**门闩在工程层，不靠 prompt 说教**；**进模型的默认是聚合完备包，不是半截明细**。

---

## 总览

```text
Phase 0  已有基线（slash / 只读 / delivery_floor / PTC）
Phase 1  工具结果投影（grain / truncated / model_view）
Phase 2  交付门闩增强（不完备证据 → partial）
Phase 3  工具流水线（pre / execute / post）
Phase 4  系统贴表（模型写解读，数字来自 traces）
Phase 5  SQL 形态治理（强制聚合 / 拒收明细）
Phase 6  Plan 模式（复杂题先列查数计划）
Phase 7  可选软数字对账（仅告警，不硬拦）
Phase 8  会话证据分层 & 大结果外置（spill）
```

| Phase | 优先级 | 预估 | 依赖 |
|-------|--------|------|------|
| 0 | — | 已完成 | — |
| 1 | P0 | 2–3 天 | — |
| 2 | P0 | 1 天 | Phase 1 |
| 3 | P1 | 2 天 | Phase 1 |
| 4 | P1 | 2–3 天 | Phase 1 |
| 5 | P1 | 2 天 | Phase 1 |
| 6 | P2 | 2–3 天 | Phase 3 |
| 7 | P3 | 1–2 天 | Phase 4 |
| 8 | P2 | 1–2 天 | Phase 1 |

---

## Phase 0 · 已有基线 ✅

| 能力 | 位置 | 说明 |
|------|------|------|
| Slash 双通道 | `app/core/routing/slash_router.py` | 显式 `/` 不进 LLM |
| ReAct 循环 | `app/core/agent/react_engine.py` | OpenAI 兼容 tools |
| 只读 SQL | `app/core/tools/sql_guard.py` + CH readonly | 三道防线中的工具层 + 库层 |
| 交付薄地板 | `app/core/agent/delivery_floor.py` | 无成功查数 / 空行 → partial |
| 证据落盘 | `app/core/agent/evidence.py` | `.scratchpad/evidence/` |
| Run Log | `app/core/session/task_store.py` + webui | 步骤 + 查看全文 |
| **PTC 并行工具** | `app/core/agent/parallel_tools.py` | 只读 parallel；export exclusive；有序回写 |
| 并行配置 | `app/config.py` → `max_parallel_tool_calls` | 默认 4；=1 强制串行 |

**缺口（Phase 0 遗留）**

- `messages` 里 tool 内容与 evidence **同文同量**，未做「投影进模型 / 全文留审计」分流
- `run_query` 的 `row_count` = 截断后行数，**无 `truncated` / `total_rows` 语义**
- `_commit_tool_outcomes` 把 **完整 JSON** 写入 `role:tool`，大表直接进 context

---

## Phase 1 · 工具结果投影（P0）

### 目标

实现 **Model-view ⟺ 审计分离**：

- **审计层（evidence / Run Log 全文）**：永远保留完整工具 JSON
- **模型层（`role:tool` content）**：按规则投影为「完备包」或「样本包」

### 1.1 统一工具结果 schema

**新建** `app/core/tools/result_shape.py`

```python
# 工具返回 JSON 建议字段（向后兼容旧字段）
{
  "ok": true,
  "sql": "...",
  "columns": [...],
  "rows": [...],
  "returned_rows": 12,      # 本次返回行数
  "total_rows": 1200,       # 可选；CH 可查时用 count 包装
  "truncated": false,       # returned < total 或 hit LIMIT
  "grain": "aggregate",     # aggregate | detail | fixed
  "model_view": { ... },    # 可选；缺省由 projector 生成
}
```

**改动** `app/core/tools/clickhouse_tool.py`

- `run_query` 执行后区分：
  - `returned_rows = len(rows)`
  - 若 SQL 带 `LIMIT n` 且可能截断 → `truncated: true`（Phase 5 再考虑 `COUNT` 包装查 total）
- `get_fixed_analysis` 路径：`grain: "fixed"`，`truncated: false`

**改动** `app/core/tools/fixed_analysis.py`：返回体增加 `grain: "fixed"`。

### 1.2 结果投影器

**新建** `app/core/agent/tool_projection.py`

```text
project_for_model(full_payload) -> (model_payload, meta)

规则：
1. grain=fixed | aggregate 且 returned_rows <= MODEL_ROW_CAP → 完备包，全文进模型
2. truncated 或 grain=detail 或 rows > MODEL_ROW_CAP → 样本包：
   - columns + sample_rows(<=5) + returned_rows + truncated + hint
   - 不含可误判为全集的 row_count 语义（用 returned_rows）
3. ok=false → 原样（短）
```

配置项（`app/config.py`）：

| 键 | 默认 | 含义 |
|----|------|------|
| `model_row_cap` | 50 | 完备包最大行数 |
| `model_sample_rows` | 5 | 样本包样例行数 |
| `model_json_char_cap` | 8192 | 超出则 head/tail 剪枝（对齐 dsh pruner 思路） |

### 1.3 接入 ReAct 循环

**改动** `app/core/agent/react_engine.py` → `_commit_tool_outcomes`

```text
full_result = outcome.result                    # 审计用
parsed = json.loads(full_result)
model_body = project_for_model(parsed)          # 模型用
messages.append({ role:tool, content: model_body })
save_evidence(..., result=full_result)          # 全文
tool_trace.table = 从 full_result 构建         # UI 仍用全文前 20 行
tool_trace.projection = meta                    # grain / truncated / incomplete
```

### 1.4 测试

**新建** `tests/test_tool_projection.py`

- 小聚合表 → 完备包、truncated=false
- 500 行 LIMIT → 样本包、truncated=true、样例 ≤5 行
- 超 char cap → head/tail 剪枝，审计仍全文

### 验收

- [ ] evidence / Run Log「查看全文」仍为完整 JSON
- [ ] `messages` 中大表明细不再全文进入
- [ ] `tool_traces[].projection.truncated` 可被查数门闩读取

---

## Phase 2 · 交付门闩增强（P0）

### 目标

在现有 `delivery_floor` 上增加 **证据完备性** 档位，不靠 prompt。

### 2.1 扩展 `assess_query_evidence`

**改动** `app/core/agent/delivery_floor.py`

新增 `reason` 枚举：

| reason | 条件 | 行为 |
|--------|------|------|
| `none` | 有 ok 查数且有行，且**无** incomplete 投影 | success |
| `empty_rows` | ok 但 0 行 | partial + 空结果提示 |
| `missing_ok_query` | 未成功查数 | partial + 无查数提示 |
| **`incomplete_evidence`** | 仅有 truncated / detail 样本包，且无后续 ok 聚合查数 | partial + 「证据不完备，结论勿采信」 |
| **`detail_only`** | 最后一次成功查数为 detail 且 truncated | 同上或更强提示 |

逻辑：

```text
扫描 tool_traces（按时间序）：
  若存在任一 ok 且 grain in (fixed, aggregate) 且 truncated=false → 视为有完备证据
  否则若存在 ok 查数 → incomplete_evidence
  否则 → 沿用现有 missing / empty
```

### 2.2 与 Phase 1 联动

`_build_tool_trace` 写入 `grain`、`truncated`、`projection_incomplete`。

### 2.3 测试

**扩展** `tests/test_delivery_floor.py`：truncated 样本包-only → `incomplete_evidence`。

### 验收

- [ ] 模型只看截断明细就交卷 → `status=partial`，新 notice 文案
- [ ] 先 truncated 再聚合查数成功 → 可 success
- [ ] slash / fixed_slash 不受影响

---

## Phase 3 · 工具流水线（P1）

### 目标

把散落在 `react_engine` / `clickhouse_tool` 的逻辑收成 **pre → execute → post**，便于加策略而不改 loop。

### 3.1 模块划分

**新建** `app/core/tools/pipeline.py`

```text
class ToolPipeline:
  def pre_execute(name, args) -> PreResult
    # sql_guard、超时预算、并发标记、明细拒收（Phase 5）

  def execute(name, args) -> str
    # 调 TOOLS 注册表

  def post_execute(name, args, full_result) -> PostResult
    # 投影 model_view、写 projection meta、可选 char 剪枝
```

**改动** `parallel_tools.py`：`_invoke_one` 改为走 `ToolPipeline.execute`（pre 在组前或 call 前按 dsh 约定：pre 有序、execute 可并行）。

### 3.2 Pre 钩子（Phase 5 预埋）

- `db_query`：SQL 形态检查入口（Phase 5 实现 `classify_sql_grain`）
- 超时：`settings.query_timeout_seconds`

### 3.3 Post 钩子

- 调用 `tool_projection.project_for_model`
- 统一 `ok` / 错误 JSON 形态

### 验收

- [ ] PTC 行为与 Phase 0 单测一致
- [ ] 新增策略只改 pipeline，不改 `react_engine` 主循环

---

## Phase 4 · 系统贴表（P1）

### 目标

**精确数字尽量由系统渲染**，模型写解读与建议，减少 prose 里手打 KPI。

### 4.1 响应结构扩展

Agent 终态 JSON 增加（已有部分 `data`）：

```python
{
  "answer": "### 核心结论：...",      # 模型 prose（少数字）
  "data": { ... },                     # 主表（来自最后一次完备查数）
  "data_tables": [                     # 多表场景（PTC 并行多次查数）
    { "label": "DAU", "table": {...}, "tool_index": 0 },
    { "label": "漏斗", "table": {...}, "tool_index": 1 },
  ],
  "render_mode": "system_tables",      # 或 legacy_markdown_tables
}
```

### 4.2 Prompt 调整

**改动** `react_engine.py` → `SYSTEM_PROMPT`

- 明确：**支撑数据表格由系统自动展示**，模型不要在 Markdown 里重复大表
- 结论段允许趋势判断；精确 KPI 可用「见上表」或仅引用表头指标名
- 禁止在 prose 中编造未出现在工具结果中的具体数值

### 4.3 前端

**改动** `webui/src/api.ts` / 消息组件

- `agent_loop` 且存在 `data_tables` → 渲染多表 tabs 或折叠
- prose 与表分离（已有 slash 逻辑，扩展到 agent）

### 4.4 从 traces 选表

**新建** `app/core/agent/table_selection.py`

```text
select_display_tables(tool_traces) -> list[DisplayTable]
  优先：grain=fixed|aggregate 且 truncated=false 的成功结果
  PTC：保留每组并行结果（按 tool 顺序）
```

### 验收

- [ ] 自然语言路径：中栏表来自 `data_tables`，非模型 Markdown 表
- [ ] 并行查 3 个 fixed analysis → 3 张表均可展示
- [ ] 无完备证据时仍走 Phase 2 partial

---

## Phase 5 · SQL 形态治理（P1）

### 目标

默认 **强制聚合完备包**；明细查询要么拒收，要么明确为样本包。

### 5.1 SQL 分类器

**新建** `app/core/tools/sql_classifier.py`

```text
classify_sql(sql) -> grain
  fixed_analysis → fixed（已有）
  含 GROUP BY / 聚合函数且无明细粒度列 → aggregate
  SELECT * / 无 GROUP BY / 用户级 id 列 → detail
```

启发式（可调）：

- `distinct_id` 出现在 SELECT 且无聚合 → detail
- 仅 `count/uniq/avg/sum` + 维度 → aggregate

### 5.2 策略（配置）

| 配置 | 默认 | 行为 |
|------|------|------|
| `reject_detail_sql` | false | true 时 detail SQL 直接 ok=false + hint 改写 |
| `detail_sample_only` | true | detail 允许执行但 grain=detail + truncated 样本进模型 |

hint 示例：

```text
当前问题需要汇总指标。请改用 GROUP BY 维度列，或使用 get_fixed_analysis(key=...)。
```

### 5.3 sql_guard 协作

- 明细拒收模式下，`guard_readonly_sql` 之后、`execute` 之前拦截
- 保留「用户明确要求下钻样例」路径：`detail_sample_only=true`

### 验收

- [ ] 「各渠道完课率」类问题 → 模型被引导写 GROUP BY 或调 fixed
- [ ] 拒收模式下明细 SQL 返回结构化错误，Run Log 可见 hint
- [ ] 固定分析 / 小聚合不受限

---

## Phase 6 · Plan 模式（P2，可选）

### 目标

复杂多指标问题：**先列查数计划 → 再 PTC 并行执行 → 再写结论**（借鉴 dsh plan-mode 流程，不做 Cordis）。

### 6.1 轻量实现（不新增 LLM 工具）

**Prompt + 状态机**（低成本）：

```text
首轮：要求模型先输出 <plan>  markdown 列表（查哪些 key / SQL 口径）
不执行工具 → Run Log 记录 plan
次轮：用户无操作自动继续，或 UI「确认执行」
执行：按计划 PTC 并行 get_fixed_analysis / db_query
末轮：写结论（Phase 4 系统贴表）
```

### 6.2 完整实现（可选）

新增工具 `submit_query_plan`：

- 输入：`steps: [{type: fixed|sql, ...}]`
- 系统校验 steps 可执行 → 自动 PTC 跑完 → 返回汇总 traces
- 模型只写解读

### 配置

- `enable_plan_mode: bool = false`（默认关，复杂 demo 再开）

### 验收

- [ ] 复杂问题（≥3 指标）计划可见于 Run Log
- [ ] 计划步骤与后续 tool_calls 可对照

---

## Phase 7 · 软数字对账（P3，可选）

### 目标

**仅告警**，不替模型改数、不用占位符替换（避免 ai_claw 式 rigid）。

### 7.1 实现

**新建** `app/core/agent/numeric_audit.py`

```text
extract_numeric_claims(answer) -> list[Claim]   # 正则 + 中文数词（可选）
build_evidence_numbers(tool_traces) -> set[str] # 从 rows 展平数值
normalize(n) -> canonical                       # 0.31 ↔ 31% ↔ 31.0%

audit(answer, traces) -> { flagged: [...], severity: warn|info }
```

策略：

- **warn**：结论中出现 ≥2 位有效数字且不在 evidence 集（归一化后）
- **不修改 answer**；仅 `delivery_notice` 追加「部分数字未在工具结果中出现，请核对」
- 忽略：日期、「第 N 条建议」、明显非 KPI 的小整数

### 7.2 不做

- 全文精确匹配
- 自动 strip 数字
- 占位符 replace

### 验收

- [ ] 工具返回 1523、结论写 1800 → warn
- [ ] 写「约 1500」且 evidence 有 1523 → 不 warn（可选宽松规则）
- [ ] 无误杀固定分析 slash 路径

---

## Phase 8 · 会话证据分层 & Spill（P2）

### 目标

对齐 dsh「日志全文 + surface 投影」；超大结果不撑爆内存与 context。

### 8.1 事件类型（轻量，不引入 Cordis）

在 `task_store` / evidence 中区分：

| 类型 | 存储 | 用途 |
|------|------|------|
| `tool_result_full` | evidence 文件 | 审计、下载 |
| `tool_result_model` | 仅内存进 messages | LLM 上下文 |
| `progress` | task JSON | UI Run Log |

### 8.2 Spill

当 `len(full_result) > spill_threshold_bytes`（如 256KB）：

- evidence 写 `{ "spill_path": ".scratchpad/evidence/xxx.json", "summary": {...} }`
- model_view 只含 summary + spill 引用
- Run Log「查看全文」读 spill 文件

**改动** `app/core/agent/evidence.py`：大结果自动 spill。

### 验收

- [ ] 10 万行查询不会 OOM；evidence 可下载
- [ ] 模型侧仅见 summary

---

## 配置汇总（`.env.example` 待增）

```env
# PTC（已有）
MAX_PARALLEL_TOOL_CALLS=4

# Phase 1 投影
MODEL_ROW_CAP=50
MODEL_SAMPLE_ROWS=5
MODEL_JSON_CHAR_CAP=8192

# Phase 5 SQL 形态
REJECT_DETAIL_SQL=false
DETAIL_SAMPLE_ONLY=true

# Phase 6
ENABLE_PLAN_MODE=false

# Phase 7
ENABLE_NUMERIC_AUDIT=false

# Phase 8
SPILL_THRESHOLD_BYTES=262144
QUERY_TIMEOUT_SECONDS=60
```

---

## 测试矩阵

| 场景 | 覆盖 Phase | 类型 |
|------|-----------|------|
| PTC 分组 / 有序回写 | 0 | 已有 `test_parallel_tools.py` |
| 投影完备 vs 样本 | 1 | 单元 |
| truncated-only → partial | 2 | 单元 |
| pipeline pre 拒收 detail | 5 | 单元 |
| 并行 3 fixed → 3 tables UI | 4 | 集成 / 手工 |
| 大结果 spill | 8 | 单元 |
| 数字 audit warn | 7 | 单元 |
| smoke_basic 回归 | 全部 | 脚本 |

---

## 推荐实施顺序

```text
Week 1   Phase 1 + 2   （投影 + 不完备 partial）← 防幻觉核心
Week 2   Phase 3 + 5   （流水线 + SQL 形态）
Week 3   Phase 4       （系统贴表 + 前端）
Week 4   Phase 8       （spill，若已遇大结果问题）
按需     Phase 6 / 7   （plan / 软对账）
```

**不要做的（本规划明确排除）**

- 引入 Cordis / 全插件化 harness
- LLM 摘要工具结果或对话历史（compaction-basic 式）作为问数默认路径
- ai_claw 式全文占位符 + replace
- 结论数字硬匹配门闩（误杀高）

---

## 与 DeepSeek Harness 对照

| 能力 | dsh | 本规划 |
|------|-----|--------|
| PTC | ✅ loop 调度 | ✅ Phase 0 已有 |
| 工具结果压缩 | 字符 head/tail + 可选 LLM compaction | Phase 1 语义投影 + Phase 8 spill |
| 防幻觉 | 日志可重建；不校验 prose 数字 | Phase 2/4/5 门闩 + 系统贴表 |
| Plan | exit_plan_mode 工具 | Phase 6 可选轻量 |
| 插件化 | Cordis 全插件 | 不引入；Python pipeline 即可 |

---

## 文档与 README

Phase 1 完成后更新 `README.md`：

- 「Agent 工具结果投影」小节
- `truncated` / partial 含义
- 新 env 配置说明
