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
  /** 产出该条回复的后端 task */
  taskId?: string;
  /** 主证据路径（.scratchpad/evidence/...） */
  evidencePath?: string;
  /** 该 task 下全部证据文件 */
  evidenceFiles?: string[];
  /** 服务端写出的单次分析报告 md */
  reportPath?: string;
  /** 看板图表 png（slash 一键报告） */
  chartPath?: string;
  /** 交付薄地板提示（无硬栏） */
  deliveryNotice?: string;
  deliveryStatus?: string;
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
    evidence_files?: string[];
    report?: { path?: string; ok?: boolean };
    chart_path?: string;
    data?: {
      rows?: Record<string, unknown>[];
      columns?: string[];
      name?: string;
      analysis_key?: string;
      chart_path?: string;
    };
    mode?: string;
    error?: string;
    status?: string;
    delivery_notice?: string;
    delivery_gate?: string;
  };
}

export interface FormattedAssistant {
  content: string;
  table?: ResultTable;
  evidencePath?: string;
  evidenceFiles?: string[];
  reportPath?: string;
  chartPath?: string;
  deliveryNotice?: string;
  deliveryStatus?: string;
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

export function scratchpadDownloadUrl(path: string): string {
  let p = String(path || "").replace(/\\/g, "/").trim();
  if (p.startsWith("./")) p = p.slice(2);
  if (p.startsWith(".scratchpad/")) p = p.slice(".scratchpad/".length);
  else if (p.startsWith("scratchpad/")) p = p.slice("scratchpad/".length);
  p = p.replace(/^\/+/, "");
  return `/download/${p}`;
}

export function scratchpadBasename(path: string): string {
  const p = String(path || "").replace(/\\/g, "/");
  const i = p.lastIndexOf("/");
  return i >= 0 ? p.slice(i + 1) : p;
}

/** 触发浏览器下载 scratchpad 内单个文件。 */
export function downloadScratchpadPath(path: string): void {
  const url = scratchpadDownloadUrl(path);
  const a = document.createElement("a");
  a.href = url;
  a.download = scratchpadBasename(path) || "download";
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

export async function downloadReportBundle(payload: {
  title: string;
  markdown: string;
  paths: string[];
  filenameHint?: string;
}): Promise<void> {
  const r = await fetch("/api/v1/reports/bundle", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title: payload.title,
      markdown: payload.markdown,
      paths: payload.paths,
    }),
  });
  if (!r.ok) throw new Error("打包下载失败");
  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = payload.filenameHint || "analysis_bundle.zip";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function formatResult(result: TaskPayload["final_result"]): FormattedAssistant {
  if (!result) return { content: "(无结果)" };
  const mode = result.mode || "unknown";
  const lines: string[] = [];
  if (mode === "error" || result.error) {
    lines.push("【执行失败】");
  }
  lines.push(result.answer || "");

  const evidenceFiles = (result.evidence_files || []).filter(Boolean);
  const evidencePath = result.evidence_path || evidenceFiles[evidenceFiles.length - 1];
  const reportPath = result.report?.path;
  const chartPath =
    result.chart_path ||
    (result.data && typeof result.data === "object"
      ? (result.data as { chart_path?: string }).chart_path
      : undefined);

  // slash：用结构化表；Agent：表格写在 Markdown「支撑数据」里，避免双表。
  const answer = result.answer || "";
  const wantTable =
    mode === "fixed_slash" ||
    (mode === "agent_loop" && !/\|\s*---/.test(answer));

  return {
    content: lines.join("\n").trim(),
    table: wantTable ? buildResultTable(result.data) : undefined,
    evidencePath,
    evidenceFiles: evidenceFiles.length ? evidenceFiles : evidencePath ? [evidencePath] : undefined,
    reportPath,
    chartPath,
    deliveryNotice: result.delivery_notice,
    deliveryStatus: result.status,
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
          "这是通用 NL2SQL / 问数 Agent（slash + ReAct + 只读查数）。\n" +
          "当前预置的 LumenLearn 只是临时虚构场景与样本库，方便开箱试用；换成你自己的连接、表结构与 FIXED_QUERIES 即可做真实业务分析。\n\n" +
          "【两条通道】\n" +
          "• slash（/dau、/today_dashboard 等）→ 固定看板：查数 + 画图 + 报告，不经 LLM\n" +
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
  table?: ResultTable,
  extras?: Partial<
    Pick<
      ChatMessage,
      | "taskId"
      | "evidencePath"
      | "evidenceFiles"
      | "reportPath"
      | "chartPath"
      | "deliveryNotice"
      | "deliveryStatus"
    >
  >
): ChatMessage {
  return {
    id: uid(),
    role,
    content,
    createdAt: Date.now(),
    table,
    ...extras,
  };
}
