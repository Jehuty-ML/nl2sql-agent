# Lumen Query Agent · 问数证据与交付规格（Spec）

> **读者**：实现者、评审者、未来接业务域的维护者。  
> **配套**：[implementation-plan.md](./implementation-plan.md)（分 Phase 的任务拆解与文件清单）。  
> **来源**：与 DeepSeek Harness / ai_claw 的对照讨论，以及 Lumen 问数场景下的实测踩坑（prompt 禁外推无效、占位符替换不灵活、截断明细导致乱编）。

---

## 1. 问题陈述

### 1.1 我们要解决什么

Lumen Query Agent 是 **NL2SQL / 问数** 引擎：用户用自然语言或 slash 指令查 ClickHouse，得到 **可核对的数字 + 结论 + 建议**，并能在 Run Log / evidence 里回溯 SQL。

核心风险不是「模型不会写 SQL」，而是：

1. **无证据结论**：没查数或查失败，仍写满「核心结论 + 运营建议」。
2. **假完整表**：明细被 `LIMIT` 截断，模型当全集写总和、排名、占比。
3. **散文手打 KPI**：结论里的数字与工具返回对不上（幻觉或口径漂移）。
4. **上下文爆炸**：大表全文进 LLM，挤掉系统约束，且仍不能防幻觉。

### 1.2 设计原则（Normative）

| ID | 原则 | 含义 |
|----|------|------|
| P1 | **门闩在工程层** | 交付档位、证据完备性、SQL 形态由代码决定；不依赖 prompt「请勿编造」。 |
| P2 | **审计全文 ⟺ 模型投影分离** | Run Log / evidence 保留完整工具 JSON；进 `role:tool` 的可以是投影后的子集，且须带 `truncated` / `grain` 元数据。 |
| P3 | **默认聚合完备包** | 用于写结论的查数结果，对当前问题应是「小且可结案」的聚合表，不是半截明细。 |
| P4 | **精确数字系统贴，模型写解读** | 表格与 KPI 优先由系统从 `tool_traces` 渲染；模型负责趋势、原因、建议（可定性，少手抄数）。 |
| P5 | **薄地板、不硬栏** | 证据异常时标 `partial` 并提示，保留模型原文，不 silent 改数、不强制打回重写（除非未来显式开启）。 |

### 1.3 非目标

- 不引入 Cordis / 全插件 harness。
- 不用 LLM 摘要工具结果或对话历史作为问数默认防幻觉手段（dsh compaction 思路）。
- 不做 ai_claw 式「正文占位符 → 全局 replace」作为主力。
- 不做结论全文数字硬精确匹配（误杀「约 1500」类表述）。

---

## 2. 术语

| 术语 | 定义 |
|------|------|
| **完备包（complete package）** | 工具返回对**当前问题**已足够结案：`grain ∈ {fixed, aggregate}` 且 `truncated=false`，行数 ≤ 配置上限。 |
| **样本包（sample package）** | 仅含列名、少量样例行、`returned_rows`、`truncated=true` 与改写 hint；**不可**用于写总和/排名类结论。 |
| **grain** | 结果粒度：`fixed`（注册固定分析）、`aggregate`（GROUP BY / 聚合 SQL）、`detail`（用户/事件级明细）。 |
| **truncated** | 返回行数因 LIMIT 或投影裁剪，不代表业务全集。 |
| **delivery_floor** | 交卷前门闩：`missing_ok_query` / `empty_rows` / `incomplete_evidence` → `status=partial`。 |
| **PTC** | Parallel Tool Calls：同一步内并行只读工具；`export_report` 等为 exclusive 屏障。 |
| **Model-view** | 写入 LLM `messages` 的工具内容。 |
| **Audit-view** | evidence / Run Log「查看全文」中的完整 JSON（或 spill 文件）。 |

---

## 3. 场景示例（Spec 用例）

以下示例是**规格行为**的锚点；实现须满足或显式文档化偏差。

---

### 3.1 例 A：渠道完课率 — 坏路径 vs 好路径

**用户**：「各渠道完课率差多少？哪个值得加投放？」

#### 坏路径（当前易出现的问题）

```sql
-- 模型发出明细 SQL
SELECT distinct_id, register_channel, event, dt FROM events WHERE ... LIMIT 500
```

工具返回 500 行（且 `row_count=500`，模型误以为共 500 人）→ 全文或 top-20 进 `messages` → 模型写：

> 抖音完课率 **35%**，微信 **28%**，建议加大抖音投放。

数字可能**不在**返回行里（模型按常识编）。

| 检查项 | 坏路径结果 |
|--------|------------|
| grain | `detail` |
| truncated | 应为 true，但旧实现常未标注 |
| delivery_floor | 仅有 ok 查数 → 可能 **success**（错误） |
| 用户能否核对 | 需点开 Run Log，且 prose 数字可能对不上表 |

#### 好路径（本 Spec 目标）

**路径 1 — 固定分析**

```text
tool: get_fixed_analysis(key="channel_completion")
```

返回 5 行渠道汇总 → `grain=fixed`, `truncated=false` → **完备包**全文进 model-view。

**路径 2 — 动态聚合**

```sql
SELECT register_channel,
       uniqExact(distinct_id) AS users,
       countIf(event='LessonComplete') / nullIf(users,0) AS completion_rate
FROM events WHERE ...
GROUP BY register_channel
```

返回 ≤10 行 → `grain=aggregate`, `truncated=false`。

**交付**

- 中栏 **3 张表由系统渲染**（若 PTC 并行查 DAU+渠道+漏斗则 `data_tables[]`）。
- 模型 prose：「抖音完课率高于微信，差距见上表『渠道完课对比』；建议…」
- `delivery_floor`: `reason=none`, `status=success`

---

### 3.2 例 B：最近一周 DAU — 完备包

**用户**：「最近一周日活大概怎样？」

**查数**

```text
get_fixed_analysis(key="dau", start_date=..., end_date=...)
```

**返回**（示意 7 行）

```json
{
  "ok": true,
  "grain": "fixed",
  "truncated": false,
  "returned_rows": 7,
  "rows": [
    {"dt": "2026-07-26", "dau": 1520},
    {"dt": "2026-07-27", "dau": 1488}
  ]
}
```

**model-view**：与 audit-view 相同（7 行 ≤ `MODEL_ROW_CAP`）。

**模型允许**：描述「先升后略降」；若写具体数字，须来自上表（Phase 4 后表由系统贴，prose 可少写数）。

**不允许（Phase 7 软 audit 可 warn）**：表内最大 DAU 1520，结论写「日均 **1800**」。

---

### 3.3 例 C：截断明细 — 必须 incomplete

**用户**：「列出最近完课的用户明细。」（明确要明细）

**查数**：detail SQL，返回 500 行，命中 `LIMIT 500`。

**audit-view**：500 行完整 JSON（或 spill）。

**model-view（样本包）**

```json
{
  "ok": true,
  "grain": "detail",
  "truncated": true,
  "returned_rows": 500,
  "sample_rows": [ "...最多 5 行..." ],
  "hint": "此为截断样本，不可用于汇总指标；若需各维度汇总请 GROUP BY 或使用 get_fixed_analysis。"
}
```

**若模型不再发起聚合查数即交卷**

```text
delivery_floor.reason = incomplete_evidence
status = partial
delivery_notice = 【系统提示】查数证据不完备（结果已截断或为明细样本），结论请谨慎采信…
```

**若随后** `get_fixed_analysis(key="channel_completion")` 成功 → 以最后一次**完备**查数为准 → 可 `success`（针对汇总型子问题）。

---

### 3.4 例 D：无查数交卷 — 已有门闩

**用户**：「最近一周日活怎样？给两条运营建议。」

**模型**：未调用 `db_query` / `get_fixed_analysis`，直接输出 Markdown 结论。

```text
delivery_floor.reason = missing_ok_query
status = partial
```

（与现网 `delivery_floor.py` 一致，Spec 保留。）

---

### 3.5 例 E：PTC 并行多指标

**用户**：「同时看下 DAU、漏斗、渠道完课，给个总览。」

**模型一步返回 3 个 tool_calls**

```text
get_fixed_analysis(key="dau")
get_fixed_analysis(key="funnel")
get_fixed_analysis(key="channel_completion")
```

**调度（Phase 0 已实现）**

```text
组 1 [parallel]: 三个 fixed 并行执行，max_parallel=4
执行顺序完成先后任意；commit 顺序 = 模型 tool_calls 顺序
```

**Run Log**：每步标注 `parallel=true`, `ptc_group=0`。

**交付（Phase 4）**

```json
{
  "data_tables": [
    {"label": "日活 DAU", "table": {...}, "tool_index": 0},
    {"label": "学习漏斗", "table": {...}, "tool_index": 1},
    {"label": "渠道完课对比", "table": {...}, "tool_index": 2}
  ],
  "render_mode": "system_tables"
}
```

**延迟**：≈ max(三次查询)，非三次相加。

---

### 3.6 例 F：为什么 prompt「禁止外推未展示行」无效

**Prompt 写法（已验证无效）**

> 禁止对未展示行做总和、排名、占比外推；不足请写【数据限制】。

**实际模型行为**

1. 仍要填满「### 核心结论 + ### 支撑数据 + ### 运营建议」三段式。
2. 看到 20 行样本，问题却是「各渠道对比」→ 补全「合理」渠道名与百分比。
3. 不会自觉再调工具，除非工具返回 **结构化 forcing function**（`ok=false` + hint，或 `truncated=true` + delivery partial）。

**Spec 要求**

- 禁止仅靠 prompt；必须 **样本包形态 + incomplete 门闩**（§3.3）。
- 可选：`reject_detail_sql=true` 时直接拒收明细 SQL（§5.2）。

---

### 3.7 例 G：ai_claw 占位符方案 vs 本 Spec

**ai_claw 做法（简述）**

- 模型正文写 `{data_reference_1}`、`[table_1]`。
- 系统 `resolve_template_references` 替换为真实 SQL / 表。

**失败模式（本项目实测）**

| 问题 | 表现 |
|------|------|
| 漏写 / 写错序号 | 替换失败，用户看到占位符 |
| 叙述与引用混排 | 不灵活，模型绕开占位符直接写数 → 幻觉 |
| 多表并行 | 序号与 tabular records 对齐 fragile |

**本 Spec 替代**

- **系统贴表**（Phase 4）：`data` / `data_tables` 由后端从 traces 生成，与 `answer` 分离。
- **软数字 audit**（Phase 7，可选）：只 warn，不 replace。

---

### 3.8 例 H：数字对账 — 做什么、不做什么

#### 不做（硬精确匹配）

```text
工具 traces 数字集 = {1520, 1488, 0.31}
结论 = "日活约 1500，完课率 35%"
→ 硬匹配失败 → 拒收或 strip 数字   ❌ 误杀正常表述
```

#### 可选做（Phase 7 软 audit）

```text
工具 traces 归一化集 = {1520, 1488, 31, 0.31}
结论 = "日活 1800"   → warn：1800 ∉ 证据集
结论 = "日活约 1500" → 不 warn（宽松规则，可配置）
结论 = "见上表"      → 不扫描
```

**白名单归一化（实现参考）**

- 整数 / 一位小数四舍五入等价
- `0.31` ↔ `31%` ↔ `31.0%`
- 忽略：日期、`第 N 条`、个位数枚举

---

## 4. 与 DeepSeek Harness 的差异（带例子）

| 维度 | DeepSeek Harness | Lumen 本 Spec |
|------|------------------|---------------|
| **主问题** | 通用 coding agent，会话长、工具输出大 | 问数：结论数字要可追溯到 SQL |
| **大 tool result** | `toolResultPruner`：**字符** head/tail + `[...pruned...]`，原文在 session log | **语义**投影：聚合完备包 vs 样本包；字符剪枝仅作兜底 |
| **Compaction** | 压力够大时 **LLM 摘要**旧对话 | **不**作为问数默认路径；摘要丢口径风险高 |
| **防 prose 幻觉** | 基本不校验结论数字 | delivery_floor + 系统贴表 + 可选软 audit |
| **并行工具** | `isConcurrencySafe` + 有序 `tool/result` | PTC 已实现，同思路 |
| **Slash** | `ctx.commands` 人类命令平面 | `/dau` 等 fixed_slash，不进 LLM |

**例：dsh 读 10 万行 grep**

```text
grep 返回 10 万行 → pruner 保留头 4096 + 尾 1024 字符 → 模型继续读代码任务
```

**问数不应照搬**：截断渠道明细后模型仍会写「完课率 35%」→ 需 §3.1 聚合路径。

---

## 5. 数据契约

### 5.1 工具结果 JSON（查数类）

```json
{
  "ok": true,
  "sql": "SELECT ...",
  "columns": ["register_channel", "completion_rate"],
  "rows": [],

  "returned_rows": 5,
  "total_rows": null,
  "truncated": false,
  "grain": "fixed",

  "analysis_key": "channel_completion",
  "name": "渠道完课对比",

  "hint": null
}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `ok` | 是 | 查数是否成功 |
| `returned_rows` | 查数成功时 | 本次返回行数；**禁止**在 truncated 时暗示等于全集 |
| `truncated` | 是 | 是否截断 / 非全集 |
| `grain` | 是 | `fixed` \| `aggregate` \| `detail` |
| `total_rows` | 否 | 若执行 COUNT 包装则填；否则 null |
| `row_count` | 兼容 | 逐步废弃，等同 `returned_rows`；文档注明 deprecated |

### 5.2 tool_trace（Run Log / delivery）

`tool_traces` 挂在 task / `final_result` 上，**故意不存完整 `result`**（避免 task JSON 膨胀）。全文在 evidence；traces 只留摘要字段。

```json
{
  "tool": "db_query",
  "ok": true,
  "parallel": true,
  "ptc_group": 0,
  "grain": "aggregate",
  "truncated": false,
  "returned_rows": 5,
  "result_preview": "{... 最多约 800 字符的 JSON 摘要 ...}",
  "projection": {
    "kind": "complete",
    "incomplete": false,
    "model_chars": 1200
  },
  "table": {
    "name": "...",
    "row_count": 5,
    "rows": ["... UI 最多 20 行 ..."],
    "sql": "..."
  }
}
```

`projection.kind`: `complete` | `sample` | `pruned_chars`

| 字段 | 在哪 | 含义 |
|------|------|------|
| `result_preview` | `tool_traces` | 审计结果 JSON 的短摘要（约 800 字） |
| `table` | `tool_traces` | UI / 系统贴表用（最多约 20 行） |
| **`result`** | **evidence** `*_tool_*.json` | **投影前**完整工具返回 |
| **`model_content`** | **evidence** 同文件 | **投影后**进 LLM 的内容；`model_chars = len(model_content)` |
| `projection` | traces + evidence | 投影元数据 |

Run Log「查看全文」读的是 progress 步骤的 `full`（通常等于审计全文），不是 traces 里的 `result` 字段。

### 5.3 Agent 终态（HTTP / task result）

```json
{
  "mode": "agent_loop",
  "status": "success",
  "answer": "### 核心结论：…",
  "data": { },
  "data_tables": [],
  "render_mode": "system_tables",
  "tool_traces": [],
  "delivery_assessment": {
    "has_ok_query": true,
    "has_nonempty_rows": true,
    "has_complete_evidence": true,
    "reason": "none"
  },
  "delivery_notice": null
}
```

`status` 枚举：`success` | `partial` | （错误路径 `mode=error` 不变）

### 5.4 delivery_floor.reason 枚举

| reason | 触发 | 用户可见 |
|--------|------|----------|
| `none` | 有完备证据且有行 | 无额外黄标 |
| `empty_rows` | ok 但 0 行 | 空结果提示 |
| `missing_ok_query` | 无成功查数 | 无查数提示 |
| `incomplete_evidence` | 仅 truncated/样本/detail 且无后续完备查数 | 证据不完备提示 |
| `numeric_audit_warn` | Phase 7 开启且软 audit 命中 | 附加核对提示（仍 partial 或 success+notice，实现时二选一，默认 success+notice） |

---

## 6. 工具结果投影规则（Normative）

**函数**：`project_for_model(full_payload) -> (model_json_str, projection_meta)`

| 条件 | model-view | projection.kind |
|------|------------|-----------------|
| `ok=false` | 原样（错误 JSON） | — |
| `grain=fixed` 且 `returned_rows ≤ MODEL_ROW_CAP` | 全文 | `complete` |
| `grain=aggregate` 且 `truncated=false` 且行数 ≤ cap | 全文 | `complete` |
| `truncated=true` 或 `grain=detail` 或行数 > cap | 样本包（§3.3） | `sample` |
| 完备包 JSON 字符 > `MODEL_JSON_CHAR_CAP` | head + marker + tail（dsh 式） | `pruned_chars` |

**不变量**

- Audit-view **始终**保存投影前完整 JSON（或 spill 路径）。
- `sample` 包 **不得**包含可被误解为全集的 `"row_count": 500` 而无 `truncated: true` 说明。

---

## 7. SQL 形态规则（Phase 5）

### 7.1 分类启发式

```text
classify_sql(sql) -> grain

若来自 get_fixed_analysis → fixed
若 SELECT 列表含 distinct_id / identity_login_id 且无聚合函数 → detail
若含 GROUP BY 或 uniq/count/avg/sum 等聚合 → aggregate
否则 → detail（保守）
```

### 7.2 策略矩阵

| `reject_detail_sql` | `detail_sample_only` | detail SQL 行为 |
|---------------------|----------------------|-----------------|
| true | * | `ok=false` + hint 改写 |
| false | true | 执行 → sample 进 model → incomplete 门闩 |
| false | false | 执行 → 全文/截断进 model（**不推荐**，仅调试） |

**hint 示例**

```text
当前 SQL 为明细查询，无法直接回答汇总类问题。
请改用：get_fixed_analysis(key=...) 或 SELECT 维度, count() ... GROUP BY 维度
```

---

## 8. 系统贴表（Phase 4）

### 8.1 职责划分

| 组件 | 负责 |
|------|------|
| 模型 | 核心结论（定性为主）、运营建议、数据限制说明 |
| 系统 | `data` / `data_tables` 从完备 traces 渲染 Markdown 表或 UI 表格 |
| 用户 | Run Log / evidence 核对 SQL 与原始行 |

### 8.2 Prompt 约束（辅助，非唯一防线）

```text
支撑数据表格由系统自动展示；请勿在 Markdown 中重复粘贴大段表格。
结论中若引用具体 KPI，须与工具返回或上表一致；无法确认则写【数据限制】。
```

### 8.3 选表算法（示意）

```python
def select_display_tables(tool_traces) -> list[DisplayTable]:
    candidates = [
        t for t in tool_traces
        if t.ok and t.grain in ("fixed", "aggregate") and not t.truncated
    ]
    return [build_display_table(t) for t in candidates]
```

并行 PTC：按 `tool_index` 顺序全部展示，不合并。

---

## 9. Plan 模式（Phase 6，可选）

**触发**：配置 `ENABLE_PLAN_MODE=true` 或问题复杂度启发（≥3 独立指标）。

**例：用户**「概览 + DAU 趋势 + 漏斗 + 渠道，再给建议。」

**Plan 输出（Run Log 一步）**

```markdown
## 查数计划
1. get_fixed_analysis(overview)
2. get_fixed_analysis(dau)
3. get_fixed_analysis(funnel)
4. get_fixed_analysis(channel_completion)
→ 并行执行（PTC）
5. 基于四表写结论与建议
```

**执行**：系统或模型第二轮 PTC 跑 1–4 → Phase 4 贴四表 → 模型写 5。

---

## 10. 配置参考

见 [implementation-plan.md §配置汇总](./implementation-plan.md#配置汇总envexample-待增)。

---

## 11. 验收场景清单（Acceptance）

| ID | 场景 | 期望 |
|----|------|------|
| AC-01 | `/dau` slash | 不经 LLM；无 delivery partial |
| AC-02 | NL + fixed 完备查数 | success；audit=model 全文（小表） |
| AC-03 | NL + detail LIMIT 500，不交卷后再查 | partial，`incomplete_evidence` |
| AC-04 | detail 后再 channel fixed | success |
| AC-05 | 无 tool call 交卷 | partial，`missing_ok_query` |
| AC-06 | PTC 3 fixed | 3 并行；traces 顺序=模型顺序；3 表展示 |
| AC-07 | export_report 与 db_query 同批 | export 独占屏障，不与其他并行 |
| AC-08 | evidence 全文 | 样本包时 model-view 短于 audit-view |
| AC-09 | reject_detail_sql | detail SQL 返回 ok=false + hint |
| AC-10 | numeric_audit（可选） | 1800 warn，约1500 不 warn |

---

## 12. 实现映射

| Spec 章节 | Phase | 主要模块 |
|-----------|-------|----------|
| §5 数据契约 | 1 | `result_shape.py`, `clickhouse_tool.py` |
| §6 投影 | 1 | `tool_projection.py`, `react_engine.py` |
| §5.4 incomplete | 2 | `delivery_floor.py` |
| §7 SQL 形态 | 5 | `sql_classifier.py`, `pipeline.py` |
| §8 系统贴表 | 4 | `table_selection.py`, webui |
| §9 Plan | 6 | `react_engine.py` / 新工具 |
| §3.8 软 audit | 7 | `numeric_audit.py` |
| Spill | 8 | `evidence.py` |

任务拆解、文件新建列表、工期见 **[implementation-plan.md](./implementation-plan.md)**。

---

## 13. 决策记录（ADR 摘要）

| 决策 | 理由 |
|------|------|
| 不用 LLM compaction 压工具结果 | 问数口径不可丢；摘要本身可能幻觉 |
| 不用占位符 replace 作为主力 | ai_claw 实测：不灵活、易失败 |
| 不做硬数字精确匹配 | 误杀四舍五入与「约」 |
| 默认 detail_sample_only 而非 reject | 保留「看样例行」路径，但 incomplete 门闩 |
| 引入 truncated 语义 | 修复 `row_count=500` 暗示全集的 bug 类问题 |
| 学 dsh PTC，不学 Cordis | 问数单体 Python，ROI 不够 |

---

## 14. 附录：Slash vs Agent 路径对照

| 输入 | 路径 | LLM | 证据 | 建议 |
|------|------|-----|------|------|
| `/dau` | fixed_slash | 否 | SQL + rows | 无（by design） |
| 「最近一周日活？」 | agent_loop | 是 | traces + evidence | 有 |
| 同上但无 LLM Key | need_llm_or_slash | — | — | 提示用 slash |

Agent 路径须满足本 Spec §3、§5、§6；Slash 路径须保持 **数字路径干净**（无 LLM 散文）。
