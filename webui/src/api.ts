export type ChatRole = "user" | "assistant" | "system";

export interface ResultTable {
  columns: string[];
  rows: Record<string, unknown>[];
}

export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  createdAt: number;
  /** 结构化结果表（固定分析 / 查询摘要） */
  table?: ResultTable;
}

export interface ProgressStep {
  step: string;
  detail?: string;
  /** 完整原文（未截断）；有则点开可看全文 Markdown */
  full?: string;
  ts?: number;
}

export interface Session {
  id: string;
  title: string;
  messages: ChatMessage[];
  taskId: string | null;
  /** 已写入对话的 task，避免轮询重复追加答案 */
  deliveredTaskId?: string | null;
  status: string;
  progress: ProgressStep[];
  updatedAt: number;
}

export interface HealthInfo {
  status: string;
  clickhouse: string;
  llm_enabled: boolean;
  llm_provider?: string;
  llm_model?: string;
  service?: string;
}

export interface TaskPayload {
  task_id: string;
  status: string;
  progress?: ProgressStep[];
  final_result?: {
    answer?: string;
    evidence_path?: string;
    report?: { path?: string };
    data?: {
      rows?: Record<string, unknown>[];
      columns?: string[];
      name?: string;
      analysis_key?: string;
    };
    mode?: string;
    error?: string;
  };
}

export interface FormattedAssistant {
  content: string;
  table?: ResultTable;
}

const COL_LABELS: Record<string, string> = {
  cohort_size: "Cohort 用户数",
  d1_retained: "次日留存人数",
  d7_retained: "七日留存人数",
  d1_rate: "次日留存率",
  d7_rate: "七日留存率",
  new_learners: "新增学习者",
  dau: "DAU",
  start_lesson_cnt: "开课次数",
  complete_lesson_cnt: "完课次数",
  completion_rate: "完课率",
  exercise_users: "练习用户数",
  dt: "日期",
  view_path_uv: "浏览路径 UV",
  start_lesson_uv: "开课 UV",
  complete_lesson_uv: "完课 UV",
  submit_exercise_uv: "交练习 UV",
  register_channel: "注册渠道",
  complete_uv: "完课 UV",
  user_cnt: "用户数",
};

function uid() {
  return Math.random().toString(36).slice(2, 10);
}

export function columnLabel(key: string): string {
  return COL_LABELS[key] || key;
}

export function formatCellValue(key: string, value: unknown): string {
  if (value == null) return "";
  if (typeof value === "boolean") return value ? "是" : "否";
  if (typeof value === "number") {
    const kl = key.toLowerCase();
    if (kl.endsWith("_rate") || kl.endsWith("_pct") || kl.endsWith("_ratio")) {
      if (value >= 0 && value <= 1) return `${(value * 100).toFixed(2)}%`;
      return `${value.toFixed(2)}%`;
    }
    if (!Number.isInteger(value)) return Number(value.toPrecision(6)).toString();
    return String(value);
  }
  return String(value);
}

export function buildResultTable(
  data: NonNullable<TaskPayload["final_result"]>["data"],
  limit = 20
): ResultTable | undefined {
  const rows = (data?.rows || []).slice(0, limit);
  if (!rows.length) return undefined;
  const columns =
    data?.columns && data.columns.length
      ? data.columns
      : Object.keys(rows[0] || {});
  if (!columns.length) return undefined;
  return { columns, rows };
}

export async function fetchHealth(): Promise<HealthInfo> {
  const r = await fetch("/health");
  if (!r.ok) throw new Error("health failed");
  return r.json();
}

export async function startChat(query: string): Promise<{ task_id: string }> {
  const r = await fetch("/api/v1/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, sync: false }),
  });
  if (!r.ok) throw new Error("chat failed");
  return r.json();
}

export async function fetchTask(taskId: string): Promise<TaskPayload> {
  const r = await fetch(`/api/v1/task/${taskId}`);
  if (r.status === 404) {
    const err = new Error("task not found");
    (err as Error & { code?: string }).code = "TASK_NOT_FOUND";
    throw err;
  }
  if (!r.ok) throw new Error("task failed");
  return r.json();
}

export function formatResult(result: TaskPayload["final_result"]): FormattedAssistant {
  if (!result) return { content: "(无结果)" };
  const mode = result.mode || "unknown";
  const lines: string[] = [];
  // slash 终态是 Markdown 报表；Agent 终态是叙事三段式。不在正文塞说教。
  if (mode === "error" || result.error) {
    lines.push("【执行失败】");
  }
  lines.push(result.answer || "");
  if (result.report?.path) lines.push(`\n报告: ${result.report.path}`);

  // slash：用结构化表（中文列名）；Agent：表格写在 Markdown「支撑数据」里，避免双表。
  const answer = result.answer || "";
  const wantTable =
    mode === "fixed_slash" ||
    (mode === "agent_loop" && !/\|\s*---/.test(answer));

  return {
    content: lines.join("\n").trim(),
    table: wantTable ? buildResultTable(result.data) : undefined,
  };
}

export function createSession(title = "新分析"): Session {
  const now = Date.now();
  return {
    id: uid(),
    title,
    messages: [
      {
        id: uid(),
        role: "system",
        content:
          "【关于本项目】\n" +
          "LumenLearn（流明学堂）是虚构的示例业务域：合成学习数据与指标用于跑通问数流程，不是真实产品。\n" +
          "核心能力是「自然语言 / slash → 只读查数 → 表格与结论」；换成你自己的库表与固定 SQL 同样可以分析——连接配置、事件字典、FIXED_QUERIES 都可替换。\n\n" +
          "【两条通道】\n" +
          "• slash（/dau 等）→ 固定 SQL，只出数据表，不经 LLM\n" +
          "• 中文提问 → Agent，产出「结论 + 支撑数据 + 运营建议」（需配置 LLM）",
        createdAt: now,
      },
    ],
    taskId: null,
    status: "idle",
    progress: [],
    updatedAt: now,
  };
}

export function newMessage(
  role: ChatRole,
  content: string,
  table?: ResultTable
): ChatMessage {
  return { id: uid(), role, content, createdAt: Date.now(), table };
}
